"""Tracing readiness file rendering."""

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
class TracingTemplateSpec:
    """Mapping between a tracing template and generated output file."""

    template_name: str
    output_name: str
    enabled: bool = True


GENERATED_TRACING_FILES = (
    "README.md",
    "opentelemetry/instrumentation-notes.md",
    "opentelemetry/otel-env.md",
    "tempo/traceql-examples.md",
    "grafana/traces-dashboard.json",
    "collector/collector-notes.md",
)


def resolve_tracing_service_name(config: AppConfig) -> str:
    """Return the OpenTelemetry service name."""
    configured_name = config.tracing.instrumentation.service_name.strip()
    if configured_name:
        return configured_name
    return config.app.name


def resolve_tracing_dashboard_title(config: AppConfig) -> str:
    """Return the Grafana traces dashboard title."""
    configured_title = config.tracing.grafana.dashboard.title.strip()
    if configured_title:
        return configured_title
    return config.app.name


def otel_protocol_value(config: AppConfig) -> str:
    """Return the environment variable value for OTLP protocol."""
    if config.tracing.collector.protocol == "otlp-grpc":
        return "grpc"
    return "http/protobuf"


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("tracing_templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def _template_specs(config: AppConfig) -> list[TracingTemplateSpec]:
    examples_enabled = config.tracing.examples.enabled
    return [
        TracingTemplateSpec("README.md.j2", "README.md"),
        TracingTemplateSpec(
            "opentelemetry/instrumentation-notes.md.j2",
            "opentelemetry/instrumentation-notes.md",
            enabled=config.tracing.instrumentation.enabled,
        ),
        TracingTemplateSpec(
            "opentelemetry/otel-env.md.j2",
            "opentelemetry/otel-env.md",
            enabled=config.tracing.instrumentation.enabled,
        ),
        TracingTemplateSpec(
            "tempo/traceql-examples.md.j2",
            "tempo/traceql-examples.md",
            enabled=examples_enabled,
        ),
        TracingTemplateSpec(
            "grafana/traces-dashboard.json.j2",
            "grafana/traces-dashboard.json",
            enabled=(
                config.tracing.grafana.enabled
                and config.tracing.grafana.dashboard.enabled
            ),
        ),
        TracingTemplateSpec(
            "collector/collector-notes.md.j2",
            "collector/collector-notes.md",
            enabled=config.tracing.collector.enabled,
        ),
    ]


def _context(config: AppConfig) -> dict[str, Any]:
    return {
        "app": config.app,
        "tracing": config.tracing,
        "service_name": resolve_tracing_service_name(config),
        "dashboard_title": resolve_tracing_dashboard_title(config),
        "otel_protocol": otel_protocol_value(config),
    }


def _check_existing_files(paths: list[Path], force: bool) -> None:
    if force:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing)
        msg = (
            f"Tracing output file already exists, use --force to overwrite: {rendered}"
        )
        raise RenderError(msg)


def render_tracing_files(
    config: AppConfig,
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Render tracing readiness files into the output directory."""
    if not config.tracing.enabled:
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
        msg = f"Unable to render tracing files: {exc}"
        raise RenderError(msg) from exc

    return written_files
