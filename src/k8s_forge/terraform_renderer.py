"""Terraform readiness file rendering."""

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
class TerraformTemplateSpec:
    """Mapping between a Terraform template and generated output file."""

    template_name: str
    output_name: str
    enabled: bool = True


GENERATED_TERRAFORM_FILES = (
    "README.md",
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "main.tf",
    "outputs.tf",
)


def resolve_terraform_project_name(config: AppConfig) -> str:
    """Return the Terraform project name."""
    configured_name = config.terraform.project_name.strip()
    if configured_name:
        return configured_name
    return config.app.name


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("terraform_templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def _template_specs(config: AppConfig) -> list[TerraformTemplateSpec]:
    return [
        TerraformTemplateSpec("README.md.j2", "README.md"),
        TerraformTemplateSpec("versions.tf.j2", "versions.tf"),
        TerraformTemplateSpec("providers.tf.j2", "providers.tf"),
        TerraformTemplateSpec("variables.tf.j2", "variables.tf"),
        TerraformTemplateSpec(
            "main.tf.j2", "main.tf", enabled=config.terraform.examples.enabled
        ),
        TerraformTemplateSpec("outputs.tf.j2", "outputs.tf"),
    ]


def _context(config: AppConfig) -> dict[str, Any]:
    return {
        "app": config.app,
        "terraform": config.terraform,
        "project_name": resolve_terraform_project_name(config),
        "chart_path": f"charts-generated/{config.app.name}",
    }


def _check_existing_files(paths: list[Path], force: bool) -> None:
    if force:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing)
        msg = (
            "Terraform output file already exists, use --force to overwrite: "
            f"{rendered}"
        )
        raise RenderError(msg)


def render_terraform_files(
    config: AppConfig,
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Render Terraform readiness files into the output directory."""
    if not config.terraform.enabled:
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
        msg = f"Unable to render Terraform files: {exc}"
        raise RenderError(msg) from exc

    return written_files
