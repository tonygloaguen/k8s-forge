"""Observability readiness file rendering."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateError,
    select_autoescape,
)

from k8s_forge.exceptions import RenderError
from k8s_forge.models import AppConfig


@dataclass(frozen=True)
class ObservabilityTemplateSpec:
    """Mapping between an observability template and generated output file."""

    template_name: str
    output_name: str
    enabled: bool = True


GENERATED_OBSERVABILITY_FILES = (
    "README.md",
    "prometheus/servicemonitor.yaml",
    "grafana/dashboard.json",
)


def resolve_service_monitor_namespace(config: AppConfig) -> str:
    """Return the ServiceMonitor namespace."""
    configured_namespace = config.observability.serviceMonitor.namespace.strip()
    if configured_namespace:
        return configured_namespace
    return config.app.namespace


def resolve_dashboard_title(config: AppConfig) -> str:
    """Return the Grafana dashboard title."""
    configured_title = config.observability.grafana.dashboard.title.strip()
    if configured_title:
        return configured_title
    return config.app.name


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("observability_templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def _template_specs(config: AppConfig) -> list[ObservabilityTemplateSpec]:
    return [
        ObservabilityTemplateSpec("README.md.j2", "README.md"),
        ObservabilityTemplateSpec(
            "prometheus/servicemonitor.yaml.j2",
            "prometheus/servicemonitor.yaml",
            enabled=config.observability.serviceMonitor.enabled,
        ),
        ObservabilityTemplateSpec(
            "grafana/dashboard.json.j2",
            "grafana/dashboard.json",
            enabled=(
                config.observability.grafana.enabled
                and config.observability.grafana.dashboard.enabled
            ),
        ),
    ]


def _context(config: AppConfig) -> dict[str, Any]:
    return {
        "app": config.app,
        "service": config.service,
        "observability": config.observability,
        "service_monitor_namespace": resolve_service_monitor_namespace(config),
        "dashboard_title": resolve_dashboard_title(config),
    }


def _check_existing_files(paths: list[Path], force: bool) -> None:
    if force:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing)
        msg = (
            "Observability output file already exists, use --force to overwrite: "
            f"{rendered}"
        )
        raise RenderError(msg)


def render_observability_files(
    config: AppConfig,
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Render observability readiness files into the output directory."""
    if not config.observability.enabled:
        return []

    specs = [spec for spec in _template_specs(config) if spec.enabled]
    output_paths = [output_dir / spec.output_name for spec in specs]
    _check_existing_files(output_paths, force)

    environment = _template_environment()
    context = _context(config)
    written_files: list[Path] = []

    try:
        for spec, output_path in zip(specs, output_paths, strict=True):
            template = environment.get_template(spec.template_name)
            rendered = template.render(context).rstrip() + "\n"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
            written_files.append(output_path)
    except (OSError, TemplateError) as exc:
        msg = f"Unable to render observability files: {exc}"
        raise RenderError(msg) from exc

    return written_files
