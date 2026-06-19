"""Command line interface for k8s-forge."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from k8s_forge import __version__
from k8s_forge.config_loader import load_app_config
from k8s_forge.exceptions import ConfigLoadError
from k8s_forge.kubectl import kubectl_not_implemented
from k8s_forge.models import AppConfig

app = typer.Typer(
    help="Generic Kubernetes manifest generator for stateless web applications.",
    no_args_is_help=True,
)
console = Console()


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
    name: Annotated[str, typer.Argument(help="Application name for the template.")],
) -> None:
    """Create a starter app.yaml file."""
    console.print(f"init for {name}: not implemented yet")


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
    _ = (config_path, output)
    console.print("render is not implemented yet")


@app.command("dry-run")
def dry_run(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for manifests."),
    ] = Path("generated"),
) -> None:
    """Render manifests and perform a future kubectl dry run."""
    _ = (config_path, output)
    console.print(kubectl_not_implemented("dry-run"))


@app.command()
def diff(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for manifests."),
    ] = Path("generated"),
) -> None:
    """Render manifests and perform a future kubectl diff."""
    _ = (config_path, output)
    console.print(kubectl_not_implemented("diff"))


@app.command()
def apply(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for manifests."),
    ] = Path("generated"),
) -> None:
    """Render manifests and perform a future controlled kubectl apply."""
    _ = (config_path, output)
    console.print(kubectl_not_implemented("apply"))


@app.command()
def status(
    name: Annotated[str, typer.Argument(help="Application name.")],
    namespace: Annotated[
        str,
        typer.Option("--namespace", "-n", help="Kubernetes namespace."),
    ],
) -> None:
    """Show future application status from kubectl."""
    _ = (name, namespace)
    console.print(kubectl_not_implemented("status"))
