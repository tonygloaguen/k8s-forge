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

    data = _starter_config_data(name, namespace, image, port, replicas, service_port)
    try:
        AppConfig.model_validate(data)
    except ValidationError as exc:
        console.print(f"[red]Generated configuration is invalid: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if output.parent != Path(""):
        output.parent.mkdir(parents=True, exist_ok=True)
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
        generated = _load_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

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
        generated = _load_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_render_summary(generated)
    _run_kubectl_or_exit(["apply", "--dry-run=server", "-f", str(output)], timeout)


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
        generated = _load_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_render_summary(generated)
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
        generated = _load_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_render_summary(generated)
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
        ]
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
