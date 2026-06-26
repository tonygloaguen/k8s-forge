"""ArgoCD GitOps readiness file rendering."""

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
class GitOpsTemplateSpec:
    """Mapping between a GitOps template and generated output file."""

    template_name: str
    output_name: str


GENERATED_GITOPS_FILES = (
    "README.md",
    "argocd/application.yaml",
)


def resolve_gitops_application_name(config: AppConfig) -> str:
    """Return the ArgoCD Application name."""
    configured_name = config.gitops.application.name.strip()
    if configured_name:
        return configured_name
    return config.app.name


def resolve_gitops_destination_namespace(config: AppConfig) -> str:
    """Return the ArgoCD destination namespace."""
    configured_namespace = config.gitops.destination.namespace.strip()
    if configured_namespace:
        return configured_namespace
    return config.app.namespace


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("gitops_templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def _template_specs() -> list[GitOpsTemplateSpec]:
    return [
        GitOpsTemplateSpec("README.md.j2", "README.md"),
        GitOpsTemplateSpec("argocd/application.yaml.j2", "argocd/application.yaml"),
    ]


def _context(config: AppConfig) -> dict[str, Any]:
    return {
        "app": config.app,
        "gitops": config.gitops,
        "application_name": resolve_gitops_application_name(config),
        "destination_namespace": resolve_gitops_destination_namespace(config),
    }


def _check_existing_files(paths: list[Path], force: bool) -> None:
    if force:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing)
        msg = f"GitOps output file already exists, use --force to overwrite: {rendered}"
        raise RenderError(msg)


def render_gitops_files(
    config: AppConfig,
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Render ArgoCD GitOps readiness files into the output directory."""
    if not config.gitops.enabled:
        return []

    specs = _template_specs()
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
        msg = f"Unable to render GitOps files: {exc}"
        raise RenderError(msg) from exc

    return written_files
