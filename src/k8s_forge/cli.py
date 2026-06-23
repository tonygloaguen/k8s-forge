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
from k8s_forge.helm_renderer import render_helm_chart
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
helm_app = typer.Typer(help="Generate local Helm charts.")


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


def _print_step(message: str) -> None:
    console.print(f"[bold]{message}[/bold]")


def _print_hint(message: str) -> None:
    console.print(message)


def _print_warning(message: str) -> None:
    console.print(f"[yellow]{message}[/yellow]")


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
            "Warning: Deployment replicas is lower than HPA minReplicas. "
            "Kubernetes will initially create the Deployment value, then the HPA "
            "may reconcile it back to its minimum once metrics are available."
        )
    return None


def _print_autoscaling_warning(config: AppConfig) -> None:
    warning = _autoscaling_warning(config)
    if warning:
        _print_warning(warning)


def _print_autoscaling_summary(config: AppConfig) -> None:
    if not config.autoscaling.enabled:
        return
    _print_hint("Autoscaling is enabled.")
    _print_hint(
        "The Deployment will start with "
        f"{config.app.replicas} replicas, and the HPA will be allowed to scale "
        f"between {config.autoscaling.minReplicas} and "
        f"{config.autoscaling.maxReplicas} pods based on CPU usage."
    )


def _print_hpa_runtime_hint(config: AppConfig) -> None:
    if not config.autoscaling.enabled:
        return
    _print_hint("Autoscaling is enabled, so an HPA manifest will be generated.")
    _print_hint("The HPA requires metrics-server to calculate CPU usage at runtime.")


def _print_ingress_summary(config: AppConfig) -> None:
    if not config.ingress.enabled:
        return
    _print_hint("Ingress is enabled.")
    _print_hint(
        "Kubernetes will route HTTP traffic for host "
        f"{config.ingress.host} to the Service."
    )
    _print_hint("Ingress requires an ingress controller such as ingress-nginx.")
    if config.ingress.tls.enabled:
        _print_hint("TLS is enabled for this Ingress.")
        _print_hint(
            "cert-manager can issue or prepare the certificate only if a "
            "matching ClusterIssuer exists."
        )


def _print_ingress_runtime_hint(config: AppConfig) -> None:
    if not config.ingress.enabled:
        return
    _print_hint("Ingress is enabled, so an Ingress manifest will be generated.")
    _print_hint(
        "This exposes the Service through an HTTP host rule, but it still "
        "requires ingress-nginx in the cluster."
    )
    _print_local_ingress_hints(config)


def _print_helm_ingress_hint(config: AppConfig) -> None:
    if not config.ingress.enabled:
        return
    _print_hint("The Helm chart includes an optional Ingress template.")
    _print_hint("Helm will not install ingress-nginx or cert-manager.")
    _print_hint("Validate those prerequisites separately.")
    _print_local_ingress_hints(config)


def _print_local_ingress_hints(config: AppConfig) -> None:
    if not config.ingress.host:
        return
    _print_hint("For local testing, map the host to localhost:")
    _print_hint(f"127.0.0.1 {config.ingress.host}")
    _print_warning(
        "On kind, ports 80 and 443 must be exposed by the cluster "
        "configuration for direct local ingress access."
    )
    _print_hint(
        "If they are not exposed, use port-forwarding or recreate the lab "
        "cluster with extraPortMappings."
    )


def _print_mesh_summary(config: AppConfig) -> None:
    if not config.mesh.enabled:
        return
    _print_hint("Service mesh support is enabled.")
    _print_hint(
        "A service mesh adds a sidecar proxy next to your application container."
    )
    _print_hint(
        "With Linkerd, injected pods usually show 2/2 containers: app + linkerd-proxy."
    )
    if config.mesh.inject:
        _print_hint("Linkerd injection is enabled for this workload.")
        _print_hint(
            "The generated Deployment includes the annotation "
            "linkerd.io/inject: enabled."
        )
        _print_hint(
            "After apply or helm upgrade, restart/rollout the Deployment and "
            "verify pods show 2/2 containers."
        )


def _print_mesh_validation_commands(namespace: str) -> None:
    _print_hint("Mesh validation commands:")
    _print_hint("  linkerd check")
    _print_hint(f"  kubectl -n {namespace} get pods")
    _print_hint(f"  kubectl -n {namespace} describe pod <pod>")
    _print_hint(f"  linkerd stat deploy -n {namespace}")


def _print_mesh_runtime_hint(config: AppConfig) -> None:
    if not config.mesh.enabled:
        return
    _print_mesh_summary(config)
    _print_hint("k8s-forge does not install Linkerd and does not run linkerd inject.")
    _print_mesh_validation_commands(config.app.namespace)


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


def _print_helm_chart_summary(paths: list[Path]) -> None:
    """Print generated Helm chart paths."""
    table = Table(title="Generated Helm chart files")
    table.add_column("File")
    chart_dir = paths[0].parent if paths else Path(".")
    for path in paths:
        table.add_row(str(path.relative_to(chart_dir)))
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
            "className": _QuotedString("nginx"),
            "path": _QuotedString("/"),
            "pathType": _QuotedString("Prefix"),
            "tls": {
                "enabled": False,
                "secretName": None,
            },
            "certManager": {
                "enabled": False,
                "clusterIssuer": None,
            },
            "annotations": {},
        },
        "mesh": {
            "enabled": False,
            "provider": _QuotedString("linkerd"),
            "inject": False,
            "annotations": {
                "linkerd.io/inject": _QuotedString("enabled"),
            },
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
    _print_step("Checking target namespace before dry-run...")
    _print_hint(
        "Server-side dry-run does not create the namespace for following "
        "resources, so the namespace must already exist."
    )
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
    _print_step("Validating application configuration...")
    _print_hint(
        "This step checks that app.yaml is structurally valid before "
        "generating Kubernetes manifests."
    )
    try:
        loaded = load_app_config(config_path)
    except ConfigLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print("[green]configuration is valid[/green]")
    _print_check_summary(loaded)
    _print_autoscaling_summary(loaded)
    _print_ingress_summary(loaded)
    _print_mesh_summary(loaded)
    if loaded.mesh.enabled:
        _print_mesh_validation_commands(loaded.app.namespace)
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
    _print_step("Rendering Kubernetes manifests from app.yaml...")
    _print_hint(
        "This does not contact the cluster. It only writes YAML files locally "
        "so they can be reviewed before applying them."
    )
    try:
        loaded, generated = _load_config_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_hpa_runtime_hint(loaded)
    _print_ingress_runtime_hint(loaded)
    _print_mesh_runtime_hint(loaded)
    _print_autoscaling_warning(loaded)
    console.print("[green]manifests generated[/green]")
    _print_render_summary(generated)
    _print_hint(f"Generated manifests are ready for review in {output}.")
    _print_hint("Review them before applying to the cluster.")


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
    _print_step("Running Kubernetes server-side dry-run...")
    _print_hint(
        "This sends the manifests to the Kubernetes API for validation, but "
        "does not persist changes."
    )
    _print_hint("No changes are persisted.")
    _print_autoscaling_warning(loaded)
    _warn_if_namespace_missing(loaded.app.namespace, timeout)
    if loaded.autoscaling.enabled:
        _print_step("Validating HPA manifest against the Kubernetes API...")
        _print_hint(
            "The HPA can be accepted even if metrics-server is not installed "
            "yet; in that case CPU targets may appear as <unknown>."
        )

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
    _print_step("Applying manifests to the current Kubernetes context...")
    _print_hint(
        "This will create or update Kubernetes resources to match the desired "
        "state declared in app.yaml."
    )
    _print_autoscaling_warning(loaded)
    _print_warning(
        "Current context will be modified. Review the generated manifests and "
        "the current context before continuing."
    )
    if not yes and not typer.confirm("Continue with kubectl apply?"):
        console.print("apply cancelled")
        return

    _run_kubectl_or_exit(["apply", "-f", str(output)], timeout)
    console.print("[green]Apply completed.[/green]")
    _print_hint(
        "Next steps: check rollout status, verify pods are Running, then test "
        "the Service."
    )


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
    _print_step(
        f"Reading Kubernetes status for application {name} in namespace {namespace}..."
    )
    _print_hint(
        "This checks the Deployment, Pods, Service, and HPA associated with "
        "the app label."
    )
    _print_hint(
        "Deployment status shows whether Kubernetes reached the desired number "
        "of replicas."
    )
    _print_hint("Pods are the actual running instances of the application containers.")
    _print_hint(
        "If a pod is deleted, the Deployment should recreate it to maintain "
        "the desired state."
    )
    _print_hint(
        "The Service provides a stable network entry point even when pods are "
        "recreated."
    )
    _run_kubectl_or_exit(
        ["-n", namespace, "get", "deploy,po,svc", "-l", f"app={name}"],
        timeout,
    )

    _print_hint(
        "The HPA controls scaling between minReplicas and maxReplicas based "
        "on CPU metrics."
    )
    _print_hint(
        "If TARGETS shows <unknown>, metrics-server is missing or not ready yet."
    )
    hpa_result = _run_kubectl_or_exit(
        ["-n", namespace, "get", "hpa", "-l", f"app={name}"],
        timeout,
    )
    combined = f"{hpa_result.stdout}\n{hpa_result.stderr}".strip().lower()
    if not combined or "no resources found" in combined:
        _print_warning(f"No HPA found for app {name}.")
        _print_hint("This is normal when autoscaling.enabled is false.")


@app.command()
def doctor(
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Local command timeout in seconds."),
    ] = 30,
) -> None:
    """Check local Docker, kind, and kubectl prerequisites."""
    _print_step("Checking local DevSecOps toolchain...")
    _print_hint(
        "This verifies that the required command-line tools are available "
        "before using k8s-forge."
    )
    _print_step("Checking metrics-server availability...")
    _print_hint(
        "metrics-server is required for HPA CPU metrics. Without it, HPA "
        "TARGETS may stay <unknown>."
    )
    report = check_environment(timeout)
    _print_tool_checks(
        [
            report.docker,
            report.kind,
            report.kubectl,
            report.current_context,
            report.nodes,
            report.metrics_server,
            report.ingress_nginx,
            report.cert_manager,
            report.linkerd_cli,
            report.linkerd_namespace,
            report.linkerd_control_plane,
            report.linkerd_viz,
        ]
    )
    if report.metrics_server.status == "OK":
        console.print("[green]metrics-server available.[/green]")
        _print_hint("HPA can read CPU and memory metrics from the cluster.")
    else:
        _print_warning("metrics-server not found.")
        _print_hint(
            "HPA manifests can still be created, but CPU-based scaling will "
            "not work until metrics-server is installed."
        )
    _print_step("Checking ingress-nginx readiness...")
    _print_hint(
        "Ingress resources need an ingress controller before traffic can "
        "reach the Service."
    )
    if report.ingress_nginx.status == "OK":
        console.print("[green]ingress-nginx available.[/green]")
    else:
        _print_warning("ingress-nginx not found.")
        _print_hint(
            "k8s-forge will not install ingress-nginx automatically; install "
            "it manually before testing Ingress traffic."
        )

    _print_step("Checking cert-manager readiness...")
    _print_hint(
        "cert-manager is required only when TLS certificate automation is enabled."
    )
    if report.cert_manager.status == "OK":
        console.print("[green]cert-manager available.[/green]")
    else:
        _print_warning("cert-manager not found.")
        _print_hint(
            "k8s-forge will not install cert-manager automatically; install "
            "it manually before using cert-manager annotations."
        )

    _print_step("Checking Linkerd service mesh readiness...")
    _print_hint(
        "Linkerd adds a sidecar proxy to injected pods so service-to-service "
        "traffic can be observed and secured."
    )
    if (
        report.linkerd_cli.status == "OK"
        and report.linkerd_namespace.status == "OK"
        and report.linkerd_control_plane.status == "OK"
    ):
        console.print("[green]Linkerd control plane appears to be available.[/green]")
    else:
        _print_warning("Linkerd does not appear to be installed in this cluster.")
        _print_hint("k8s-forge will not install it automatically.")
        _print_hint(
            "Install and validate Linkerd manually before expecting sidecars "
            "or mesh metrics."
        )
    if report.linkerd_viz.status == "OK":
        console.print("[green]Linkerd Viz appears to be available.[/green]")
    else:
        _print_hint("Linkerd Viz is optional and was not detected.")

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
    _print_step("Checking kind cluster status...")
    _print_hint("A Ready node means Kubernetes can schedule and run pods.")
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
    _print_step("Loading Docker image into kind cluster...")
    _print_hint(
        "kind nodes use their own containerd image store. Loading the image "
        "makes it available to pods without pushing it to a registry."
    )
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


@helm_app.command("render")
def helm_render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for charts."),
    ] = Path("charts"),
    chart_name: Annotated[
        str | None,
        typer.Option("--chart-name", help="Generated chart directory name."),
    ] = None,
) -> None:
    """Render a local Helm chart from app.yaml."""
    _print_step("Rendering a Helm chart from app.yaml...")
    _print_hint(
        "Helm packages Kubernetes manifests into a reusable and configurable chart."
    )
    _print_hint("This step does not contact the cluster and does not install anything.")
    try:
        loaded = load_app_config(config_path)
        generated = render_helm_chart(loaded, output, chart_name)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    resolved_chart_name = chart_name or loaded.app.name
    chart_dir = output / resolved_chart_name
    console.print(f"[green]Helm chart generated in {chart_dir}.[/green]")
    _print_helm_chart_summary(generated)
    _print_helm_ingress_hint(loaded)
    _print_mesh_runtime_hint(loaded)
    _print_warning(
        "If raw Kubernetes resources already exist from k8s-forge apply, Helm "
        "may refuse to import them because of ownership metadata."
    )
    _print_hint(
        "For a clean lab migration, delete the raw resources first or use a "
        "fresh namespace."
    )
    _print_hint("Next validation commands:")
    _print_hint(f"  helm lint {chart_dir}")
    _print_hint(
        f"  helm template {resolved_chart_name} {chart_dir} -n {loaded.app.namespace}"
    )
    _print_hint(
        "  helm upgrade --install "
        f"{resolved_chart_name} {chart_dir} -n {loaded.app.namespace} "
        "--create-namespace"
    )


app.add_typer(cluster_app, name="cluster")
app.add_typer(image_app, name="image")
app.add_typer(helm_app, name="helm")
