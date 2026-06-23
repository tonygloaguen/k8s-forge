"""GitHub Actions CI readiness file rendering."""

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
from k8s_forge.supply_chain_renderer import uses_latest_tag


@dataclass(frozen=True)
class CiTemplateSpec:
    """Mapping between a CI template and generated output file."""

    template_name: str
    output_name: str
    enabled: bool = True


GENERATED_CI_FILES = (
    "README.md",
    ".github/workflows/ci.yml",
    ".github/workflows/security.yml",
)

DIRECT_WORKFLOW_README = "README.k8s-forge-ci.md"


def resolve_ci_image(config: AppConfig) -> str:
    """Return the CI container image using the configured fallback order."""
    ci_image = config.ci.container.image.strip()
    if ci_image:
        return ci_image
    supply_chain_image = config.supplyChain.image.strip()
    if supply_chain_image:
        return supply_chain_image
    return config.app.image


def _sbom_output(format_name: str) -> str:
    outputs = {
        "cyclonedx-json": "reports/sbom.cdx.json",
        "spdx-json": "reports/sbom.spdx.json",
        "syft-json": "reports/sbom.syft.json",
    }
    return outputs[format_name]


def _severity_csv(config: AppConfig) -> str:
    return ",".join(config.ci.container.scan.severity)


def _is_direct_workflow_output(output_dir: Path) -> bool:
    return output_dir.name == "workflows" and output_dir.parent.name == ".github"


def _output_path(output_dir: Path, output_name: str) -> Path:
    if not _is_direct_workflow_output(output_dir):
        return output_dir / output_name
    if output_name == "README.md":
        return output_dir / DIRECT_WORKFLOW_README
    prefix = ".github/workflows/"
    if output_name.startswith(prefix):
        return output_dir / output_name.removeprefix(prefix)
    return output_dir / output_name


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("ci_templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def _template_specs(config: AppConfig) -> list[CiTemplateSpec]:
    return [
        CiTemplateSpec("README.md.j2", "README.md"),
        CiTemplateSpec(
            "workflows/ci.yml.j2",
            ".github/workflows/ci.yml",
            enabled=config.ci.python.enabled,
        ),
        CiTemplateSpec(
            "workflows/security.yml.j2",
            ".github/workflows/security.yml",
            enabled=config.ci.container.enabled,
        ),
    ]


def _context(config: AppConfig) -> dict[str, Any]:
    image = resolve_ci_image(config)
    return {
        "app": config.app,
        "ci": config.ci,
        "image": image,
        "severity_csv": _severity_csv(config),
        "sbom_output": _sbom_output(config.ci.container.sbom.format),
        "uses_latest": uses_latest_tag(image),
    }


def _check_existing_files(paths: list[Path], force: bool) -> None:
    if force:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing)
        msg = f"CI output file already exists, use --force to overwrite: {rendered}"
        raise RenderError(msg)


def render_ci_files(
    config: AppConfig,
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Render GitHub Actions CI readiness files into the output directory."""
    if not config.ci.enabled:
        return []

    specs = [spec for spec in _template_specs(config) if spec.enabled]
    output_paths = [_output_path(output_dir, spec.output_name) for spec in specs]
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
        msg = f"Unable to render CI files: {exc}"
        raise RenderError(msg) from exc

    return written_files
