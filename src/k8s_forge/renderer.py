"""Manifest rendering entry points."""

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
from k8s_forge.models import AppConfig, ResourceValues


@dataclass(frozen=True)
class TemplateSpec:
    """Mapping between a template and its generated output file."""

    template_name: str
    output_name: str
    enabled: bool = True


GENERATED_FILENAMES = (
    "00-namespace.yaml",
    "10-configmap.yaml",
    "20-secret.yaml",
    "30-deployment.yaml",
    "40-service.yaml",
    "50-hpa.yaml",
)


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def _labels(app_name: str) -> dict[str, str]:
    return {
        "app": app_name,
        "app.kubernetes.io/name": app_name,
        "app.kubernetes.io/part-of": app_name,
        "app.kubernetes.io/managed-by": "k8s-forge",
    }


def _selector_labels(app_name: str) -> dict[str, str]:
    return {
        "app": app_name,
        "app.kubernetes.io/name": app_name,
    }


def _resource_values(values: ResourceValues) -> dict[str, str]:
    return values.model_dump(exclude_none=True)


def _resources(config: AppConfig) -> dict[str, dict[str, str]]:
    resources: dict[str, dict[str, str]] = {}
    requests = _resource_values(config.resources.requests)
    limits = _resource_values(config.resources.limits)
    if requests:
        resources["requests"] = requests
    if limits:
        resources["limits"] = limits
    return resources


def _env_from(config: AppConfig) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    if config.config:
        sources.append({"kind": "configMapRef", "name": f"{config.app.name}-config"})
    if config.secrets:
        sources.append({"kind": "secretRef", "name": f"{config.app.name}-secret"})
    return sources


def _context(config: AppConfig) -> dict[str, Any]:
    app_name = config.app.name
    return {
        "app": config.app,
        "config": config.config,
        "secrets": config.secrets,
        "service": config.service,
        "labels": _labels(app_name),
        "selector_labels": _selector_labels(app_name),
        "resources": _resources(config),
        "env_from": _env_from(config),
        "probes": config.probes,
        "autoscaling": config.autoscaling,
    }


def _template_specs(config: AppConfig) -> list[TemplateSpec]:
    return [
        TemplateSpec("00-namespace.yaml.j2", "00-namespace.yaml"),
        TemplateSpec(
            "10-configmap.yaml.j2",
            "10-configmap.yaml",
            enabled=bool(config.config),
        ),
        TemplateSpec(
            "20-secret.yaml.j2",
            "20-secret.yaml",
            enabled=bool(config.secrets),
        ),
        TemplateSpec("30-deployment.yaml.j2", "30-deployment.yaml"),
        TemplateSpec(
            "40-service.yaml.j2",
            "40-service.yaml",
            enabled=config.service.enabled,
        ),
        TemplateSpec(
            "50-hpa.yaml.j2",
            "50-hpa.yaml",
            enabled=config.autoscaling.enabled,
        ),
    ]


def _clear_previous_generated_files(output_dir: Path) -> None:
    for filename in GENERATED_FILENAMES:
        path = output_dir / filename
        if path.exists():
            path.unlink()


def render_manifests(config: AppConfig, output_dir: Path) -> list[Path]:
    """Render MVP Kubernetes manifests into the output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_previous_generated_files(output_dir)

    environment = _template_environment()
    context = _context(config)
    written_files: list[Path] = []

    try:
        for spec in _template_specs(config):
            if not spec.enabled:
                continue
            template = environment.get_template(spec.template_name)
            rendered = template.render(context).rstrip() + "\n"
            output_path = output_dir / spec.output_name
            output_path.write_text(rendered, encoding="utf-8")
            written_files.append(output_path)
    except (OSError, TemplateError) as exc:
        msg = f"Unable to render manifests: {exc}"
        raise RenderError(msg) from exc

    return written_files
