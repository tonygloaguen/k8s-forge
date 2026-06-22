"""Command line interface for k8s-forge."""

from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from k8s_forge import __version__
from k8s_forge.config_loader import load_app_config
from k8s_forge.exceptions import (
    ConfigLoadError,
    KubectlError,
    LocalCommandError,
    RenderError,
)
from k8s_forge.kubectl import KubectlResult, run_kubectl
from k8s_forge.local_cluster import (
    LocalCommandResult,
    ToolCheck,
    check_environment,
    create_kind_cluster,
    current_context,
    delete_kind_cluster,
    docker_image_inspect,
    get_kind_clusters,
    get_nodes,
    load_docker_image,
    wait_for_nodes_ready,
)
from k8s_forge.models import AppConfig
from k8s_forge.renderer import render_manifests

app = typer.Typer(
    help="Generic Kubernetes manifest generator for stateless web applications.",
    no_args_is_help=True,
)
console = Console()
cluster_app = typer.Typer(help="Manage local kind clusters.")
image_app = typer.Typer(help="Manage local images for kind clusters.")


class _QuotedString(str):
    """String rendered with double quotes in starter YAML."""


class _InitConfigDumper(yaml.SafeDumper):
    """YAML dumper for starter configuration files."""


def _quoted_string_representer(
    dumper: yaml.SafeDumper, data: _QuotedString
) -> yaml.nodes.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')


_InitConfigDumper.add_representer(_QuotedString, _quoted_string_representer)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"k8s-forge {__version__}")
        raise typer.Exit


def _service_state(config: AppConfig) -> str:
    if config.service.enabled:
        return f"enabled on port {config.service.port}"
    return "disabled"


def _autoscaling_state(config: AppConfig) -> str:
    if not config.autoscaling.enabled:
        return "disabled"
    return (
        "enabled "
        f"min={config.autoscaling.minReplicas} "
        f"max={config.autoscaling.maxReplicas} "
        f"cpu={config.autoscaling.targetCPUUtilizationPercentage}%"
    )


def _autoscaling_warning(config: AppConfig) -> str | None:
    if (
        config.autoscaling.enabled
        and config.app.replicas < config.autoscaling.minReplicas
    ):
        return (
            "autoscaling is enabled but app.replicas is lower than "
            "autoscaling.minReplicas; Kubernetes may scale from the HPA minimum "
            "after the HorizontalPodAutoscaler is active."
        )
    return None


def _print_autoscaling_warning(config: AppConfig) -> None:
    warning = _autoscaling_warning(config)
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")


def _print_check_summary(config: AppConfig) -> None:
    """Print a concise validation summary."""
    table = Table(title="Application configuration")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("app name", config.app.name)
    table.add_row("namespace", config.app.namespace)
    table.add_row("image", config.app.image)
    table.add_row("replicas", str(config.app.replicas))
    table.add_row("container port", str(config.app.containerPort))
    table.add_row("service", _service_state(config))
    table.add_row("autoscaling", _autoscaling_state(config))
    console.print(table)


def _print_render_summary(paths: list[Path]) -> None:
    """Print the generated manifest paths."""
    table = Table(title="Generated manifests")
    table.add_column("File")
    for path in paths:
        table.add_row(path.name)
    console.print(table)


def _starter_config_data(
    name: str,
    namespace: str | None,
    image: str | None,
    port: int,
    replicas: int,
    service_port: int,
    hpa_enabled: bool,
    hpa_min: int,
    hpa_max: int,
    hpa_cpu: int,
) -> dict[str, Any]:
    app_namespace = namespace or name
    app_image = image or f"{name}:latest"
    return {
        "app": {
            "name": name,
            "namespace": app_namespace,
            "image": app_image,
            "containerPort": port,
            "replicas": replicas,
        },
        "config": {
            "APP_ENV": _QuotedString("dev"),
            "LOG_LEVEL": _QuotedString("info"),
        },
        "secrets": {
            "API_TOKEN": _QuotedString("change-me"),
        },
        "service": {
            "enabled": True,
            "port": service_port,
        },
        "resources": {
            "requests": {
                "cpu": _QuotedString("50m"),
                "memory": _QuotedString("64Mi"),
            },
            "limits": {
                "cpu": _QuotedString("250m"),
                "memory": _QuotedString("128Mi"),
            },
        },
        "probes": {
            "liveness": _QuotedString("/healthz"),
            "readiness": _QuotedString("/readyz"),
        },
        "autoscaling": {
            "enabled": hpa_enabled,
            "minReplicas": hpa_min,
            "maxReplicas": hpa_max,
            "targetCPUUtilizationPercentage": hpa_cpu,
        },
        "ingress": {
            "enabled": False,
            "host": None,
        },
    }


def _starter_config_yaml(data: dict[str, Any]) -> str:
    rendered = yaml.dump(
        data,
        Dumper=_InitConfigDumper,
        sort_keys=False,
        default_flow_style=False,
    )
    return rendered.rstrip() + "\n"


def _load_and_render(config_path: Path, output: Path) -> list[Path]:
    loaded = load_app_config(config_path)
    return render_manifests(loaded, output)


def _load_config_and_render(
    config_path: Path, output: Path
) -> tuple[AppConfig, list[Path]]:
    loaded = load_app_config(config_path)
    return loaded, render_manifests(loaded, output)


def _print_kubectl_result(result: KubectlResult) -> None:
    if result.stdout:
        console.print(result.stdout.rstrip())
    if result.stderr:
        console.print(result.stderr.rstrip(), style="red")


def _run_kubectl_or_exit(
    args: list[str],
    timeout: int,
    success_codes: tuple[int, ...] = (0,),
) -> KubectlResult:
    try:
        result = run_kubectl(args, timeout=timeout)
    except KubectlError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_kubectl_result(result)
    if result.returncode not in success_codes:
        raise typer.Exit(code=result.returncode or 1)
    return result


def _namespace_not_found(output: str, namespace: str) -> bool:
    normalized = output.lower()
    quoted_double = f'namespaces "{namespace.lower()}" not found'
    quoted_single = f"namespaces '{namespace.lower()}' not found"
    return (
        quoted_double in normalized
        or quoted_single in normalized
        or ("namespaces" in normalized and "not found" in normalized)
    )


def _print_namespace_dry_run_warning(namespace: str) -> None:
    console.print(
        f"[yellow]Namespace {namespace!r} does not exist in the cluster.[/yellow]"
    )
    console.print(
        "[yellow]Server-side dry-run simulates the Namespace manifest but does "
        "not persist it. Namespaced resources such as ConfigMap, Secret, "
        "Deployment, and Service may fail validation.[/yellow]"
    )
    console.print(
        f"[yellow]Create it first with: kubectl create namespace {namespace}[/yellow]"
    )


def _print_namespace_dry_run_failure(
    namespace: str, config_path: Path, output: Path
) -> None:
    console.print(
        f"[yellow]The namespace {namespace!r} was only simulated during "
        "server-side dry-run; it was not really created.[/yellow]"
    )
    console.print(
        "[yellow]ConfigMap, Secret, Deployment, and Service cannot be validated "
        "inside a namespace that does not exist yet.[/yellow]"
    )
    console.print(f"[yellow]Run: kubectl create namespace {namespace}[/yellow]")
    rerun = f"k8s-forge dry-run {config_path} --output {output}"
    console.print(f"[yellow]Then rerun: {rerun}[/yellow]")


def _warn_if_namespace_missing(namespace: str, timeout: int) -> None:
    try:
        result = run_kubectl(["get", "namespace", namespace], timeout=timeout)
    except KubectlError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if result.ok:
        return

    combined = f"{result.stdout}\n{result.stderr}"
    if _namespace_not_found(combined, namespace):
        _print_namespace_dry_run_warning(namespace)
        return

    _print_kubectl_result(result)
    console.print(
        f"[yellow]Could not verify namespace {namespace!r} before dry-run; "
        "continuing so Kubernetes can return the authoritative validation "
        "result.[/yellow]"
    )


def _print_local_result(result: LocalCommandResult) -> None:
    if result.stdout:
        console.print(result.stdout.rstrip())
    if result.stderr:
        console.print(result.stderr.rstrip(), style="red")


def _run_local_or_exit(
    result: LocalCommandResult, success_codes: tuple[int, ...] = (0,)
) -> LocalCommandResult:
    _print_local_result(result)
    if result.returncode not in success_codes:
        raise typer.Exit(code=result.returncode or 1)
    return result


def _print_tool_checks(checks: list[ToolCheck]) -> None:
    table = Table(title="Local environment")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Details")
    for check in checks:
        table.add_row(check.name, check.status, check.details)
    console.print(table)
    for check in checks:
        if check.status != "OK" and check.details:
            console.print(f"{check.name}: {check.details}")


def _print_context_and_nodes(timeout: int) -> None:
    try:
        console.print("[bold]Current context[/bold]")
        _run_local_or_exit(current_context(timeout))
        console.print("[bold]Nodes[/bold]")
        _run_local_or_exit(get_nodes(timeout))
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


def _kind_clusters_or_exit(timeout: int) -> list[str]:
    try:
        return get_kind_clusters(timeout)
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help="Show the k8s-forge version and exit.",
        ),
    ] = False,
) -> None:
    """Run k8s-forge."""
    _ = version


@app.command()
def init(
    name: Annotated[str, typer.Argument(help="Application name for app.yaml.")],
    namespace: Annotated[
        str | None,
        typer.Option("--namespace", help="Kubernetes namespace."),
    ] = None,
    image: Annotated[
        str | None,
        typer.Option("--image", help="Container image."),
    ] = None,
    port: Annotated[
        int,
        typer.Option("--port", help="Container port."),
    ] = 8000,
    replicas: Annotated[
        int,
        typer.Option("--replicas", help="Deployment replica count."),
    ] = 1,
    service_port: Annotated[
        int,
        typer.Option("--service-port", help="Service port."),
    ] = 80,
    hpa: Annotated[
        bool,
        typer.Option("--hpa", help="Enable Horizontal Pod Autoscaler."),
    ] = False,
    hpa_min: Annotated[
        int,
        typer.Option("--hpa-min", help="HPA minimum replicas."),
    ] = 2,
    hpa_max: Annotated[
        int,
        typer.Option("--hpa-max", help="HPA maximum replicas."),
    ] = 6,
    hpa_cpu: Annotated[
        int,
        typer.Option("--hpa-cpu", help="HPA target CPU utilization percentage."),
    ] = 70,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output app.yaml path."),
    ] = Path("app.yaml"),
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing output file."),
    ] = False,
) -> None:
    """Create a starter app.yaml file."""
    if output.exists() and not force:
        console.print("[red]file already exists, use --force to overwrite[/red]")
        raise typer.Exit(code=1)

    data = _starter_config_data(
        name,
        namespace,
        image,
        port,
        replicas,
        service_port,
        hpa,
        hpa_min,
        hpa_max,
        hpa_cpu,
    )
    try:
        generated_config = AppConfig.model_validate(data)
    except ValidationError as exc:
        console.print(f"[red]Generated configuration is invalid: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if output.parent != Path(""):
        output.parent.mkdir(parents=True, exist_ok=True)
    _print_autoscaling_warning(generated_config)
    output.write_text(_starter_config_yaml(data), encoding="utf-8")
    console.print(f"[green]created {output}[/green]")


@app.command()
def check(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
) -> None:
    """Validate an app.yaml configuration file."""
    try:
        loaded = load_app_config(config_path)
    except ConfigLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print("[green]configuration is valid[/green]")
    _print_check_summary(loaded)
    _print_autoscaling_warning(loaded)


@app.command()
def render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for manifests."),
    ] = Path("generated"),
) -> None:
    """Render Kubernetes manifests."""
    try:
        loaded, generated = _load_config_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_autoscaling_warning(loaded)
    console.print("[green]manifests generated[/green]")
    _print_render_summary(generated)


@app.command("dry-run")
def dry_run(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for manifests."),
    ] = Path("generated"),
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="kubectl timeout in seconds."),
    ] = 30,
) -> None:
    """Render manifests and run kubectl server-side dry-run."""
    try:
        loaded, generated = _load_config_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_render_summary(generated)
    _print_autoscaling_warning(loaded)
    _warn_if_namespace_missing(loaded.app.namespace, timeout)

    try:
        result = run_kubectl(
            ["apply", "--dry-run=server", "-f", str(output)], timeout=timeout
        )
    except KubectlError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_kubectl_result(result)
    combined = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        if _namespace_not_found(combined, loaded.app.namespace):
            _print_namespace_dry_run_failure(loaded.app.namespace, config_path, output)
        raise typer.Exit(code=result.returncode or 1)


@app.command()
def diff(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for manifests."),
    ] = Path("generated"),
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="kubectl timeout in seconds."),
    ] = 30,
) -> None:
    """Render manifests and run kubectl diff."""
    try:
        loaded, generated = _load_config_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_render_summary(generated)
    _print_autoscaling_warning(loaded)
    result = _run_kubectl_or_exit(["diff", "-f", str(output)], timeout, (0, 1))
    if result.returncode == 1:
        console.print("[yellow]kubectl diff found changes[/yellow]")


@app.command()
def apply(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for manifests."),
    ] = Path("generated"),
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Apply without interactive confirmation."),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="kubectl timeout in seconds."),
    ] = 30,
) -> None:
    """Render manifests and run controlled kubectl apply."""
    try:
        loaded, generated = _load_config_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_render_summary(generated)
    _print_autoscaling_warning(loaded)
    console.print(
        "[yellow]This will apply manifests to the current Kubernetes context.[/yellow]"
    )
    if not yes and not typer.confirm("Continue with kubectl apply?"):
        console.print("apply cancelled")
        return

    _run_kubectl_or_exit(["apply", "-f", str(output)], timeout)


@app.command()
def status(
    name: Annotated[str, typer.Argument(help="Application name.")],
    namespace: Annotated[
        str,
        typer.Option("--namespace", "-n", help="Kubernetes namespace."),
    ],
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="kubectl timeout in seconds."),
    ] = 30,
) -> None:
    """Show application status from kubectl."""
    _run_kubectl_or_exit(
        ["-n", namespace, "get", "deploy,po,svc", "-l", f"app={name}"],
        timeout,
    )

    hpa_result = _run_kubectl_or_exit(
        ["-n", namespace, "get", "hpa", "-l", f"app={name}"],
        timeout,
    )
    combined = f"{hpa_result.stdout}\n{hpa_result.stderr}".strip().lower()
    if not combined or "no resources found" in combined:
        console.print(f"[yellow]No HPA found for app {name}[/yellow]")


@app.command()
def doctor(
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Local command timeout in seconds."),
    ] = 30,
) -> None:
    """Check local Docker, kind, and kubectl prerequisites."""
    report = check_environment(timeout)
    _print_tool_checks(
        [
            report.docker,
            report.kind,
            report.kubectl,
            report.current_context,
            report.nodes,
            report.metrics_server,
        ]
    )
    if report.metrics_server.status == "OK":
        console.print("[green]metrics-server available[/green]")
    else:
        console.print(
            "[yellow]metrics-server not found; HPA CPU metrics may stay "
            "<unknown> on kind until metrics-server is installed.[/yellow]"
        )
    if report.ready:
        console.print("[green]Ready for local kind workflows.[/green]")
    else:
        console.print(
            "[yellow]Missing or failing prerequisites. "
            "Install or fix the tools above.[/yellow]"
        )


@cluster_app.command("create")
def cluster_create(
    name: Annotated[
        str,
        typer.Option("--name", help="kind cluster name."),
    ] = "devsecops",
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Local command timeout in seconds."),
    ] = 120,
) -> None:
    """Create a local kind cluster if it does not already exist."""
    clusters = _kind_clusters_or_exit(timeout)
    if name in clusters:
        console.print(
            f"[yellow]kind cluster {name} already exists; skipping create.[/yellow]"
        )
        _print_context_and_nodes(timeout)
        return

    try:
        result = create_kind_cluster(name, timeout)
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    _run_local_or_exit(result)

    console.print("[bold]Waiting for nodes to become Ready[/bold]")
    try:
        wait_result = wait_for_nodes_ready(timeout)
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("[yellow]Check cluster state with: kubectl get nodes[/yellow]")
        console.print("[yellow]Inspect system pods with: kubectl get pods -A[/yellow]")
        raise typer.Exit(code=1) from exc
    _print_local_result(wait_result)
    if not wait_result.ok:
        console.print(
            "[red]Timed out or failed while waiting for nodes to be Ready.[/red]"
        )
        console.print("[yellow]Check cluster state with: kubectl get nodes[/yellow]")
        console.print("[yellow]Inspect system pods with: kubectl get pods -A[/yellow]")
        raise typer.Exit(code=wait_result.returncode or 1)

    _print_context_and_nodes(timeout)


@cluster_app.command("status")
def cluster_status(
    name: Annotated[
        str,
        typer.Option("--name", help="kind cluster name."),
    ] = "devsecops",
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Local command timeout in seconds."),
    ] = 30,
) -> None:
    """Show local kind cluster status."""
    clusters = _kind_clusters_or_exit(timeout)
    if name not in clusters:
        console.print(f"[red]kind cluster {name} does not exist.[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]kind cluster {name} exists.[/green]")
    _print_context_and_nodes(timeout)


@cluster_app.command("delete")
def cluster_delete(
    name: Annotated[
        str,
        typer.Option("--name", help="kind cluster name."),
    ] = "devsecops",
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Delete without interactive confirmation."),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Local command timeout in seconds."),
    ] = 120,
) -> None:
    """Delete a local kind cluster."""
    if not yes and not typer.confirm(f"Delete kind cluster {name}?"):
        console.print("cluster delete cancelled")
        return

    try:
        result = delete_kind_cluster(name, timeout)
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    _run_local_or_exit(result)


@image_app.command("load")
def image_load(
    image: Annotated[str, typer.Argument(help="Local Docker image to load.")],
    cluster: Annotated[
        str,
        typer.Option("--cluster", help="kind cluster name."),
    ] = "devsecops",
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Local command timeout in seconds."),
    ] = 120,
) -> None:
    """Load a local Docker image into a kind cluster."""
    try:
        inspect = docker_image_inspect(image, timeout)
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not inspect.ok:
        _print_local_result(inspect)
        console.print(f"[red]Docker image {image} was not found locally.[/red]")
        raise typer.Exit(code=1)

    try:
        result = load_docker_image(image, cluster, timeout)
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    _run_local_or_exit(result)
    console.print(f"[green]Loaded {image} into kind cluster {cluster}.[/green]")


app.add_typer(cluster_app, name="cluster")
app.add_typer(image_app, name="image")
