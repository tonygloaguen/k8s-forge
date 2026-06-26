"""Logging readiness file rendering."""

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
class LoggingTemplateSpec:
    """Mapping between a logging template and generated output file."""

    template_name: str
    output_name: str
    enabled: bool = True


GENERATED_LOGGING_FILES = (
    "README.md",
    "loki/logql-queries.md",
    "grafana/logs-dashboard.json",
    "collector/collector-notes.md",
)


def resolve_logging_dashboard_title(config: AppConfig) -> str:
    """Return the Grafana logs dashboard title."""
    configured_title = config.logging.grafana.dashboard.title.strip()
    if configured_title:
        return configured_title
    return config.app.name


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("logging_templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def _template_specs(config: AppConfig) -> list[LoggingTemplateSpec]:
    return [
        LoggingTemplateSpec("README.md.j2", "README.md"),
        LoggingTemplateSpec(
            "loki/logql-queries.md.j2",
            "loki/logql-queries.md",
            enabled=config.logging.queries.enabled,
        ),
        LoggingTemplateSpec(
            "grafana/logs-dashboard.json.j2",
            "grafana/logs-dashboard.json",
            enabled=(
                config.logging.grafana.enabled
                and config.logging.grafana.dashboard.enabled
            ),
        ),
        LoggingTemplateSpec(
            "collector/collector-notes.md.j2",
            "collector/collector-notes.md",
            enabled=config.logging.collector.enabled,
        ),
    ]


def _context(config: AppConfig) -> dict[str, Any]:
    return {
        "app": config.app,
        "logging": config.logging,
        "dashboard_title": resolve_logging_dashboard_title(config),
    }


def _check_existing_files(paths: list[Path], force: bool) -> None:
    if force:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing)
        msg = (
            f"Logging output file already exists, use --force to overwrite: {rendered}"
        )
        raise RenderError(msg)


def render_logging_files(
    config: AppConfig,
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Render logging readiness files into the output directory."""
    if not config.logging.enabled:
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
        msg = f"Unable to render logging files: {exc}"
        raise RenderError(msg) from exc

    return written_files
