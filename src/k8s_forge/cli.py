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
from k8s_forge.exceptions import ConfigLoadError, KubectlError, RenderError
from k8s_forge.kubectl import KubectlResult, run_kubectl
from k8s_forge.models import AppConfig
from k8s_forge.renderer import render_manifests

app = typer.Typer(
    help="Generic Kubernetes manifest generator for stateless web applications.",
    no_args_is_help=True,
)
console = Console()


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
