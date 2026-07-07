"""Repository discovery readiness rendering."""

from dataclasses import dataclass
from pathlib import Path

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateError,
    select_autoescape,
)

from k8s_forge.discovery import RepositoryDiscoveryResult
from k8s_forge.exceptions import RenderError


@dataclass(frozen=True)
class DiscoveryTemplateSpec:
    """Mapping between a discovery template and output file."""

    template_name: str
    output_name: str
    enabled: bool = True


GENERATED_DISCOVERY_FILES = (
    "discovery-report.md",
    "warnings.md",
    "k8s-forge-app.yaml",
)


def render_discovery_files(
    result: RepositoryDiscoveryResult,
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Render local repository discovery files."""
    specs = _template_specs(result)
    if not force:
        for spec in specs:
            target = output_dir / spec.output_name
            if target.exists():
                msg = f"{target} already exists, use --force to overwrite"
                raise RenderError(msg)

    environment = _template_environment()
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for spec in specs:
        target = output_dir / spec.output_name
        try:
            template = environment.get_template(spec.template_name)
            rendered = template.render(result=result)
        except TemplateError as exc:
            msg = f"Failed to render discovery template {spec.template_name}: {exc}"
            raise RenderError(msg) from exc
        target.write_text(rendered.rstrip() + "\n", encoding="utf-8")
        generated.append(target)
    return generated


def _template_specs(result: RepositoryDiscoveryResult) -> list[DiscoveryTemplateSpec]:
    specs = [
        DiscoveryTemplateSpec("discovery-report.md.j2", "discovery-report.md"),
        DiscoveryTemplateSpec("warnings.md.j2", "warnings.md"),
    ]
    if result.yaml_generated:
        specs.append(
            DiscoveryTemplateSpec("k8s-forge-app.yaml.j2", "k8s-forge-app.yaml")
        )
    return specs


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("discovery_templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )
