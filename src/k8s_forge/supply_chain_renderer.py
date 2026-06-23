"""Supply chain readiness file rendering."""

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
class SupplyChainTemplateSpec:
    """Mapping between a supply chain template and generated output file."""

    template_name: str
    output_name: str
    enabled: bool = True
    executable: bool = False


GENERATED_SUPPLY_CHAIN_FILES = (
    "README.md",
    "scan-image.sh",
    "generate-sbom.sh",
    "sign-image.sh",
    "verify-image.sh",
)


def resolve_supply_chain_image(config: AppConfig) -> str:
    """Return the configured supply chain image or fall back to app.image."""
    configured_image = config.supplyChain.image.strip()
    if configured_image:
        return configured_image
    return config.app.image


def uses_latest_tag(image: str) -> bool:
    """Return True when an image reference uses the latest tag explicitly."""
    last_slash = image.rfind("/")
    last_colon = image.rfind(":")
    return last_colon > last_slash and image[last_colon + 1 :] == "latest"


def is_registry_backed_image(image: str) -> bool:
    """Return a conservative guess for whether an image includes a registry host."""
    if "/" not in image:
        return False
    first_segment = image.split("/", 1)[0]
    return "." in first_segment or ":" in first_segment or first_segment == "localhost"


def _sbom_output(format_name: str) -> str:
    outputs = {
        "cyclonedx-json": "reports/sbom.cdx.json",
        "spdx-json": "reports/sbom.spdx.json",
        "syft-json": "reports/sbom.syft.json",
    }
    return outputs[format_name]


def _severity_csv(config: AppConfig) -> str:
    return ",".join(config.supplyChain.scan.severity)


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("supply_chain_templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def _template_specs(config: AppConfig) -> list[SupplyChainTemplateSpec]:
    return [
        SupplyChainTemplateSpec("README.md.j2", "README.md"),
        SupplyChainTemplateSpec(
            "scan-image.sh.j2",
            "scan-image.sh",
            enabled=config.supplyChain.scan.enabled,
            executable=True,
        ),
        SupplyChainTemplateSpec(
            "generate-sbom.sh.j2",
            "generate-sbom.sh",
            enabled=config.supplyChain.sbom.enabled,
            executable=True,
        ),
        SupplyChainTemplateSpec(
            "sign-image.sh.j2",
            "sign-image.sh",
            enabled=config.supplyChain.signing.enabled,
            executable=True,
        ),
        SupplyChainTemplateSpec(
            "verify-image.sh.j2",
            "verify-image.sh",
            enabled=config.supplyChain.signing.enabled,
            executable=True,
        ),
    ]


def _context(config: AppConfig) -> dict[str, Any]:
    image = resolve_supply_chain_image(config)
    return {
        "app": config.app,
        "supplyChain": config.supplyChain,
        "image": image,
        "severity_csv": _severity_csv(config),
        "sbom_output": _sbom_output(config.supplyChain.sbom.format),
        "uses_latest": uses_latest_tag(image),
        "registry_backed": is_registry_backed_image(image),
    }


def _clear_previous_generated_files(output_dir: Path) -> None:
    for filename in GENERATED_SUPPLY_CHAIN_FILES:
        path = output_dir / filename
        if path.exists():
            path.unlink()


def render_supply_chain_files(config: AppConfig, output_dir: Path) -> list[Path]:
    """Render supply chain readiness files into the output directory."""
    if not config.supplyChain.enabled:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "reports").mkdir(parents=True, exist_ok=True)
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
            if spec.executable:
                output_path.chmod(0o755)
            written_files.append(output_path)
    except (OSError, TemplateError) as exc:
        msg = f"Unable to render supply chain files: {exc}"
        raise RenderError(msg) from exc

    return written_files
