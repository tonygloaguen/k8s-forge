"""Ansible readiness file rendering."""

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
class AnsibleTemplateSpec:
    """Mapping between an Ansible template and generated output file."""

    template_name: str
    output_name: str
    enabled: bool = True


GENERATED_ANSIBLE_FILES = (
    "README.md",
    "ansible.cfg",
    "inventory.ini",
    "site.yml",
    "group_vars/all.yml",
    "roles/README.md",
)


def resolve_ansible_project_name(config: AppConfig) -> str:
    """Return the Ansible project name."""
    configured_name = config.ansible.project_name.strip()
    if configured_name:
        return configured_name
    return config.app.name


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("ansible_templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def _template_specs(config: AppConfig) -> list[AnsibleTemplateSpec]:
    return [
        AnsibleTemplateSpec("README.md.j2", "README.md"),
        AnsibleTemplateSpec("ansible.cfg.j2", "ansible.cfg"),
        AnsibleTemplateSpec("inventory.ini.j2", "inventory.ini"),
        AnsibleTemplateSpec(
            "site.yml.j2",
            config.ansible.playbook.name,
            enabled=config.ansible.examples.enabled,
        ),
        AnsibleTemplateSpec("group_vars/all.yml.j2", "group_vars/all.yml"),
        AnsibleTemplateSpec(
            "roles/README.md.j2",
            "roles/README.md",
            enabled=config.ansible.roles.enabled,
        ),
    ]


def _context(config: AppConfig) -> dict[str, Any]:
    return {
        "app": config.app,
        "ansible": config.ansible,
        "project_name": resolve_ansible_project_name(config),
        "manifest_path": "generated-k8s-forge-ansible",
        "chart_path": f"charts-generated/{config.app.name}",
    }


def _check_existing_files(paths: list[Path], force: bool) -> None:
    if force:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing)
        msg = (
            f"Ansible output file already exists, use --force to overwrite: {rendered}"
        )
        raise RenderError(msg)


def render_ansible_files(
    config: AppConfig,
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Render Ansible readiness files into the output directory."""
    if not config.ansible.enabled:
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
        msg = f"Unable to render Ansible files: {exc}"
        raise RenderError(msg) from exc

    return written_files
