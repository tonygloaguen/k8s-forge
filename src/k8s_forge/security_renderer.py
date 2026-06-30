"""Security Audit readiness file rendering."""

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
class SecurityTemplateSpec:
    """Mapping between a Security Audit template and generated output file."""

    template_name: str
    output_name: str
    enabled: bool = True


@dataclass(frozen=True)
class SecurityChecklistItem:
    """One row in the generated security checklist."""

    control: str
    status: str
    source: str
    risk: str
    recommended_action: str


GENERATED_SECURITY_FILES = (
    "README.md",
    "container-security.md",
    "kubernetes-manifest-audit.md",
    "rbac-audit.md",
    "pod-security-audit.md",
    "network-security-audit.md",
    "secrets-audit.md",
    "supply-chain-security.md",
    "final-security-checklist.md",
)


def resolve_security_project_name(config: AppConfig) -> str:
    """Return the Security Audit project name."""
    configured_name = config.security.project_name.strip()
    if configured_name:
        return configured_name
    return config.app.name


def image_tag_status(config: AppConfig) -> str:
    """Return a human-readable image tag assessment."""
    if uses_latest_tag(config.app.image):
        return "warning: mutable latest tag"
    if ":" not in config.app.image and "@" not in config.app.image:
        return "manual: image tag not explicit"
    return "ok: stable-looking tag or digest"


def _resources_defined(config: AppConfig) -> bool:
    requests = config.resources.requests
    limits = config.resources.limits
    return any((requests.cpu, requests.memory, limits.cpu, limits.memory))


def _probes_defined(config: AppConfig) -> bool:
    return bool(config.probes.liveness and config.probes.readiness)


def _status(enabled: bool) -> str:
    return "ok" if enabled else "not enabled"


def security_checklist_items(config: AppConfig) -> list[SecurityChecklistItem]:
    """Build the local educational security checklist rows."""
    image_status = "warning" if uses_latest_tag(config.app.image) else "ok"
    explicit_tag = ":" in config.app.image or "@" in config.app.image
    if not explicit_tag:
        image_status = "manual"

    return [
        SecurityChecklistItem(
            "Image tag stable",
            image_status,
            "app.image",
            "Mutable or implicit image references weaken traceability",
            "Use an immutable version tag or image digest",
        ),
        SecurityChecklistItem(
            "Container resources",
            "ok" if _resources_defined(config) else "warning",
            "resources",
            "Missing limits can hide noisy neighbor and capacity issues",
            "Define CPU and memory requests and limits",
        ),
        SecurityChecklistItem(
            "Health probes",
            "ok" if _probes_defined(config) else "warning",
            "probes",
            "Missing probes can delay failure detection",
            "Define readiness and liveness HTTP probes",
        ),
        SecurityChecklistItem(
            "NetworkPolicy",
            _status(config.networkPolicy.enabled),
            "networkPolicy.enabled",
            "Unrestricted pod traffic increases lateral movement risk",
            "Keep a least-privilege ingress profile and review egress later",
        ),
        SecurityChecklistItem(
            "Ingress TLS",
            "ok" if config.ingress.enabled and config.ingress.tls.enabled else "manual",
            "ingress.tls.enabled",
            "Plain HTTP exposure is weak for real environments",
            "Use TLS and validate ingress controller plus certificate workflow",
        ),
        SecurityChecklistItem(
            "Kyverno policies",
            _status(config.policy.enabled),
            "policy.enabled",
            "Policies are only useful at runtime after the controller exists",
            "Install Kyverno manually before relying on admission checks",
        ),
        SecurityChecklistItem(
            "RBAC review",
            "manual",
            "generated manifests",
            "Broad permissions can expose namespaces and sensitive resources",
            "Review ServiceAccounts, RoleBindings, and least-privilege scope",
        ),
        SecurityChecklistItem(
            "Secrets handling",
            "manual",
            "generated manifests",
            "Sensitive values need external lifecycle and encryption decisions",
            "Use an external manager for real sensitive configuration",
        ),
        SecurityChecklistItem(
            "Supply chain readiness",
            _status(config.supplyChain.enabled),
            "supplyChain.enabled",
            "Image provenance and dependency visibility need explicit workflow",
            "Generate local scan and SBOM scripts, then run them manually",
        ),
        SecurityChecklistItem(
            "CI security workflow",
            _status(config.ci.enabled and config.ci.container.enabled),
            "ci.container.enabled",
            "Manual-only review can miss regressions",
            "Generate CI security workflow examples and review artifacts",
        ),
    ]


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("security_templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def _template_specs(config: AppConfig) -> list[SecurityTemplateSpec]:
    return [
        SecurityTemplateSpec("README.md.j2", "README.md"),
        SecurityTemplateSpec(
            "container-security.md.j2",
            "container-security.md",
            enabled=config.security.container.enabled,
        ),
        SecurityTemplateSpec(
            "kubernetes-manifest-audit.md.j2",
            "kubernetes-manifest-audit.md",
            enabled=config.security.manifests.enabled,
        ),
        SecurityTemplateSpec(
            "rbac-audit.md.j2",
            "rbac-audit.md",
            enabled=config.security.rbac.enabled,
        ),
        SecurityTemplateSpec(
            "pod-security-audit.md.j2",
            "pod-security-audit.md",
            enabled=config.security.pod_security.enabled,
        ),
        SecurityTemplateSpec(
            "network-security-audit.md.j2",
            "network-security-audit.md",
            enabled=config.security.network.enabled,
        ),
        SecurityTemplateSpec(
            "secrets-audit.md.j2",
            "secrets-audit.md",
            enabled=config.security.secrets.enabled,
        ),
        SecurityTemplateSpec(
            "supply-chain-security.md.j2",
            "supply-chain-security.md",
            enabled=config.security.supply_chain.enabled,
        ),
        SecurityTemplateSpec(
            "final-security-checklist.md.j2",
            "final-security-checklist.md",
            enabled=config.security.checklist.enabled,
        ),
    ]


def _context(config: AppConfig) -> dict[str, Any]:
    return {
        "app": config.app,
        "autoscaling": config.autoscaling,
        "ci": config.ci,
        "ingress": config.ingress,
        "network_policy": config.networkPolicy,
        "policy": config.policy,
        "service": config.service,
        "resources_defined": _resources_defined(config),
        "probes_defined": _probes_defined(config),
        "security": config.security,
        "supply_chain": config.supplyChain,
        "project_name": resolve_security_project_name(config),
        "image_tag_status": image_tag_status(config),
        "checklist_items": security_checklist_items(config),
    }


def _check_existing_files(paths: list[Path], force: bool) -> None:
    if force:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing)
        msg = (
            "Security Audit output file already exists, use --force to overwrite: "
            f"{rendered}"
        )
        raise RenderError(msg)


def render_security_files(
    config: AppConfig,
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Render Security Audit readiness files into the output directory."""
    if not config.security.enabled:
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
        msg = f"Unable to render Security Audit files: {exc}"
        raise RenderError(msg) from exc

    return written_files
