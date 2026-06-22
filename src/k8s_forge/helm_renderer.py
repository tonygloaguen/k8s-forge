"""Helm chart rendering entry points."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
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
class HelmTemplateSpec:
    """Mapping between a Helm template source and its generated output file."""

    template_name: str
    output_name: str


GENERATED_HELM_FILES = (
    "Chart.yaml",
    "values.yaml",
    "templates/_helpers.tpl",
    "templates/configmap.yaml",
    "templates/secret.yaml",
    "templates/deployment.yaml",
    "templates/service.yaml",
    "templates/hpa.yaml",
)


def split_image(image: str) -> tuple[str, str]:
    """Split a container image into repository and tag."""
    last_slash = image.rfind("/")
    last_colon = image.rfind(":")
    if last_colon > last_slash:
        return image[:last_colon], image[last_colon + 1 :]
    return image, "latest"


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("helm_templates")
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
        variable_start_string="[[",
        variable_end_string="]]",
        block_start_string="[%",
        block_end_string="%]",
        comment_start_string="[#",
        comment_end_string="#]",
    )
    environment.filters["yaml_scalar"] = _yaml_scalar
    return environment


def _yaml_scalar(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    rendered = yaml.safe_dump(value, default_flow_style=True, sort_keys=False)
    return rendered.strip().removesuffix("\n...")


def _template_specs() -> list[HelmTemplateSpec]:
    return [
        HelmTemplateSpec("Chart.yaml.j2", "Chart.yaml"),
        HelmTemplateSpec("values.yaml.j2", "values.yaml"),
        HelmTemplateSpec("templates/_helpers.tpl.j2", "templates/_helpers.tpl"),
        HelmTemplateSpec("templates/configmap.yaml.j2", "templates/configmap.yaml"),
        HelmTemplateSpec("templates/secret.yaml.j2", "templates/secret.yaml"),
        HelmTemplateSpec("templates/deployment.yaml.j2", "templates/deployment.yaml"),
        HelmTemplateSpec("templates/service.yaml.j2", "templates/service.yaml"),
        HelmTemplateSpec("templates/hpa.yaml.j2", "templates/hpa.yaml"),
    ]


def _clear_previous_generated_files(chart_dir: Path) -> None:
    for filename in GENERATED_HELM_FILES:
        path = chart_dir / filename
        if path.exists():
            path.unlink()


def _values_context(config: AppConfig) -> dict[str, Any]:
    image_repository, image_tag = split_image(config.app.image)
    return {
        "replica_count": config.app.replicas,
        "image_repository": image_repository,
        "image_tag": image_tag,
        "service_enabled": config.service.enabled,
        "service_port": config.service.port,
        "service_target_port": config.app.containerPort,
        "config": config.config,
        "secrets_enabled": bool(config.secrets),
        "secrets": config.secrets,
        "resources": config.resources.model_dump(exclude_none=True),
        "probes": config.probes,
        "autoscaling": config.autoscaling,
        "ingress": config.ingress,
    }


def _context(config: AppConfig, chart_name: str) -> dict[str, Any]:
    image_repository, image_tag = split_image(config.app.image)
    return {
        "app": config.app,
        "app_name": config.app.name,
        "chart_name": chart_name,
        "image_repository": image_repository,
        "image_tag": image_tag,
        "values": _values_context(config),
    }


def render_helm_chart(
    config: AppConfig,
    output_dir: Path,
    chart_name: str | None = None,
) -> list[Path]:
    """Render a local Helm chart from an application configuration."""
    resolved_chart_name = chart_name or config.app.name
    chart_dir = output_dir / resolved_chart_name
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "templates").mkdir(parents=True, exist_ok=True)
    _clear_previous_generated_files(chart_dir)

    environment = _template_environment()
    context = _context(config, resolved_chart_name)
    written_files: list[Path] = []

    try:
        for spec in _template_specs():
            template = environment.get_template(spec.template_name)
            rendered = template.render(context).rstrip() + "\n"
            output_path = chart_dir / spec.output_name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
            written_files.append(output_path)
    except (OSError, TemplateError) as exc:
        msg = f"Unable to render Helm chart: {exc}"
        raise RenderError(msg) from exc

    return written_files
