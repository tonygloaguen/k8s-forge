"""Capstone readiness file rendering."""

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
class CapstoneTemplateSpec:
    """Mapping between a Capstone template and generated output file."""

    template_name: str
    output_name: str
    enabled: bool = True


@dataclass(frozen=True)
class CapstoneModuleSummary:
    """One row in the Capstone modules summary."""

    module: str
    version: str
    purpose: str
    generated_output: str
    runtime_dependency: str
    status: str


@dataclass(frozen=True)
class CapstoneChecklistItem:
    """One row in the final Capstone validation checklist."""

    control: str
    status: str
    evidence: str
    manual_action: str


@dataclass(frozen=True)
class CapstoneRuntimeDependency:
    """Runtime dependency description for the Capstone dossier."""

    name: str
    classification: str
    used_by: str
    note: str


GENERATED_CAPSTONE_FILES = (
    "README.md",
    "lab-summary.md",
    "architecture-overview.md",
    "devsecops-chain.md",
    "modules-summary.md",
    "validation-checklist.md",
    "manual-steps.md",
    "runtime-dependencies.md",
    "security-summary.md",
    "v1-readiness.md",
    "final-report-outline.md",
)


def resolve_capstone_project_name(config: AppConfig) -> str:
    """Return the Capstone project name."""
    configured_name = config.capstone.project_name.strip()
    if configured_name:
        return configured_name
    return config.app.name


def resolve_capstone_report_title(config: AppConfig) -> str:
    """Return the Capstone report title."""
    configured_title = config.capstone.report.title.strip()
    if configured_title:
        return configured_title
    return f"{config.app.name} DevSecOps Cloud-Native Lab"


def _enabled_state(enabled: bool) -> str:
    return "generated" if enabled else "manual"


def capstone_module_summaries(config: AppConfig) -> list[CapstoneModuleSummary]:
    """Build module summary rows for every readiness layer."""
    return [
        CapstoneModuleSummary(
            "Kubernetes raw",
            "v0.2.0",
            "Generate reviewable base manifests",
            "Namespace, ConfigMap, Secret placeholder, Deployment, Service, HPA",
            "Kubernetes cluster",
            "generated",
        ),
        CapstoneModuleSummary(
            "Helm",
            "v0.3.0",
            "Package the application as a local chart",
            "Chart.yaml, values.yaml, templates",
            "Helm CLI for manual validation",
            "generated",
        ),
        CapstoneModuleSummary(
            "Ingress / TLS",
            "v0.4.0",
            "Prepare HTTP routing and certificate readiness",
            "Ingress manifests and chart templates",
            "ingress-nginx and cert-manager",
            _enabled_state(config.ingress.enabled),
        ),
        CapstoneModuleSummary(
            "Linkerd",
            "v0.5.0",
            "Prepare service mesh injection metadata",
            "Deployment pod annotations",
            "Linkerd control plane",
            _enabled_state(config.mesh.enabled),
        ),
        CapstoneModuleSummary(
            "NetworkPolicy",
            "v0.6.0",
            "Prepare ingress-only network isolation",
            "NetworkPolicy manifest",
            "CNI with NetworkPolicy enforcement",
            _enabled_state(config.networkPolicy.enabled),
        ),
        CapstoneModuleSummary(
            "Kyverno",
            "v0.7.0",
            "Prepare admission policy visibility",
            "Namespace-scoped Kyverno Policy",
            "Kyverno installed in cluster",
            _enabled_state(config.policy.enabled),
        ),
        CapstoneModuleSummary(
            "Supply Chain",
            "v0.8.0",
            "Prepare image scan, SBOM, and signing commands",
            "Local scripts and README",
            "Trivy, Syft, optional Cosign",
            _enabled_state(config.supplyChain.enabled),
        ),
        CapstoneModuleSummary(
            "CI GitHub Actions",
            "v0.9.0",
            "Prepare automated quality and image checks",
            "GitHub Actions workflow examples",
            "GitHub repository and Actions runners",
            _enabled_state(config.ci.enabled),
        ),
        CapstoneModuleSummary(
            "GitOps ArgoCD",
            "v0.10.0",
            "Prepare ArgoCD Application delivery review",
            "ArgoCD Application manifest",
            "ArgoCD installed and connected to Git",
            _enabled_state(config.gitops.enabled),
        ),
        CapstoneModuleSummary(
            "Observability",
            "v0.11.0",
            "Prepare metrics scraping and dashboard review",
            "ServiceMonitor and Grafana dashboard JSON",
            "Prometheus Operator and Grafana",
            _enabled_state(config.observability.enabled),
        ),
        CapstoneModuleSummary(
            "Logging",
            "v0.12.0",
            "Prepare Loki log review examples",
            "LogQL examples, collector notes, dashboard JSON",
            "Loki, Grafana, and collector",
            _enabled_state(config.logging.enabled),
        ),
        CapstoneModuleSummary(
            "Tracing",
            "v0.13.0",
            "Prepare OpenTelemetry and Tempo trace examples",
            "OTEL notes, TraceQL examples, dashboard JSON",
            "Instrumented app, collector, Tempo, Grafana",
            _enabled_state(config.tracing.enabled),
        ),
        CapstoneModuleSummary(
            "Terraform",
            "v0.14.0",
            "Prepare Infrastructure as Code examples",
            "Local Terraform files",
            "Terraform CLI for manual workflows",
            _enabled_state(config.terraform.enabled),
        ),
        CapstoneModuleSummary(
            "Ansible",
            "v0.15.0",
            "Prepare automation examples",
            "Local Ansible files",
            "Ansible CLI for manual workflows",
            _enabled_state(config.ansible.enabled),
        ),
        CapstoneModuleSummary(
            "Security Audit",
            "v0.16.0",
            "Prepare local hardening review",
            "Markdown security audit dossier",
            "Manual review and existing readiness outputs",
            _enabled_state(config.security.enabled),
        ),
    ]


def capstone_checklist_items(config: AppConfig) -> list[CapstoneChecklistItem]:
    """Build final validation checklist rows."""
    return [
        CapstoneChecklistItem(
            "Kubernetes manifests",
            "ready",
            "k8s-forge render output",
            "Review generated YAML before any cluster workflow",
        ),
        CapstoneChecklistItem(
            "Helm chart",
            "generated",
            "helm render output",
            "Run manual chart linting when Helm is available",
        ),
        CapstoneChecklistItem(
            "Ingress and TLS",
            "requires runtime" if config.ingress.enabled else "manual",
            "ingress.enabled and ingress.tls.enabled",
            "Install and validate ingress controller and certificate workflow manually",
        ),
        CapstoneChecklistItem(
            "Network policy",
            "requires runtime" if config.networkPolicy.enabled else "manual",
            "networkPolicy.enabled",
            "Use a CNI that enforces NetworkPolicy",
        ),
        CapstoneChecklistItem(
            "Kyverno policies",
            "requires runtime" if config.policy.enabled else "manual",
            "policy.enabled",
            "Install Kyverno manually before relying on admission checks",
        ),
        CapstoneChecklistItem(
            "Supply chain review",
            "generated" if config.supplyChain.enabled else "manual",
            "supplyChain.enabled",
            "Run scan and SBOM steps manually from generated scripts",
        ),
        CapstoneChecklistItem(
            "CI workflows",
            "generated" if config.ci.enabled else "manual",
            "ci.enabled",
            "Copy workflows into the repository and review before committing",
        ),
        CapstoneChecklistItem(
            "GitOps delivery",
            "requires runtime" if config.gitops.enabled else "manual",
            "gitops.enabled",
            "Install and configure ArgoCD manually before sync",
        ),
        CapstoneChecklistItem(
            "Observability stack",
            "requires runtime" if config.observability.enabled else "manual",
            "observability.enabled",
            "Install Prometheus Operator and Grafana manually",
        ),
        CapstoneChecklistItem(
            "Security Audit readiness",
            "generated" if config.security.enabled else "manual",
            "security.enabled",
            "Review the generated Security Audit dossier",
        ),
        CapstoneChecklistItem(
            "Production deployment",
            "out of scope",
            "capstone scope",
            "Design a separate controlled release workflow for production",
        ),
    ]


def capstone_runtime_dependencies() -> list[CapstoneRuntimeDependency]:
    """Return runtime dependency descriptions for the Capstone dossier."""
    return [
        CapstoneRuntimeDependency(
            "Kubernetes cluster",
            "required",
            "raw manifests",
            "Runtime target for application objects",
        ),
        CapstoneRuntimeDependency(
            "ingress-nginx",
            "optional",
            "Ingress",
            "Required only for generated Ingress traffic routing",
        ),
        CapstoneRuntimeDependency(
            "cert-manager",
            "optional",
            "TLS",
            "Required only for certificate automation",
        ),
        CapstoneRuntimeDependency(
            "metrics-server",
            "optional",
            "HPA",
            "Required for CPU-based autoscaling decisions",
        ),
        CapstoneRuntimeDependency(
            "CNI compatible NetworkPolicy",
            "optional",
            "NetworkPolicy",
            "Required for network isolation enforcement",
        ),
        CapstoneRuntimeDependency(
            "Kyverno", "optional", "Policy", "Required for runtime admission review"
        ),
        CapstoneRuntimeDependency(
            "Linkerd", "optional", "Mesh", "Required for service mesh sidecar injection"
        ),
        CapstoneRuntimeDependency(
            "ArgoCD",
            "optional",
            "GitOps",
            "Required for Git-based application reconciliation",
        ),
        CapstoneRuntimeDependency(
            "Prometheus Operator",
            "optional",
            "Observability",
            "Required for ServiceMonitor resources",
        ),
        CapstoneRuntimeDependency(
            "Grafana",
            "optional",
            "Dashboards",
            "Required to import dashboard JSON manually",
        ),
        CapstoneRuntimeDependency(
            "Loki", "optional", "Logging", "Required to query application logs"
        ),
        CapstoneRuntimeDependency(
            "Tempo", "optional", "Tracing", "Required to query traces"
        ),
        CapstoneRuntimeDependency(
            "OpenTelemetry Collector",
            "optional",
            "Tracing",
            "Required to receive and export OTLP traces",
        ),
        CapstoneRuntimeDependency(
            "Trivy", "manual", "Supply Chain", "Used when manually scanning images"
        ),
        CapstoneRuntimeDependency(
            "Syft", "manual", "Supply Chain", "Used when manually generating SBOM files"
        ),
        CapstoneRuntimeDependency(
            "Cosign",
            "manual",
            "Supply Chain",
            "Optional signing and verification workflow",
        ),
        CapstoneRuntimeDependency(
            "Terraform",
            "manual",
            "IaC",
            "Used only in a manual workflow outside k8s-forge",
        ),
        CapstoneRuntimeDependency(
            "Ansible",
            "manual",
            "Automation",
            "Used only in a manual workflow outside k8s-forge",
        ),
    ]


def _template_environment() -> Environment:
    template_dir = Path(__file__).with_name("capstone_templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def _template_specs(config: AppConfig) -> list[CapstoneTemplateSpec]:
    return [
        CapstoneTemplateSpec("README.md.j2", "README.md"),
        CapstoneTemplateSpec("lab-summary.md.j2", "lab-summary.md"),
        CapstoneTemplateSpec(
            "architecture-overview.md.j2",
            "architecture-overview.md",
            enabled=config.capstone.architecture.enabled,
        ),
        CapstoneTemplateSpec(
            "devsecops-chain.md.j2",
            "devsecops-chain.md",
            enabled=config.capstone.devsecops_matrix.enabled,
        ),
        CapstoneTemplateSpec(
            "modules-summary.md.j2",
            "modules-summary.md",
            enabled=config.capstone.modules_summary.enabled,
        ),
        CapstoneTemplateSpec(
            "validation-checklist.md.j2",
            "validation-checklist.md",
            enabled=config.capstone.checklist.enabled,
        ),
        CapstoneTemplateSpec(
            "manual-steps.md.j2",
            "manual-steps.md",
            enabled=config.capstone.manual_steps.enabled,
        ),
        CapstoneTemplateSpec(
            "runtime-dependencies.md.j2",
            "runtime-dependencies.md",
            enabled=config.capstone.runtime_dependencies.enabled,
        ),
        CapstoneTemplateSpec(
            "security-summary.md.j2",
            "security-summary.md",
            enabled=config.capstone.security_summary.enabled,
        ),
        CapstoneTemplateSpec(
            "v1-readiness.md.j2",
            "v1-readiness.md",
            enabled=config.capstone.v1_readiness.enabled,
        ),
        CapstoneTemplateSpec(
            "final-report-outline.md.j2",
            "final-report-outline.md",
            enabled=config.capstone.examples.enabled,
        ),
    ]


def _context(config: AppConfig) -> dict[str, Any]:
    return {
        "app": config.app,
        "autoscaling": config.autoscaling,
        "capstone": config.capstone,
        "ci": config.ci,
        "gitops": config.gitops,
        "ingress": config.ingress,
        "logging": config.logging,
        "mesh": config.mesh,
        "network_policy": config.networkPolicy,
        "observability": config.observability,
        "policy": config.policy,
        "security": config.security,
        "supply_chain": config.supplyChain,
        "terraform": config.terraform,
        "ansible": config.ansible,
        "tracing": config.tracing,
        "project_name": resolve_capstone_project_name(config),
        "report_title": resolve_capstone_report_title(config),
        "module_summaries": capstone_module_summaries(config),
        "checklist_items": capstone_checklist_items(config),
        "runtime_dependencies": capstone_runtime_dependencies(),
    }


def _check_existing_files(paths: list[Path], force: bool) -> None:
    if force:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing)
        msg = (
            f"Capstone output file already exists, use --force to overwrite: {rendered}"
        )
        raise RenderError(msg)


def render_capstone_files(
    config: AppConfig,
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Render Capstone readiness files into the output directory."""
    if not config.capstone.enabled:
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
        msg = f"Unable to render Capstone files: {exc}"
        raise RenderError(msg) from exc

    return written_files
