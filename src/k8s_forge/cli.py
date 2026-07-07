"""Command line interface for k8s-forge."""

from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from k8s_forge import __version__
from k8s_forge.ansible_renderer import (
    render_ansible_files,
    resolve_ansible_project_name,
)
from k8s_forge.capstone_renderer import (
    render_capstone_files,
    resolve_capstone_project_name,
    resolve_capstone_report_title,
)
from k8s_forge.ci_renderer import render_ci_files, resolve_ci_image
from k8s_forge.config_loader import load_app_config
from k8s_forge.discovery import DiscoveryError, discover_repository
from k8s_forge.discovery_renderer import render_discovery_files
from k8s_forge.exceptions import (
    ConfigLoadError,
    KubectlError,
    LocalCommandError,
    RenderError,
)
from k8s_forge.explain import build_explanation
from k8s_forge.explain_renderer import render_explanation
from k8s_forge.gitops_renderer import (
    render_gitops_files,
    resolve_gitops_application_name,
    resolve_gitops_destination_namespace,
)
from k8s_forge.helm_renderer import render_helm_chart
from k8s_forge.kubectl import KubectlResult, run_kubectl
from k8s_forge.local_cluster import (
    DoctorReport,
    LocalCommandResult,
    ToolCheck,
    check_environment,
    create_kind_cluster,
    current_context,
    delete_kind_cluster,
    docker_image_inspect,
    get_kind_clusters,
    get_nodes,
    load_docker_image,
    wait_for_nodes_ready,
)
from k8s_forge.logging_renderer import (
    render_logging_files,
    resolve_logging_dashboard_title,
)
from k8s_forge.models import AppConfig
from k8s_forge.observability_renderer import (
    render_observability_files,
    resolve_dashboard_title,
    resolve_service_monitor_namespace,
)
from k8s_forge.renderer import render_manifests
from k8s_forge.security_renderer import (
    render_security_files,
    resolve_security_project_name,
)
from k8s_forge.studio.server import (
    StudioDependencyError,
    StudioHostError,
    run_studio,
)
from k8s_forge.supply_chain_renderer import (
    is_registry_backed_image,
    render_supply_chain_files,
    resolve_supply_chain_image,
    uses_latest_tag,
)
from k8s_forge.terraform_renderer import (
    render_terraform_files,
    resolve_terraform_project_name,
)
from k8s_forge.tracing_renderer import (
    render_tracing_files,
    resolve_tracing_dashboard_title,
    resolve_tracing_service_name,
)

app = typer.Typer(
    help="Generic Kubernetes manifest generator for stateless web applications.",
    no_args_is_help=True,
)
console = Console()
cluster_app = typer.Typer(help="Manage local kind clusters.")
image_app = typer.Typer(help="Manage local images for kind clusters.")
helm_app = typer.Typer(help="Generate local Helm charts.")
supply_chain_app = typer.Typer(help="Generate supply chain readiness scripts.")
ci_app = typer.Typer(help="Generate GitHub Actions CI readiness workflows.")
gitops_app = typer.Typer(help="Generate ArgoCD GitOps readiness manifests.")
observability_app = typer.Typer(help="Generate observability readiness files.")
logging_app = typer.Typer(help="Generate logging readiness files.")
tracing_app = typer.Typer(help="Generate tracing readiness files.")
terraform_app = typer.Typer(help="Generate Terraform readiness files.")
ansible_app = typer.Typer(help="Generate Ansible readiness files.")
security_app = typer.Typer(help="Generate Security Audit readiness files.")
capstone_app = typer.Typer(help="Generate Capstone readiness files.")


class _QuotedString(str):
    """String rendered with double quotes in starter YAML."""


class _InitConfigDumper(yaml.SafeDumper):
    """YAML dumper for starter configuration files."""


def _quoted_string_representer(
    dumper: yaml.SafeDumper, data: _QuotedString
) -> yaml.nodes.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')


_InitConfigDumper.add_representer(_QuotedString, _quoted_string_representer)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"k8s-forge {__version__}")
        raise typer.Exit


def _print_step(message: str) -> None:
    console.print(f"[bold]{message}[/bold]")


def _print_hint(message: str) -> None:
    console.print(message)


def _print_warning(message: str) -> None:
    console.print(f"[yellow]{message}[/yellow]")


def _service_state(config: AppConfig) -> str:
    if config.service.enabled:
        return f"enabled on port {config.service.port}"
    return "disabled"


def _autoscaling_state(config: AppConfig) -> str:
    if not config.autoscaling.enabled:
        return "disabled"
    return (
        "enabled "
        f"min={config.autoscaling.minReplicas} "
        f"max={config.autoscaling.maxReplicas} "
        f"cpu={config.autoscaling.targetCPUUtilizationPercentage}%"
    )


def _autoscaling_warning(config: AppConfig) -> str | None:
    if (
        config.autoscaling.enabled
        and config.app.replicas < config.autoscaling.minReplicas
    ):
        return (
            "Warning: Deployment replicas is lower than HPA minReplicas. "
            "Kubernetes will initially create the Deployment value, then the HPA "
            "may reconcile it back to its minimum once metrics are available."
        )
    return None


def _print_autoscaling_warning(config: AppConfig) -> None:
    warning = _autoscaling_warning(config)
    if warning:
        _print_warning(warning)


def _print_autoscaling_summary(config: AppConfig) -> None:
    if not config.autoscaling.enabled:
        return
    _print_hint("Autoscaling is enabled.")
    _print_hint(
        "The Deployment will start with "
        f"{config.app.replicas} replicas, and the HPA will be allowed to scale "
        f"between {config.autoscaling.minReplicas} and "
        f"{config.autoscaling.maxReplicas} pods based on CPU usage."
    )


def _print_hpa_runtime_hint(config: AppConfig) -> None:
    if not config.autoscaling.enabled:
        return
    _print_hint("Autoscaling is enabled, so an HPA manifest will be generated.")
    _print_hint("The HPA requires metrics-server to calculate CPU usage at runtime.")


def _print_ingress_summary(config: AppConfig) -> None:
    if not config.ingress.enabled:
        return
    _print_hint("Ingress is enabled.")
    _print_hint(
        "Kubernetes will route HTTP traffic for host "
        f"{config.ingress.host} to the Service."
    )
    _print_hint("Ingress requires an ingress controller such as ingress-nginx.")
    if config.ingress.tls.enabled:
        _print_hint("TLS is enabled for this Ingress.")
        _print_hint(
            "cert-manager can issue or prepare the certificate only if a "
            "matching ClusterIssuer exists."
        )


def _print_ingress_runtime_hint(config: AppConfig) -> None:
    if not config.ingress.enabled:
        return
    _print_hint("Ingress is enabled, so an Ingress manifest will be generated.")
    _print_hint(
        "This exposes the Service through an HTTP host rule, but it still "
        "requires ingress-nginx in the cluster."
    )
    _print_local_ingress_hints(config)


def _print_helm_ingress_hint(config: AppConfig) -> None:
    if not config.ingress.enabled:
        return
    _print_hint("The Helm chart includes an optional Ingress template.")
    _print_hint("Helm will not install ingress-nginx or cert-manager.")
    _print_hint("Validate those prerequisites separately.")
    _print_local_ingress_hints(config)


def _print_local_ingress_hints(config: AppConfig) -> None:
    if not config.ingress.host:
        return
    _print_hint("For local testing, map the host to localhost:")
    _print_hint(f"127.0.0.1 {config.ingress.host}")
    _print_warning(
        "On kind, ports 80 and 443 must be exposed by the cluster "
        "configuration for direct local ingress access."
    )
    _print_hint(
        "If they are not exposed, use port-forwarding or recreate the lab "
        "cluster with extraPortMappings."
    )


def _print_mesh_summary(config: AppConfig) -> None:
    if not config.mesh.enabled:
        return
    _print_hint("Service mesh support is enabled.")
    _print_hint(
        "A service mesh adds a sidecar proxy next to your application container."
    )
    _print_hint(
        "With Linkerd, injected pods usually show 2/2 containers: app + linkerd-proxy."
    )
    if config.mesh.inject:
        _print_hint("Linkerd injection is enabled for this workload.")
        _print_hint(
            "The generated Deployment includes the annotation "
            "linkerd.io/inject: enabled."
        )
        _print_hint(
            "After apply or helm upgrade, restart/rollout the Deployment and "
            "verify pods show 2/2 containers."
        )


def _print_mesh_validation_commands(namespace: str) -> None:
    _print_hint("Mesh validation commands:")
    _print_hint("  linkerd check")
    _print_hint(f"  kubectl -n {namespace} get pods")
    _print_hint(f"  kubectl -n {namespace} describe pod <pod>")
    _print_hint(f"  linkerd stat deploy -n {namespace}")


def _print_mesh_runtime_hint(config: AppConfig) -> None:
    if not config.mesh.enabled:
        return
    _print_mesh_summary(config)
    _print_hint("k8s-forge does not install Linkerd and does not run linkerd inject.")
    _print_mesh_validation_commands(config.app.namespace)


def _network_policy_name(config: AppConfig) -> str:
    return f"{config.app.name}-ingress-only"


def _print_network_policy_summary(config: AppConfig) -> None:
    if not config.networkPolicy.enabled:
        return
    _print_hint("NetworkPolicy support is enabled.")
    _print_hint(
        "A NetworkPolicy restricts which traffic is allowed to reach selected pods."
    )
    _print_hint(
        "This manifest is useful only if the cluster CNI enforces NetworkPolicy."
    )
    if config.networkPolicy.profile == "ingress-only":
        _print_hint(
            "The ingress-only profile allows traffic to the application pods "
            "from the ingress-nginx namespace."
        )
        _print_hint(
            "This keeps the application reachable through Ingress while "
            "reducing direct pod-to-pod exposure."
        )
    if not config.ingress.enabled:
        _print_warning(
            "networkPolicy.profile is ingress-only, but ingress.enabled is false. "
            "The policy can still be rendered, but the expected lab path uses Ingress."
        )


def _print_network_policy_cni_warning() -> None:
    _print_warning("NetworkPolicy enforcement depends on the CNI plugin.")
    _print_hint("Some local kind clusters do not enforce NetworkPolicy by default.")
    _print_hint(
        "k8s-forge generates the policy but does not install or replace the CNI."
    )


def _print_network_policy_validation_commands(config: AppConfig) -> None:
    namespace = config.app.namespace
    policy_name = _network_policy_name(config)
    _print_hint("NetworkPolicy validation commands:")
    _print_hint(f"  kubectl -n {namespace} get networkpolicy")
    _print_hint(f"  kubectl -n {namespace} describe networkpolicy {policy_name}")
    _print_hint(f"  kubectl -n {namespace} get pods")
    host = config.ingress.host or "weather.local"
    _print_hint(
        f"  curl -k --resolve {host}:8443:127.0.0.1 https://{host}:8443/weather"
    )


def _print_network_policy_runtime_hint(config: AppConfig) -> None:
    if not config.networkPolicy.enabled:
        return
    _print_network_policy_summary(config)
    _print_network_policy_cni_warning()
    _print_network_policy_validation_commands(config)


def _cni_summary(details: str) -> str:
    normalized = details.lower()
    if "calico" in normalized:
        return "calico"
    if "cilium" in normalized:
        return "cilium"
    if "kindnet" in normalized or "kind-net" in normalized:
        return "kindnet"
    if "flannel" in normalized:
        return "flannel"
    if details.strip():
        return "unknown"
    return "unavailable"


def _print_supply_chain_diagnostics(report: DoctorReport) -> None:
    _print_step("Checking supply chain tooling...")
    _print_hint("Trivy can scan images for known vulnerabilities.")
    _print_hint("Syft can generate SBOM files.")
    _print_hint("Cosign can sign and verify images.")
    if (
        report.trivy.status == "OK"
        and report.syft.status == "OK"
        and report.cosign.status == "OK"
    ):
        console.print("[green]Supply chain tools detected.[/green]")
    if report.trivy.status != "OK":
        _print_warning(
            "Trivy is not installed. Image vulnerability scans are not available yet."
        )
    if report.syft.status != "OK":
        _print_warning("Syft is not installed. SBOM generation is not available yet.")
    if report.cosign.status != "OK":
        _print_warning(
            "Cosign is not installed. Image signing and verification are not "
            "available yet."
        )


def _print_kyverno_diagnostics(report: DoctorReport) -> None:
    _print_step("Checking Kyverno policy readiness...")
    if (
        report.kyverno_namespace.status == "OK"
        and report.kyverno_deployments.status == "OK"
        and report.kyverno_crds.status == "OK"
    ):
        console.print("[green]Kyverno appears to be installed.[/green]")
        _print_hint(
            "Generated policies can be applied and observed through PolicyReports."
        )
    else:
        _print_warning("Kyverno does not appear to be installed in this cluster.")
        _print_hint("k8s-forge will not install it automatically.")
        _print_hint(
            "Generated policies can be reviewed locally, but the cluster will "
            "audit or enforce them only after Kyverno is installed."
        )
    if report.policy_reports.status == "OK":
        _print_hint("PolicyReports are available in the cluster.")
    else:
        _print_hint("PolicyReports are not available yet or no reports were found.")


def _print_cni_diagnostics(report: DoctorReport) -> None:
    _print_step("Checking NetworkPolicy and CNI readiness...")
    _print_network_policy_cni_warning()
    cni = _cni_summary(
        report.cni_pods.details if report.cni_pods.status == "OK" else ""
    )
    if cni in {"calico", "cilium"}:
        console.print(
            f"[green]A NetworkPolicy-capable CNI appears to be present ({cni}).[/green]"
        )
    elif cni in {"kindnet", "flannel"}:
        _print_warning(
            f"Detected {cni}; NetworkPolicy enforcement may be unavailable or limited."
        )
    else:
        _print_warning("Could not identify a NetworkPolicy-enforcing CNI.")
    _print_hint(
        "The presence of a NetworkPolicy object does not prove that traffic is "
        "actually enforced by the cluster network plugin."
    )


def _policy_name(config: AppConfig) -> str:
    return f"{config.app.name}-baseline"


def _print_kyverno_prerequisite_warning() -> None:
    _print_warning("k8s-forge generates Kyverno policies but does not install Kyverno.")
    _print_hint(
        "Install and validate Kyverno manually before expecting policy reports."
    )


def _print_policy_mode_hint(config: AppConfig) -> None:
    if config.policy.validationFailureAction == "Audit":
        _print_hint("The generated Kyverno policy uses Audit mode.")
        _print_hint("Violations are reported by Kyverno but resources are not blocked.")
        _print_hint("Use Enforce only after validating the policy impact.")
        return
    _print_warning("The generated Kyverno policy uses Enforce mode.")
    _print_hint("Resources that violate the policy may be rejected by the cluster.")
    _print_hint("Use this only after validating the policy in Audit mode.")


def _print_policy_summary(config: AppConfig) -> None:
    if not config.policy.enabled:
        return
    _print_hint("Kyverno policy support is enabled.")
    _print_hint(
        "Kyverno is an admission controller that can validate Kubernetes "
        "resources before they are accepted by the cluster."
    )
    _print_hint(
        "This profile generates audit-mode policies by default so the lab can "
        "observe compliance without blocking deployments."
    )
    _print_policy_mode_hint(config)


def _print_policy_validation_commands(config: AppConfig) -> None:
    namespace = config.app.namespace
    policy_name = _policy_name(config)
    _print_hint("Kyverno validation commands:")
    _print_hint(f"  kubectl -n {namespace} get policy")
    _print_hint(f"  kubectl -n {namespace} describe policy {policy_name}")
    _print_hint("  kubectl -n kyverno get pods")
    _print_hint("  kubectl get policyreport -A")


def _print_policy_runtime_hint(config: AppConfig) -> None:
    if not config.policy.enabled:
        return
    _print_policy_summary(config)
    _print_kyverno_prerequisite_warning()
    _print_policy_validation_commands(config)


def _print_supply_chain_latest_warning(image: str) -> None:
    if uses_latest_tag(image):
        _print_warning("The selected image uses the latest tag.")
        _print_hint("This is convenient for labs but weak for traceability.")
        _print_hint(
            "Prefer immutable version tags or digests for supply-chain validation."
        )


def _print_supply_chain_signing_warning(config: AppConfig, image: str) -> None:
    if not config.supplyChain.signing.enabled:
        return
    _print_hint(
        "Cosign can sign and verify images, but signing requires a "
        "registry-compatible image reference and a keyless or key-based workflow."
    )
    if not is_registry_backed_image(image):
        _print_warning(
            "Cosign signing usually requires a registry-backed image reference."
        )
        _print_hint(
            "Local-only images may not be suitable for signing and verification."
        )


def _print_supply_chain_summary(config: AppConfig) -> None:
    if not config.supplyChain.enabled:
        return
    image = resolve_supply_chain_image(config)
    _print_hint("Supply chain readiness is enabled.")
    _print_hint(
        "This prepares image scanning, SBOM generation, and optional signing commands."
    )
    _print_hint("k8s-forge does not install Trivy, Syft, or Cosign automatically.")
    _print_hint(f"Supply chain image: {image}")
    if config.supplyChain.scan.enabled:
        _print_hint("Trivy can scan the container image for known vulnerabilities.")
        _print_hint(
            "Failing or passing the scan depends on your chosen policy and "
            "severity threshold."
        )
    if config.supplyChain.sbom.enabled:
        _print_hint(
            "Syft can generate a Software Bill of Materials so dependencies "
            "are traceable."
        )
    _print_supply_chain_signing_warning(config, image)
    _print_supply_chain_latest_warning(image)


def _print_supply_chain_render_hint(config_path: Path) -> None:
    _print_hint("Supply chain readiness is enabled.")
    _print_hint("Kubernetes manifests were generated separately.")
    _print_hint(
        "Run: k8s-forge supply-chain render "
        f"{config_path} --output generated-supply-chain/"
    )


def _print_supply_chain_summary_table(paths: list[Path]) -> None:
    table = Table(title="Generated supply chain files")
    table.add_column("File")
    for path in paths:
        table.add_row(path.name)
    console.print(table)


def _print_supply_chain_next_steps(paths: list[Path]) -> None:
    generated_names = {path.name for path in paths}
    _print_hint("Next validation commands:")
    if "scan-image.sh" in generated_names:
        _print_hint("  ./scan-image.sh")
    if "generate-sbom.sh" in generated_names:
        _print_hint("  ./generate-sbom.sh")
    if "sign-image.sh" in generated_names:
        _print_hint("  ./sign-image.sh")
    if "verify-image.sh" in generated_names:
        _print_hint("  ./verify-image.sh")
    _print_hint("  k8s-forge doctor")


def _is_direct_workflows_output(output: Path) -> bool:
    return output.name == "workflows" and output.parent.name == ".github"


def _print_ci_latest_warning(image: str) -> None:
    if uses_latest_tag(image):
        _print_warning("The selected CI image uses the latest tag.")
        _print_hint("This is convenient for labs but weak for traceability.")
        _print_hint("Prefer immutable version tags or digests in CI workflows.")


def _print_ci_summary(config: AppConfig) -> None:
    if not config.ci.enabled:
        return
    image = resolve_ci_image(config)
    _print_hint("CI readiness is enabled.")
    _print_hint("GitHub Actions can automate the same checks you run locally.")
    _print_hint(
        "k8s-forge generates workflow files but does not push code, publish "
        "images, deploy Kubernetes resources, or create secrets."
    )
    if config.ci.python.enabled:
        _print_hint(
            "The Python workflow can run formatting, linting, typing, tests, "
            "security audit, and package build checks."
        )
    if config.ci.container.enabled:
        _print_hint(
            "The security workflow can build the image locally, scan it with "
            "Trivy, and generate an SBOM with Syft."
        )
        _print_hint(f"CI container image: {image}")
        _print_ci_latest_warning(image)


def _print_ci_render_hint(config_path: Path) -> None:
    _print_hint("CI readiness is enabled.")
    _print_hint("Kubernetes manifests were generated separately.")
    _print_hint(f"Run: k8s-forge ci render {config_path} --output generated-ci/")


def _print_ci_summary_table(paths: list[Path], output: Path) -> None:
    table = Table(title="Generated CI files")
    table.add_column("File")
    for path in paths:
        try:
            rendered = str(path.relative_to(output))
        except ValueError:
            rendered = str(path)
        table.add_row(rendered)
    console.print(table)


def _print_ci_next_steps(output: Path) -> None:
    _print_hint("Next validation steps:")
    _print_hint(f"  Review the files in {output}")
    if not _is_direct_workflows_output(output):
        _print_hint("  Copy generated .github/workflows/*.yml into your repository")
    _print_hint("  git status")
    _print_hint("  Commit the workflow files when you are ready")


def _print_ci_diagnostics(report: DoctorReport) -> None:
    _print_step("Checking CI readiness...")
    _print_hint(
        "Git is required to manage GitHub Actions workflow files in a repository."
    )
    _print_hint(
        "k8s-forge does not create GitHub secrets and does not push workflows "
        "automatically."
    )
    if report.git.status == "OK":
        console.print("[green]Git is available.[/green]")
    else:
        _print_warning(
            "Git is not available. CI workflow files can still be rendered, "
            "but repository operations are not available yet."
        )


def _print_gitops_warnings(config: AppConfig) -> None:
    if not config.gitops.enabled:
        return
    repo_url = config.gitops.source.repo_url
    if "example" in repo_url.lower():
        _print_warning("The GitOps repoURL still looks like an example value.")
    if not repo_url.strip():
        _print_warning("gitops.source.repoURL is empty.")
    if not config.gitops.source.path.strip():
        _print_warning("gitops.source.path is empty.")
    if config.gitops.sync_policy.automated:
        _print_warning("ArgoCD automated sync is enabled. Review this carefully.")
    if config.gitops.sync_policy.prune:
        _print_warning(
            "ArgoCD prune is enabled. It can delete resources missing from Git."
        )
    if config.gitops.sync_policy.self_heal:
        _print_warning(
            "ArgoCD selfHeal is enabled. It can revert manual cluster changes."
        )


def _print_gitops_summary(config: AppConfig) -> None:
    if not config.gitops.enabled:
        return
    _print_hint("GitOps readiness is enabled.")
    _print_hint(
        "ArgoCD can continuously compare a Git repository with the cluster state."
    )
    _print_hint(
        "k8s-forge generates ArgoCD manifests but does not install ArgoCD, "
        "push Git commits, or sync applications automatically."
    )
    _print_hint(f"ArgoCD Application: {resolve_gitops_application_name(config)}")
    _print_hint(
        f"Destination namespace: {resolve_gitops_destination_namespace(config)}"
    )
    _print_gitops_warnings(config)


def _print_gitops_render_hint(config_path: Path) -> None:
    _print_hint("GitOps readiness is enabled.")
    _print_hint("Kubernetes manifests were generated separately.")
    _print_hint(
        f"Run: k8s-forge gitops render {config_path} --output generated-gitops/"
    )


def _print_gitops_summary_table(paths: list[Path], output: Path) -> None:
    table = Table(title="Generated GitOps files")
    table.add_column("File")
    for path in paths:
        try:
            rendered = str(path.relative_to(output))
        except ValueError:
            rendered = str(path)
        table.add_row(rendered)
    console.print(table)


def _print_gitops_next_steps(output: Path) -> None:
    _print_hint("Next review commands:")
    _print_hint(f"  cat {output / 'README.md'}")
    _print_hint(f"  cat {output / 'argocd' / 'application.yaml'}")
    _print_hint("  k8s-forge doctor")


def _print_argocd_diagnostics(report: DoctorReport) -> None:
    _print_step("Checking ArgoCD GitOps readiness...")
    _print_hint(
        "ArgoCD manifests can be reviewed locally, but they become active only "
        "after ArgoCD is installed in the cluster."
    )
    _print_hint(
        "k8s-forge does not install ArgoCD and does not sync applications "
        "automatically."
    )
    if (
        report.argocd_namespace.status == "OK"
        and report.argocd_deployments.status == "OK"
        and report.argocd_applications_crd.status == "OK"
    ):
        console.print("[green]ArgoCD appears to be installed.[/green]")
    else:
        _print_warning("ArgoCD does not appear to be installed in this cluster.")
        _print_hint(
            "Generated Application manifests can be reviewed locally, but they "
            "will be accepted by the cluster only after ArgoCD CRDs are installed."
        )


def _print_observability_warnings(config: AppConfig) -> None:
    if not config.observability.enabled:
        return
    if config.observability.serviceMonitor.enabled:
        _print_warning(
            "ServiceMonitor readiness is enabled. The cluster needs Prometheus "
            "Operator CRDs before this resource can be accepted."
        )
    if (
        config.observability.grafana.enabled
        and config.observability.grafana.dashboard.enabled
    ):
        _print_warning(
            "The Grafana dashboard is a local model. Real panels need Prometheus "
            "data and application metrics."
        )
    if config.observability.alerts.enabled:
        _print_warning(
            "observability.alerts.enabled is true, but PrometheusRule rendering "
            "is outside v0.11.0."
        )


def _print_observability_summary(config: AppConfig) -> None:
    if not config.observability.enabled:
        return
    _print_hint("Observability readiness is enabled.")
    _print_hint(
        "Prometheus can scrape application metrics when the application exposes "
        "a metrics endpoint and the Prometheus Operator is installed."
    )
    _print_hint(
        "k8s-forge generates observability manifests and dashboard examples but "
        "does not install Prometheus, Grafana, Loki, or monitoring CRDs automatically."
    )
    _print_hint(f"Metrics endpoint: {config.observability.metrics.path}")
    _print_hint(
        f"ServiceMonitor namespace: {resolve_service_monitor_namespace(config)}"
    )
    dashboard_state = (
        "enabled"
        if config.observability.grafana.enabled
        and config.observability.grafana.dashboard.enabled
        else "disabled"
    )
    _print_hint(f"Grafana dashboard: {dashboard_state}")
    _print_observability_warnings(config)


def _print_observability_render_hint(config_path: Path) -> None:
    _print_hint("Observability readiness is enabled.")
    _print_hint("Kubernetes manifests were generated separately.")
    _print_hint(
        "Run: k8s-forge observability render "
        f"{config_path} --output generated-observability/"
    )


def _print_observability_summary_table(paths: list[Path], output: Path) -> None:
    table = Table(title="Generated observability files")
    table.add_column("File")
    for path in paths:
        try:
            rendered = str(path.relative_to(output))
        except ValueError:
            rendered = str(path)
        table.add_row(rendered)
    console.print(table)


def _print_observability_next_steps(output: Path) -> None:
    _print_hint("Next review commands:")
    _print_hint(f"  cat {output / 'README.md'}")
    _print_hint(f"  cat {output / 'prometheus' / 'servicemonitor.yaml'}")
    _print_hint(f"  cat {output / 'grafana' / 'dashboard.json'}")
    _print_hint("  k8s-forge doctor")


def _print_observability_diagnostics(report: DoctorReport) -> None:
    _print_step("Checking observability readiness...")
    _print_hint(
        "Prometheus Operator CRDs are required before ServiceMonitor resources "
        "can be accepted by the cluster."
    )
    _print_hint(
        "k8s-forge does not install Prometheus, Grafana, Loki, or "
        "kube-prometheus-stack automatically."
    )
    _print_hint(
        "Generated observability files can be reviewed locally and applied only "
        "after the monitoring stack is installed manually."
    )
    if report.servicemonitor_crd.status == "OK":
        console.print("[green]ServiceMonitor CRD appears to be available.[/green]")
    else:
        _print_warning(
            "Prometheus Operator CRDs do not appear to be installed in this cluster."
        )
        _print_hint(
            "Generated ServiceMonitor manifests can be reviewed locally, but they "
            "will be accepted by the cluster only after monitoring.coreos.com CRDs "
            "are installed."
        )


def _print_logging_warnings(config: AppConfig) -> None:
    if not config.logging.enabled:
        return
    if config.logging.collector.enabled:
        _print_warning(
            "Promtail is only the collector model here; it must be installed and "
            "configured manually for real log collection."
        )
    if config.logging.grafana.enabled and config.logging.grafana.dashboard.enabled:
        _print_warning(
            "The Grafana logs dashboard is a local model. A Loki datasource must "
            "be configured manually in Grafana."
        )
    _print_hint(
        "The generated LogQL labels are examples; adapt them to the labels exposed "
        "by your collector."
    )
    _print_hint(
        "The application must write useful logs to stdout or stderr for Kubernetes "
        "log collection to be useful."
    )


def _print_logging_summary(config: AppConfig) -> None:
    if not config.logging.enabled:
        return
    _print_hint("Logging readiness is enabled.")
    _print_hint(
        "Loki can store and query Kubernetes logs when a compatible collector is "
        "installed."
    )
    _print_hint(
        "k8s-forge generates logging examples and dashboard files but does not "
        "install Loki, Grafana, Promtail, Alloy, or logging agents automatically."
    )
    _print_hint(f"Logging provider: {config.logging.provider}")
    _print_hint(f"Application log source: {config.logging.application_logs.source}")
    _print_hint(f"Collector model: {config.logging.collector.type}")
    dashboard_state = (
        "enabled"
        if config.logging.grafana.enabled and config.logging.grafana.dashboard.enabled
        else "disabled"
    )
    _print_hint(f"Grafana logs dashboard: {dashboard_state}")
    _print_logging_warnings(config)


def _print_logging_render_hint(config_path: Path) -> None:
    _print_hint("Logging readiness is enabled.")
    _print_hint("Kubernetes manifests were generated separately.")
    _print_hint(
        f"Run: k8s-forge logging render {config_path} --output generated-logging/"
    )


def _print_logging_summary_table(paths: list[Path], output: Path) -> None:
    table = Table(title="Generated logging files")
    table.add_column("File")
    for path in paths:
        try:
            rendered = str(path.relative_to(output))
        except ValueError:
            rendered = str(path)
        table.add_row(rendered)
    console.print(table)


def _print_logging_next_steps(output: Path) -> None:
    _print_hint("Next review commands:")
    _print_hint(f"  cat {output / 'README.md'}")
    _print_hint(f"  cat {output / 'loki' / 'logql-queries.md'}")
    _print_hint(f"  cat {output / 'grafana' / 'logs-dashboard.json'}")
    _print_hint(f"  cat {output / 'collector' / 'collector-notes.md'}")
    _print_hint("  k8s-forge doctor")


def _print_logging_diagnostics(report: DoctorReport) -> None:
    _print_step("Checking logging readiness...")
    _print_hint(
        "Loki stores logs only after a compatible collector is installed and "
        "configured."
    )
    _print_hint(
        "k8s-forge does not install Loki, Grafana, Promtail, Alloy, or logging "
        "agents automatically."
    )
    _print_hint(
        "Generated logging files can be reviewed locally and used after the "
        "logging stack is installed manually."
    )
    if report.loki.status == "OK" and (
        report.promtail.status == "OK" or report.alloy.status == "OK"
    ):
        console.print(
            "[green]Loki and a compatible log collector appear to be available.[/green]"
        )
    else:
        _print_warning(
            "Loki or a compatible log collector does not appear to be installed "
            "in this cluster."
        )
        _print_hint(
            "Generated logging examples can be reviewed locally, but logs will "
            "be queryable only after a logging stack is installed manually."
        )
    if report.grafana.status == "OK":
        console.print("[green]Grafana appears to be available.[/green]")
    else:
        _print_hint("Grafana was not detected for logging dashboard import.")


def _print_tracing_warnings(config: AppConfig) -> None:
    if not config.tracing.enabled:
        return
    if config.tracing.collector.enabled:
        _print_warning(
            "OpenTelemetry Collector is only the collector model here; it must "
            "be installed and configured manually for real trace export."
        )
    if config.tracing.grafana.enabled and config.tracing.grafana.dashboard.enabled:
        _print_warning(
            "The Grafana traces dashboard is a local model. A Tempo datasource "
            "must be configured manually in Grafana."
        )
    if config.tracing.instrumentation.enabled:
        _print_hint(
            "Application instrumentation is not automatic; the application must "
            "emit spans with OpenTelemetry libraries or framework support."
        )
    if not config.tracing.instrumentation.service_name.strip():
        _print_hint(
            f"Tracing serviceName is empty; using application name {config.app.name}."
        )
    _print_hint(
        "Traces will not be visible until the application is instrumented and "
        "a collector plus backend such as Tempo are installed manually."
    )


def _print_tracing_summary(config: AppConfig) -> None:
    if not config.tracing.enabled:
        return
    _print_hint("Tracing readiness is enabled.")
    _print_hint(
        "OpenTelemetry can export application traces to a compatible backend "
        "such as Tempo."
    )
    _print_hint(
        "k8s-forge generates tracing examples and dashboard files but does not "
        "install OpenTelemetry Collector, Tempo, Grafana, or tracing agents "
        "automatically."
    )
    _print_hint(f"Tracing provider: {config.tracing.provider}")
    _print_hint(f"Trace backend: {config.tracing.backend.type}")
    _print_hint(f"Collector model: {config.tracing.collector.type}")
    _print_hint(f"OTLP protocol: {config.tracing.collector.protocol}")
    dashboard_state = (
        "enabled"
        if config.tracing.grafana.enabled and config.tracing.grafana.dashboard.enabled
        else "disabled"
    )
    _print_hint(f"Grafana traces dashboard: {dashboard_state}")
    _print_tracing_warnings(config)


def _print_tracing_render_hint(config_path: Path) -> None:
    _print_hint("Tracing readiness is enabled.")
    _print_hint("Kubernetes manifests were generated separately.")
    _print_hint(
        f"Run: k8s-forge tracing render {config_path} --output generated-tracing/"
    )


def _print_tracing_summary_table(paths: list[Path], output: Path) -> None:
    table = Table(title="Generated tracing files")
    table.add_column("File")
    for path in paths:
        try:
            rendered = str(path.relative_to(output))
        except ValueError:
            rendered = str(path)
        table.add_row(rendered)
    console.print(table)


def _print_tracing_next_steps(output: Path) -> None:
    _print_hint("Next review commands:")
    _print_hint(f"  cat {output / 'README.md'}")
    _print_hint(f"  cat {output / 'opentelemetry' / 'instrumentation-notes.md'}")
    _print_hint(f"  cat {output / 'opentelemetry' / 'otel-env.md'}")
    _print_hint(f"  cat {output / 'tempo' / 'traceql-examples.md'}")
    _print_hint(f"  cat {output / 'grafana' / 'traces-dashboard.json'}")
    _print_hint(f"  cat {output / 'collector' / 'collector-notes.md'}")
    _print_hint("  k8s-forge doctor")


def _print_tracing_diagnostics(report: DoctorReport) -> None:
    _print_step("Checking tracing readiness...")
    _print_hint(
        "OpenTelemetry exports traces only after the application is instrumented "
        "and a compatible collector/backend is installed."
    )
    _print_hint(
        "k8s-forge does not install OpenTelemetry Collector, Tempo, Grafana, "
        "Jaeger, or tracing agents automatically."
    )
    _print_hint(
        "Generated tracing files can be reviewed locally and used after the "
        "tracing stack is installed manually."
    )
    if report.tempo.status == "OK" and report.otel_collector.status == "OK":
        console.print(
            "[green]Tempo and OpenTelemetry Collector appear to be available.[/green]"
        )
    else:
        _print_warning(
            "Tempo or a compatible tracing backend does not appear to be installed "
            "in this cluster."
        )
        _print_hint(
            "Generated tracing examples can be reviewed locally, but traces will "
            "be queryable only after a tracing stack is installed manually."
        )
    if report.tracing_grafana.status == "OK":
        console.print("[green]Grafana appears to be available for tracing.[/green]")
    else:
        _print_hint("Grafana was not detected for tracing dashboard import.")
    if report.jaeger.status == "OK":
        _print_hint("Jaeger was detected as a possible tracing backend alternative.")


def _print_terraform_summary(config: AppConfig) -> None:
    if not config.terraform.enabled:
        return
    _print_hint("Terraform readiness is enabled.")
    _print_hint(
        "Terraform can describe infrastructure as code, but k8s-forge only "
        "generates local educational examples."
    )
    _print_hint(
        "k8s-forge does not run Terraform commands that create, modify, or "
        "destroy resources."
    )
    _print_hint(f"Terraform project: {resolve_terraform_project_name(config)}")
    _print_hint(f"Terraform backend: {config.terraform.backend.type}")
    kubernetes_state = (
        "enabled" if config.terraform.providers.kubernetes.enabled else "disabled"
    )
    helm_state = "enabled" if config.terraform.providers.helm.enabled else "disabled"
    cloud_state = "enabled" if config.terraform.providers.cloud.enabled else "disabled"
    _print_hint(f"Kubernetes provider example: {kubernetes_state}")
    _print_hint(f"Helm provider example: {helm_state}")
    _print_hint(f"Cloud provider example: {cloud_state}")
    if config.terraform.providers.cloud.enabled:
        _print_warning(
            "terraform.providers.cloud.enabled is true, but v0.14.0 does not "
            "render a real cloud provider."
        )


def _print_terraform_render_hint(config_path: Path) -> None:
    _print_hint("Terraform readiness is enabled.")
    _print_hint("Kubernetes manifests were generated separately.")
    _print_hint(
        f"Run: k8s-forge terraform render {config_path} --output generated-terraform/"
    )


def _print_terraform_summary_table(paths: list[Path], output: Path) -> None:
    table = Table(title="Generated Terraform files")
    table.add_column("File")
    for path in paths:
        try:
            rendered = str(path.relative_to(output))
        except ValueError:
            rendered = str(path)
        table.add_row(rendered)
    console.print(table)


def _print_terraform_next_steps(output: Path) -> None:
    _print_hint("Next review commands:")
    _print_hint(f"  cat {output / 'README.md'}")
    _print_hint(f"  cat {output / 'versions.tf'}")
    _print_hint(f"  cat {output / 'providers.tf'}")
    _print_hint(f"  cat {output / 'variables.tf'}")
    _print_hint(f"  cat {output / 'main.tf'}")
    _print_hint(f"  cat {output / 'outputs.tf'}")
    _print_hint("  k8s-forge doctor")


def _print_terraform_diagnostics(report: DoctorReport) -> None:
    _print_step("Checking Terraform readiness...")
    _print_hint(
        "Terraform can be used to model infrastructure, but k8s-forge does not "
        "run Terraform commands that create, modify, or destroy resources."
    )
    _print_hint(
        "Generated Terraform files can be reviewed locally before any manual "
        "Terraform workflow."
    )
    if report.terraform.status == "OK":
        console.print("[green]Terraform is available.[/green]")
    else:
        _print_warning(
            "Terraform is not installed. Terraform readiness files can still be "
            "rendered and reviewed locally."
        )


def _print_ansible_summary(config: AppConfig) -> None:
    if not config.ansible.enabled:
        return
    _print_hint("Ansible readiness is enabled.")
    _print_hint(
        "Ansible can automate configuration and operational tasks, but "
        "k8s-forge only generates local educational examples."
    )
    _print_hint(
        "k8s-forge does not run Ansible commands, open SSH connections, "
        "or modify remote hosts."
    )
    _print_hint(f"Ansible project: {resolve_ansible_project_name(config)}")
    _print_hint(f"Ansible inventory type: {config.ansible.inventory.type}")
    _print_hint(f"Ansible example host: {', '.join(config.ansible.inventory.hosts)}")
    roles_state = "enabled" if config.ansible.roles.enabled else "disabled"
    kubernetes_state = (
        "enabled" if config.ansible.collections.kubernetes.enabled else "disabled"
    )
    community_state = (
        "enabled" if config.ansible.collections.community.enabled else "disabled"
    )
    _print_hint(f"Ansible roles structure: {roles_state}")
    _print_hint(f"Kubernetes collection example: {kubernetes_state}")
    _print_hint(f"Community collection example: {community_state}")


def _print_ansible_render_hint(config_path: Path) -> None:
    _print_hint("Ansible readiness is enabled.")
    _print_hint("Kubernetes manifests were generated separately.")
    _print_hint(
        f"Run: k8s-forge ansible render {config_path} --output generated-ansible/"
    )


def _print_ansible_summary_table(paths: list[Path], output: Path) -> None:
    table = Table(title="Generated Ansible files")
    table.add_column("File")
    for path in paths:
        try:
            rendered = str(path.relative_to(output))
        except ValueError:
            rendered = str(path)
        table.add_row(rendered)
    console.print(table)


def _print_ansible_next_steps(output: Path, playbook_name: str) -> None:
    _print_hint("Next review commands:")
    _print_hint(f"  cat {output / 'README.md'}")
    _print_hint(f"  cat {output / 'ansible.cfg'}")
    _print_hint(f"  cat {output / 'inventory.ini'}")
    _print_hint(f"  cat {output / playbook_name}")
    _print_hint(f"  cat {output / 'group_vars' / 'all.yml'}")
    _print_hint(f"  cat {output / 'roles' / 'README.md'}")
    _print_hint("  k8s-forge doctor")


def _print_ansible_diagnostics(report: DoctorReport) -> None:
    _print_step("Checking Ansible readiness...")
    _print_hint(
        "Ansible can automate configuration and operational workflows, but "
        "k8s-forge does not run playbooks or contact remote hosts."
    )
    _print_hint(
        "Generated Ansible files can be reviewed locally before any manual "
        "Ansible workflow."
    )
    if report.ansible.status == "OK":
        console.print(
            f"[green]Ansible is available.[/green] {escape(report.ansible.details)}"
        )
    else:
        _print_warning(
            "Ansible is not installed. Ansible readiness files can still be "
            "rendered and reviewed locally."
        )
    if report.ansible_lint.status == "OK":
        console.print(
            "[green]ansible-lint is available.[/green] "
            f"{escape(report.ansible_lint.details)}"
        )
    else:
        _print_hint("ansible-lint is optional and was not detected.")


def _print_security_summary(config: AppConfig) -> None:
    if not config.security.enabled:
        return
    _print_hint("Security Audit readiness is enabled.")
    _print_hint(
        "k8s-forge will generate a local security review for containers, "
        "manifests, RBAC, network policies, secrets, and supply chain."
    )
    _print_hint(
        "This module does not run scanners, contact the cluster, or prove "
        "runtime compliance automatically."
    )
    _print_hint(f"Security project: {resolve_security_project_name(config)}")
    container_state = "enabled" if config.security.container.enabled else "disabled"
    manifests_state = "enabled" if config.security.manifests.enabled else "disabled"
    rbac_state = "enabled" if config.security.rbac.enabled else "disabled"
    pod_security_state = (
        "enabled" if config.security.pod_security.enabled else "disabled"
    )
    network_state = "enabled" if config.security.network.enabled else "disabled"
    secrets_state = "enabled" if config.security.secrets.enabled else "disabled"
    supply_chain_state = (
        "enabled" if config.security.supply_chain.enabled else "disabled"
    )
    checklist_state = "enabled" if config.security.checklist.enabled else "disabled"
    _print_hint(f"Container security review: {container_state}")
    _print_hint(f"Kubernetes manifest review: {manifests_state}")
    _print_hint(f"RBAC review: {rbac_state}")
    _print_hint(f"Pod security review: {pod_security_state}")
    _print_hint(f"Network security review: {network_state}")
    _print_hint(f"Secrets review: {secrets_state}")
    _print_hint(f"Supply chain review: {supply_chain_state}")
    _print_hint(f"Final security checklist: {checklist_state}")


def _print_security_render_hint(config_path: Path) -> None:
    _print_hint("Security Audit readiness is enabled.")
    _print_hint("Kubernetes manifests were generated separately.")
    _print_hint(
        "Run: k8s-forge security render "
        f"{config_path} --output generated-security-audit/"
    )


def _print_security_summary_table(paths: list[Path], output: Path) -> None:
    table = Table(title="Generated Security Audit files")
    table.add_column("File")
    for path in paths:
        try:
            rendered = str(path.relative_to(output))
        except ValueError:
            rendered = str(path)
        table.add_row(rendered)
    console.print(table)


def _print_security_next_steps(output: Path) -> None:
    _print_hint("Next review commands:")
    _print_hint(f"  cat {output / 'README.md'}")
    _print_hint(f"  cat {output / 'container-security.md'}")
    _print_hint(f"  cat {output / 'kubernetes-manifest-audit.md'}")
    _print_hint(f"  cat {output / 'rbac-audit.md'}")
    _print_hint(f"  cat {output / 'pod-security-audit.md'}")
    _print_hint(f"  cat {output / 'network-security-audit.md'}")
    _print_hint(f"  cat {output / 'secrets-audit.md'}")
    _print_hint(f"  cat {output / 'supply-chain-security.md'}")
    _print_hint(f"  cat {output / 'final-security-checklist.md'}")
    _print_hint("  k8s-forge doctor")


def _print_capstone_summary(config: AppConfig) -> None:
    if not config.capstone.enabled:
        return
    _print_hint("Capstone readiness is enabled.")
    _print_hint(
        "k8s-forge will generate a final DevSecOps lab summary and validation "
        "checklist."
    )
    _print_hint(
        "This module does not deploy, verify, or modify the platform automatically."
    )
    _print_hint(f"Capstone project: {resolve_capstone_project_name(config)}")
    architecture_state = (
        "enabled" if config.capstone.architecture.enabled else "disabled"
    )
    matrix_state = "enabled" if config.capstone.devsecops_matrix.enabled else "disabled"
    modules_state = "enabled" if config.capstone.modules_summary.enabled else "disabled"
    checklist_state = "enabled" if config.capstone.checklist.enabled else "disabled"
    manual_steps_state = (
        "enabled" if config.capstone.manual_steps.enabled else "disabled"
    )
    runtime_state = (
        "enabled" if config.capstone.runtime_dependencies.enabled else "disabled"
    )
    security_state = (
        "enabled" if config.capstone.security_summary.enabled else "disabled"
    )
    v1_state = "enabled" if config.capstone.v1_readiness.enabled else "disabled"
    _print_hint(f"Architecture overview: {architecture_state}")
    _print_hint(f"DevSecOps matrix: {matrix_state}")
    _print_hint(f"Modules summary: {modules_state}")
    _print_hint(f"Validation checklist: {checklist_state}")
    _print_hint(f"Manual steps: {manual_steps_state}")
    _print_hint(f"Runtime dependencies: {runtime_state}")
    _print_hint(f"Security summary: {security_state}")
    _print_hint(f"v1 readiness: {v1_state}")


def _print_capstone_render_hint(config_path: Path) -> None:
    _print_hint("Capstone readiness is enabled.")
    _print_hint("Kubernetes manifests were generated separately.")
    _print_hint(
        f"Run: k8s-forge capstone render {config_path} --output generated-capstone/"
    )


def _print_capstone_summary_table(paths: list[Path], output: Path) -> None:
    table = Table(title="Generated Capstone files")
    table.add_column("File")
    for path in paths:
        try:
            rendered = str(path.relative_to(output))
        except ValueError:
            rendered = str(path)
        table.add_row(rendered)
    console.print(table)


def _print_capstone_next_steps(output: Path) -> None:
    _print_hint("Next review commands:")
    _print_hint(f"  cat {output / 'README.md'}")
    _print_hint(f"  cat {output / 'lab-summary.md'}")
    _print_hint(f"  cat {output / 'architecture-overview.md'}")
    _print_hint(f"  cat {output / 'devsecops-chain.md'}")
    _print_hint(f"  cat {output / 'modules-summary.md'}")
    _print_hint(f"  cat {output / 'validation-checklist.md'}")
    _print_hint(f"  cat {output / 'manual-steps.md'}")
    _print_hint(f"  cat {output / 'runtime-dependencies.md'}")
    _print_hint(f"  cat {output / 'security-summary.md'}")
    _print_hint(f"  cat {output / 'v1-readiness.md'}")
    _print_hint(f"  cat {output / 'final-report-outline.md'}")
    _print_hint("  k8s-forge doctor")


def _print_check_summary(config: AppConfig) -> None:
    """Print a concise validation summary."""
    table = Table(title="Application configuration")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("app name", config.app.name)
    table.add_row("namespace", config.app.namespace)
    table.add_row("image", config.app.image)
    table.add_row("replicas", str(config.app.replicas))
    table.add_row("container port", str(config.app.containerPort))
    table.add_row("service", _service_state(config))
    table.add_row("autoscaling", _autoscaling_state(config))
    console.print(table)


def _print_render_summary(paths: list[Path]) -> None:
    """Print the generated manifest paths."""
    table = Table(title="Generated manifests")
    table.add_column("File")
    for path in paths:
        table.add_row(path.name)
    console.print(table)


def _print_helm_chart_summary(paths: list[Path]) -> None:
    """Print generated Helm chart paths."""
    table = Table(title="Generated Helm chart files")
    table.add_column("File")
    chart_dir = paths[0].parent if paths else Path(".")
    for path in paths:
        table.add_row(str(path.relative_to(chart_dir)))
    console.print(table)


def _starter_config_data(
    name: str,
    namespace: str | None,
    image: str | None,
    port: int,
    replicas: int,
    service_port: int,
    hpa_enabled: bool,
    hpa_min: int,
    hpa_max: int,
    hpa_cpu: int,
) -> dict[str, Any]:
    app_namespace = namespace or name
    app_image = image or f"{name}:latest"
    return {
        "app": {
            "name": name,
            "namespace": app_namespace,
            "image": app_image,
            "containerPort": port,
            "replicas": replicas,
        },
        "config": {
            "APP_ENV": _QuotedString("dev"),
            "LOG_LEVEL": _QuotedString("info"),
        },
        "secrets": {
            "API_TOKEN": _QuotedString("change-me"),
        },
        "service": {
            "enabled": True,
            "port": service_port,
        },
        "resources": {
            "requests": {
                "cpu": _QuotedString("50m"),
                "memory": _QuotedString("64Mi"),
            },
            "limits": {
                "cpu": _QuotedString("250m"),
                "memory": _QuotedString("128Mi"),
            },
        },
        "probes": {
            "liveness": _QuotedString("/healthz"),
            "readiness": _QuotedString("/readyz"),
        },
        "autoscaling": {
            "enabled": hpa_enabled,
            "minReplicas": hpa_min,
            "maxReplicas": hpa_max,
            "targetCPUUtilizationPercentage": hpa_cpu,
        },
        "ingress": {
            "enabled": False,
            "host": None,
            "className": _QuotedString("nginx"),
            "path": _QuotedString("/"),
            "pathType": _QuotedString("Prefix"),
            "tls": {
                "enabled": False,
                "secretName": None,
            },
            "certManager": {
                "enabled": False,
                "clusterIssuer": None,
            },
            "annotations": {},
        },
        "mesh": {
            "enabled": False,
            "provider": _QuotedString("linkerd"),
            "inject": False,
            "annotations": {
                "linkerd.io/inject": _QuotedString("enabled"),
            },
        },
        "networkPolicy": {
            "enabled": False,
            "profile": _QuotedString("ingress-only"),
            "ingress": {
                "enabled": True,
                "fromNamespaces": [_QuotedString("ingress-nginx")],
                "ports": [port],
            },
            "egress": {
                "enabled": False,
            },
        },
        "policy": {
            "enabled": False,
            "provider": _QuotedString("kyverno"),
            "profile": _QuotedString("baseline"),
            "validationFailureAction": _QuotedString("Audit"),
            "background": True,
            "rules": {
                "requireRecommendedLabels": True,
                "disallowPrivilegedContainers": True,
                "requireRunAsNonRoot": True,
                "requireResources": True,
                "disallowLatestTag": True,
            },
        },
        "supplyChain": {
            "enabled": False,
            "image": _QuotedString(""),
            "scan": {
                "enabled": True,
                "tool": _QuotedString("trivy"),
                "severity": [_QuotedString("HIGH"), _QuotedString("CRITICAL")],
            },
            "sbom": {
                "enabled": True,
                "tool": _QuotedString("syft"),
                "format": _QuotedString("cyclonedx-json"),
            },
            "signing": {
                "enabled": False,
                "tool": _QuotedString("cosign"),
                "keyless": True,
            },
        },
        "ci": {
            "enabled": False,
            "provider": _QuotedString("github-actions"),
            "python": {
                "enabled": True,
                "version": _QuotedString("3.12"),
                "quality": {
                    "ruff": True,
                    "mypy": True,
                    "bandit": True,
                    "pipAudit": True,
                    "pytest": True,
                    "build": True,
                },
            },
            "container": {
                "enabled": True,
                "image": _QuotedString(""),
                "dockerfile": _QuotedString("Dockerfile"),
                "context": _QuotedString("."),
                "scan": {
                    "enabled": True,
                    "tool": _QuotedString("trivy"),
                    "severity": [_QuotedString("HIGH"), _QuotedString("CRITICAL")],
                },
                "sbom": {
                    "enabled": True,
                    "tool": _QuotedString("syft"),
                    "format": _QuotedString("cyclonedx-json"),
                },
            },
            "artifacts": {
                "enabled": True,
            },
        },
        "gitops": {
            "enabled": False,
            "provider": _QuotedString("argocd"),
            "application": {
                "name": _QuotedString(""),
                "namespace": _QuotedString("argocd"),
                "project": _QuotedString("default"),
            },
            "destination": {
                "server": _QuotedString("https://kubernetes.default.svc"),
                "namespace": _QuotedString(""),
            },
            "source": {
                "repoURL": _QuotedString(""),
                "targetRevision": _QuotedString("main"),
                "path": _QuotedString(f"charts-generated/{name}"),
                "type": _QuotedString("helm"),
            },
            "syncPolicy": {
                "automated": False,
                "prune": False,
                "selfHeal": False,
            },
        },
        "observability": {
            "enabled": False,
            "provider": _QuotedString("prometheus"),
            "metrics": {
                "enabled": True,
                "path": _QuotedString("/metrics"),
                "portName": _QuotedString("http"),
                "interval": _QuotedString("30s"),
            },
            "serviceMonitor": {
                "enabled": True,
                "namespace": _QuotedString(""),
                "labels": {},
            },
            "grafana": {
                "enabled": True,
                "dashboard": {
                    "enabled": True,
                    "title": _QuotedString(""),
                },
            },
            "alerts": {"enabled": False},
        },
        "logging": {
            "enabled": False,
            "provider": _QuotedString("loki"),
            "applicationLogs": {
                "enabled": True,
                "source": _QuotedString("stdout"),
            },
            "loki": {
                "namespace": _QuotedString("monitoring"),
                "datasourceName": _QuotedString("Loki"),
            },
            "collector": {
                "enabled": True,
                "type": _QuotedString("promtail"),
            },
            "grafana": {
                "enabled": True,
                "dashboard": {
                    "enabled": True,
                    "title": _QuotedString(""),
                },
            },
            "queries": {"enabled": True},
        },
        "tracing": {
            "enabled": False,
            "provider": _QuotedString("opentelemetry"),
            "backend": {
                "type": _QuotedString("tempo"),
                "namespace": _QuotedString("monitoring"),
                "datasourceName": _QuotedString("Tempo"),
            },
            "collector": {
                "enabled": True,
                "type": _QuotedString("opentelemetry-collector"),
                "endpoint": _QuotedString(
                    "http://otel-collector.monitoring.svc.cluster.local:4318"
                ),
                "protocol": _QuotedString("otlp-http"),
            },
            "instrumentation": {
                "enabled": True,
                "mode": _QuotedString("env"),
                "serviceName": _QuotedString(""),
            },
            "grafana": {
                "enabled": True,
                "dashboard": {
                    "enabled": True,
                    "title": _QuotedString(""),
                },
            },
            "examples": {"enabled": True},
        },
        "terraform": {
            "enabled": False,
            "projectName": _QuotedString(""),
            "backend": {"type": _QuotedString("local")},
            "providers": {
                "kubernetes": {"enabled": True},
                "helm": {"enabled": True},
                "cloud": {"enabled": False},
            },
            "modules": {"enabled": True},
            "examples": {"enabled": True},
        },
        "ansible": {
            "enabled": False,
            "projectName": _QuotedString(""),
            "inventory": {
                "type": _QuotedString("local"),
                "hosts": [_QuotedString("localhost")],
            },
            "playbook": {"name": _QuotedString("site.yml")},
            "roles": {"enabled": True},
            "collections": {
                "kubernetes": {"enabled": True},
                "community": {"enabled": False},
            },
            "examples": {"enabled": True},
        },
        "security": {
            "enabled": False,
            "projectName": _QuotedString(""),
            "container": {"enabled": True},
            "manifests": {"enabled": True},
            "rbac": {"enabled": True},
            "podSecurity": {"enabled": True},
            "network": {"enabled": True},
            "secrets": {"enabled": True},
            "supplyChain": {"enabled": True},
            "checklist": {"enabled": True},
            "examples": {"enabled": True},
        },
        "capstone": {
            "enabled": False,
            "projectName": _QuotedString(""),
            "report": {
                "title": _QuotedString(""),
                "audience": _QuotedString("technical"),
            },
            "checklist": {"enabled": True},
            "architecture": {"enabled": True},
            "devsecopsMatrix": {"enabled": True},
            "modulesSummary": {"enabled": True},
            "manualSteps": {"enabled": True},
            "runtimeDependencies": {"enabled": True},
            "securitySummary": {"enabled": True},
            "v1Readiness": {"enabled": True},
            "examples": {"enabled": True},
        },
    }


def _starter_config_yaml(data: dict[str, Any]) -> str:
    rendered = yaml.dump(
        data,
        Dumper=_InitConfigDumper,
        sort_keys=False,
        default_flow_style=False,
    )
    return rendered.rstrip() + "\n"


def _load_and_render(config_path: Path, output: Path) -> list[Path]:
    loaded = load_app_config(config_path)
    return render_manifests(loaded, output)


def _load_config_and_render(
    config_path: Path, output: Path
) -> tuple[AppConfig, list[Path]]:
    loaded = load_app_config(config_path)
    return loaded, render_manifests(loaded, output)


def _print_kubectl_result(result: KubectlResult) -> None:
    if result.stdout:
        console.print(result.stdout.rstrip())
    if result.stderr:
        console.print(result.stderr.rstrip(), style="red")


def _run_kubectl_or_exit(
    args: list[str],
    timeout: int,
    success_codes: tuple[int, ...] = (0,),
) -> KubectlResult:
    try:
        result = run_kubectl(args, timeout=timeout)
    except KubectlError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_kubectl_result(result)
    if result.returncode not in success_codes:
        raise typer.Exit(code=result.returncode or 1)
    return result


def _namespace_not_found(output: str, namespace: str) -> bool:
    normalized = output.lower()
    quoted_double = f'namespaces "{namespace.lower()}" not found'
    quoted_single = f"namespaces '{namespace.lower()}' not found"
    return (
        quoted_double in normalized
        or quoted_single in normalized
        or ("namespaces" in normalized and "not found" in normalized)
    )


def _print_namespace_dry_run_warning(namespace: str) -> None:
    console.print(
        f"[yellow]Namespace {namespace!r} does not exist in the cluster.[/yellow]"
    )
    console.print(
        "[yellow]Server-side dry-run simulates the Namespace manifest but does "
        "not persist it. Namespaced resources such as ConfigMap, Secret, "
        "Deployment, and Service may fail validation.[/yellow]"
    )
    console.print(
        f"[yellow]Create it first with: kubectl create namespace {namespace}[/yellow]"
    )


def _print_namespace_dry_run_failure(
    namespace: str, config_path: Path, output: Path
) -> None:
    console.print(
        f"[yellow]The namespace {namespace!r} was only simulated during "
        "server-side dry-run; it was not really created.[/yellow]"
    )
    console.print(
        "[yellow]ConfigMap, Secret, Deployment, and Service cannot be validated "
        "inside a namespace that does not exist yet.[/yellow]"
    )
    console.print(f"[yellow]Run: kubectl create namespace {namespace}[/yellow]")
    rerun = f"k8s-forge dry-run {config_path} --output {output}"
    console.print(f"[yellow]Then rerun: {rerun}[/yellow]")


def _warn_if_namespace_missing(namespace: str, timeout: int) -> None:
    _print_step("Checking target namespace before dry-run...")
    _print_hint(
        "Server-side dry-run does not create the namespace for following "
        "resources, so the namespace must already exist."
    )
    try:
        result = run_kubectl(["get", "namespace", namespace], timeout=timeout)
    except KubectlError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if result.ok:
        return

    combined = f"{result.stdout}\n{result.stderr}"
    if _namespace_not_found(combined, namespace):
        _print_namespace_dry_run_warning(namespace)
        return

    _print_kubectl_result(result)
    console.print(
        f"[yellow]Could not verify namespace {namespace!r} before dry-run; "
        "continuing so Kubernetes can return the authoritative validation "
        "result.[/yellow]"
    )


def _print_local_result(result: LocalCommandResult) -> None:
    if result.stdout:
        console.print(result.stdout.rstrip())
    if result.stderr:
        console.print(result.stderr.rstrip(), style="red")


def _run_local_or_exit(
    result: LocalCommandResult, success_codes: tuple[int, ...] = (0,)
) -> LocalCommandResult:
    _print_local_result(result)
    if result.returncode not in success_codes:
        raise typer.Exit(code=result.returncode or 1)
    return result


def _print_tool_checks(checks: list[ToolCheck]) -> None:
    table = Table(title="Local environment")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Details")
    for check in checks:
        table.add_row(check.name, check.status, check.details)
    console.print(table)
    for check in checks:
        if check.status != "OK" and check.details:
            console.print(f"{check.name}: {check.details}")


def _print_context_and_nodes(timeout: int) -> None:
    try:
        console.print("[bold]Current context[/bold]")
        _run_local_or_exit(current_context(timeout))
        console.print("[bold]Nodes[/bold]")
        _run_local_or_exit(get_nodes(timeout))
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


def _kind_clusters_or_exit(timeout: int) -> list[str]:
    try:
        return get_kind_clusters(timeout)
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help="Show the k8s-forge version and exit.",
        ),
    ] = False,
) -> None:
    """Run k8s-forge."""
    _ = version


@app.command()
def studio(
    host: Annotated[
        str,
        typer.Option("--host", help="Local host to bind Studio to."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="Local Studio port."),
    ] = 8765,
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Studio workspace directory."),
    ] = Path(".k8s-forge-studio"),
) -> None:
    """Run the local k8s-forge Studio web UI."""
    _print_step(f"Starting k8s-forge Studio at http://{host}:{port}")
    _print_hint("Studio is local-lab only and binds to 127.0.0.1 by default.")
    try:
        run_studio(host=host, port=port, workspace=workspace)
    except (StudioDependencyError, StudioHostError) as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(code=1) from exc


@app.command()
def discover(
    repo_path: Annotated[Path, typer.Argument(help="Repository path to inspect.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for discovery files."),
    ] = Path("generated-discovery"),
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing discovery files."),
    ] = False,
) -> None:
    """Statically discover a repository and scaffold app.yaml readiness."""
    _print_step(f"Discovering repository at {repo_path}...")
    _print_hint("This performs static analysis only.")
    _print_hint(
        "k8s-forge does not execute application code, install dependencies, "
        "build images, or deploy anything."
    )
    try:
        result = discover_repository(repo_path)
        generated = render_discovery_files(result, output, force=force)
    except (DiscoveryError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_step("Repository discovery completed.")
    _print_hint(f"Detected language: {', '.join(result.languages)}")
    framework = ", ".join(result.frameworks) if result.frameworks else "unknown"
    _print_hint(f"Detected framework: {framework}")
    _print_hint(f"Confidence: {result.confidence}")
    _print_hint(f"Recommended mode: {result.recommended_mode}")
    if result.warnings:
        _print_warning(f"Warnings: {len(result.warnings)}")
    if result.blockers:
        _print_warning(f"Blockers: {len(result.blockers)}")
    table = Table(title="Generated files")
    table.add_column("File", style="bold")
    for path in generated:
        table.add_row(str(path.relative_to(output)))
    console.print(table)
    _print_hint(
        "Generated discovery files are starter readiness artifacts. Review is "
        "required; they are not deployment-ready by default."
    )


@app.command()
def init(
    name: Annotated[str, typer.Argument(help="Application name for app.yaml.")],
    namespace: Annotated[
        str | None,
        typer.Option("--namespace", help="Kubernetes namespace."),
    ] = None,
    image: Annotated[
        str | None,
        typer.Option("--image", help="Container image."),
    ] = None,
    port: Annotated[
        int,
        typer.Option("--port", help="Container port."),
    ] = 8000,
    replicas: Annotated[
        int,
        typer.Option("--replicas", help="Deployment replica count."),
    ] = 1,
    service_port: Annotated[
        int,
        typer.Option("--service-port", help="Service port."),
    ] = 80,
    hpa: Annotated[
        bool,
        typer.Option("--hpa", help="Enable Horizontal Pod Autoscaler."),
    ] = False,
    hpa_min: Annotated[
        int,
        typer.Option("--hpa-min", help="HPA minimum replicas."),
    ] = 2,
    hpa_max: Annotated[
        int,
        typer.Option("--hpa-max", help="HPA maximum replicas."),
    ] = 6,
    hpa_cpu: Annotated[
        int,
        typer.Option("--hpa-cpu", help="HPA target CPU utilization percentage."),
    ] = 70,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output app.yaml path."),
    ] = Path("app.yaml"),
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing output file."),
    ] = False,
) -> None:
    """Create a starter app.yaml file."""
    if output.exists() and not force:
        console.print("[red]file already exists, use --force to overwrite[/red]")
        raise typer.Exit(code=1)

    data = _starter_config_data(
        name,
        namespace,
        image,
        port,
        replicas,
        service_port,
        hpa,
        hpa_min,
        hpa_max,
        hpa_cpu,
    )
    try:
        generated_config = AppConfig.model_validate(data)
    except ValidationError as exc:
        console.print(f"[red]Generated configuration is invalid: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if output.parent != Path(""):
        output.parent.mkdir(parents=True, exist_ok=True)
    _print_autoscaling_warning(generated_config)
    output.write_text(_starter_config_yaml(data), encoding="utf-8")
    console.print(f"[green]created {output}[/green]")


@app.command()
def explain(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
) -> None:
    """Explain a k8s-forge app.yaml file without generating or deploying."""
    _print_step(f"Explaining application configuration from {config_path}...")
    _print_hint(
        "This command is read-only. It validates app.yaml and explains its "
        "readiness meaning without rendering manifests or contacting a cluster."
    )
    try:
        loaded = load_app_config(config_path)
    except ConfigLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    report = build_explanation(loaded)
    console.print(render_explanation(report), markup=False)


@app.command()
def check(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
) -> None:
    """Validate an app.yaml configuration file."""
    _print_step("Validating application configuration...")
    _print_hint(
        "This step checks that app.yaml is structurally valid before "
        "generating Kubernetes manifests."
    )
    try:
        loaded = load_app_config(config_path)
    except ConfigLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print("[green]configuration is valid[/green]")
    _print_check_summary(loaded)
    _print_autoscaling_summary(loaded)
    _print_ingress_summary(loaded)
    _print_mesh_summary(loaded)
    if loaded.mesh.enabled:
        _print_mesh_validation_commands(loaded.app.namespace)
    _print_network_policy_summary(loaded)
    if loaded.networkPolicy.enabled:
        _print_network_policy_validation_commands(loaded)
    _print_policy_summary(loaded)
    if loaded.policy.enabled:
        _print_kyverno_prerequisite_warning()
        _print_policy_validation_commands(loaded)
    _print_supply_chain_summary(loaded)
    _print_ci_summary(loaded)
    _print_gitops_summary(loaded)
    _print_observability_summary(loaded)
    _print_logging_summary(loaded)
    _print_tracing_summary(loaded)
    _print_terraform_summary(loaded)
    _print_ansible_summary(loaded)
    _print_security_summary(loaded)
    _print_capstone_summary(loaded)
    _print_autoscaling_warning(loaded)


@app.command()
def render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for manifests."),
    ] = Path("generated"),
) -> None:
    """Render Kubernetes manifests."""
    _print_step("Rendering Kubernetes manifests from app.yaml...")
    _print_hint(
        "This does not contact the cluster. It only writes YAML files locally "
        "so they can be reviewed before applying them."
    )
    try:
        loaded, generated = _load_config_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_hpa_runtime_hint(loaded)
    _print_ingress_runtime_hint(loaded)
    _print_mesh_runtime_hint(loaded)
    _print_network_policy_runtime_hint(loaded)
    _print_policy_runtime_hint(loaded)
    if loaded.supplyChain.enabled:
        _print_supply_chain_render_hint(config_path)
    if loaded.ci.enabled:
        _print_ci_render_hint(config_path)
    if loaded.gitops.enabled:
        _print_gitops_render_hint(config_path)
    if loaded.observability.enabled:
        _print_observability_render_hint(config_path)
    if loaded.logging.enabled:
        _print_logging_render_hint(config_path)
    if loaded.tracing.enabled:
        _print_tracing_render_hint(config_path)
    if loaded.terraform.enabled:
        _print_terraform_render_hint(config_path)
    if loaded.ansible.enabled:
        _print_ansible_render_hint(config_path)
    if loaded.security.enabled:
        _print_security_render_hint(config_path)
    if loaded.capstone.enabled:
        _print_capstone_render_hint(config_path)
    _print_autoscaling_warning(loaded)
    console.print("[green]manifests generated[/green]")
    _print_render_summary(generated)
    _print_hint(f"Generated manifests are ready for review in {output}.")
    _print_hint("Review them before applying to the cluster.")


@app.command("dry-run")
def dry_run(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for manifests."),
    ] = Path("generated"),
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="kubectl timeout in seconds."),
    ] = 30,
) -> None:
    """Render manifests and run kubectl server-side dry-run."""
    try:
        loaded, generated = _load_config_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_render_summary(generated)
    _print_step("Running Kubernetes server-side dry-run...")
    _print_hint(
        "This sends the manifests to the Kubernetes API for validation, but "
        "does not persist changes."
    )
    _print_hint("No changes are persisted.")
    _print_autoscaling_warning(loaded)
    _warn_if_namespace_missing(loaded.app.namespace, timeout)
    if loaded.autoscaling.enabled:
        _print_step("Validating HPA manifest against the Kubernetes API...")
        _print_hint(
            "The HPA can be accepted even if metrics-server is not installed "
            "yet; in that case CPU targets may appear as <unknown>."
        )

    try:
        result = run_kubectl(
            ["apply", "--dry-run=server", "-f", str(output)], timeout=timeout
        )
    except KubectlError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_kubectl_result(result)
    combined = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        if _namespace_not_found(combined, loaded.app.namespace):
            _print_namespace_dry_run_failure(loaded.app.namespace, config_path, output)
        raise typer.Exit(code=result.returncode or 1)


@app.command()
def diff(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for manifests."),
    ] = Path("generated"),
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="kubectl timeout in seconds."),
    ] = 30,
) -> None:
    """Render manifests and run kubectl diff."""
    try:
        loaded, generated = _load_config_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_render_summary(generated)
    _print_autoscaling_warning(loaded)
    result = _run_kubectl_or_exit(["diff", "-f", str(output)], timeout, (0, 1))
    if result.returncode == 1:
        console.print("[yellow]kubectl diff found changes[/yellow]")


@app.command()
def apply(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for manifests."),
    ] = Path("generated"),
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Apply without interactive confirmation."),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="kubectl timeout in seconds."),
    ] = 30,
) -> None:
    """Render manifests and run controlled kubectl apply."""
    try:
        loaded, generated = _load_config_and_render(config_path, output)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_render_summary(generated)
    _print_step("Applying manifests to the current Kubernetes context...")
    _print_hint(
        "This will create or update Kubernetes resources to match the desired "
        "state declared in app.yaml."
    )
    _print_autoscaling_warning(loaded)
    _print_warning(
        "Current context will be modified. Review the generated manifests and "
        "the current context before continuing."
    )
    if not yes and not typer.confirm("Continue with kubectl apply?"):
        console.print("apply cancelled")
        return

    _run_kubectl_or_exit(["apply", "-f", str(output)], timeout)
    console.print("[green]Apply completed.[/green]")
    _print_hint(
        "Next steps: check rollout status, verify pods are Running, then test "
        "the Service."
    )


@app.command()
def status(
    name: Annotated[str, typer.Argument(help="Application name.")],
    namespace: Annotated[
        str,
        typer.Option("--namespace", "-n", help="Kubernetes namespace."),
    ],
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="kubectl timeout in seconds."),
    ] = 30,
) -> None:
    """Show application status from kubectl."""
    _print_step(
        f"Reading Kubernetes status for application {name} in namespace {namespace}..."
    )
    _print_hint(
        "This checks the Deployment, Pods, Service, and HPA associated with "
        "the app label."
    )
    _print_hint(
        "Deployment status shows whether Kubernetes reached the desired number "
        "of replicas."
    )
    _print_hint("Pods are the actual running instances of the application containers.")
    _print_hint(
        "If a pod is deleted, the Deployment should recreate it to maintain "
        "the desired state."
    )
    _print_hint(
        "The Service provides a stable network entry point even when pods are "
        "recreated."
    )
    _run_kubectl_or_exit(
        ["-n", namespace, "get", "deploy,po,svc", "-l", f"app={name}"],
        timeout,
    )

    _print_hint(
        "The HPA controls scaling between minReplicas and maxReplicas based "
        "on CPU metrics."
    )
    _print_hint(
        "If TARGETS shows <unknown>, metrics-server is missing or not ready yet."
    )
    hpa_result = _run_kubectl_or_exit(
        ["-n", namespace, "get", "hpa", "-l", f"app={name}"],
        timeout,
    )
    combined = f"{hpa_result.stdout}\n{hpa_result.stderr}".strip().lower()
    if not combined or "no resources found" in combined:
        _print_warning(f"No HPA found for app {name}.")
        _print_hint("This is normal when autoscaling.enabled is false.")


@app.command()
def doctor(
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Local command timeout in seconds."),
    ] = 30,
) -> None:
    """Check local Docker, kind, and kubectl prerequisites."""
    _print_step("Checking local DevSecOps toolchain...")
    _print_hint(
        "This verifies that the required command-line tools are available "
        "before using k8s-forge."
    )
    _print_step("Checking metrics-server availability...")
    _print_hint(
        "metrics-server is required for HPA CPU metrics. Without it, HPA "
        "TARGETS may stay <unknown>."
    )
    report = check_environment(timeout)
    _print_tool_checks(
        [
            report.docker,
            report.kind,
            report.kubectl,
            report.current_context,
            report.nodes,
            report.metrics_server,
            report.ingress_nginx,
            report.cert_manager,
            report.linkerd_cli,
            report.linkerd_namespace,
            report.linkerd_control_plane,
            report.linkerd_viz,
            report.cni_pods,
            report.network_policies,
            report.kyverno_namespace,
            report.kyverno_deployments,
            report.kyverno_crds,
            report.policy_reports,
            report.trivy,
            report.syft,
            report.cosign,
            report.git,
            report.terraform,
            report.ansible,
            report.ansible_lint,
            report.argocd_cli,
            report.argocd_namespace,
            report.argocd_deployments,
            report.argocd_applications_crd,
            report.servicemonitor_crd,
            report.prometheusrule_crd,
            report.monitoring_namespace,
            report.monitoring_deployments,
            report.monitoring_services,
            report.loki,
            report.grafana,
            report.promtail,
            report.alloy,
            report.tempo,
            report.otel_collector,
            report.tracing_grafana,
            report.jaeger,
        ]
    )
    if report.metrics_server.status == "OK":
        console.print("[green]metrics-server available.[/green]")
        _print_hint("HPA can read CPU and memory metrics from the cluster.")
    else:
        _print_warning("metrics-server not found.")
        _print_hint(
            "HPA manifests can still be created, but CPU-based scaling will "
            "not work until metrics-server is installed."
        )
    _print_step("Checking ingress-nginx readiness...")
    _print_hint(
        "Ingress resources need an ingress controller before traffic can "
        "reach the Service."
    )
    if report.ingress_nginx.status == "OK":
        console.print("[green]ingress-nginx available.[/green]")
    else:
        _print_warning("ingress-nginx not found.")
        _print_hint(
            "k8s-forge will not install ingress-nginx automatically; install "
            "it manually before testing Ingress traffic."
        )

    _print_step("Checking cert-manager readiness...")
    _print_hint(
        "cert-manager is required only when TLS certificate automation is enabled."
    )
    if report.cert_manager.status == "OK":
        console.print("[green]cert-manager available.[/green]")
    else:
        _print_warning("cert-manager not found.")
        _print_hint(
            "k8s-forge will not install cert-manager automatically; install "
            "it manually before using cert-manager annotations."
        )

    _print_step("Checking Linkerd service mesh readiness...")
    _print_hint(
        "Linkerd adds a sidecar proxy to injected pods so service-to-service "
        "traffic can be observed and secured."
    )
    if (
        report.linkerd_cli.status == "OK"
        and report.linkerd_namespace.status == "OK"
        and report.linkerd_control_plane.status == "OK"
    ):
        console.print("[green]Linkerd control plane appears to be available.[/green]")
    else:
        _print_warning("Linkerd does not appear to be installed in this cluster.")
        _print_hint("k8s-forge will not install it automatically.")
        _print_hint(
            "Install and validate Linkerd manually before expecting sidecars "
            "or mesh metrics."
        )
    if report.linkerd_viz.status == "OK":
        console.print("[green]Linkerd Viz appears to be available.[/green]")
    else:
        _print_hint("Linkerd Viz is optional and was not detected.")

    _print_cni_diagnostics(report)
    _print_kyverno_diagnostics(report)
    _print_supply_chain_diagnostics(report)
    _print_ci_diagnostics(report)
    _print_argocd_diagnostics(report)
    _print_observability_diagnostics(report)
    _print_logging_diagnostics(report)
    _print_tracing_diagnostics(report)
    _print_terraform_diagnostics(report)
    _print_ansible_diagnostics(report)

    if report.ready:
        console.print("[green]Ready for local kind workflows.[/green]")
    else:
        console.print(
            "[yellow]Missing or failing prerequisites. "
            "Install or fix the tools above.[/yellow]"
        )


@cluster_app.command("create")
def cluster_create(
    name: Annotated[
        str,
        typer.Option("--name", help="kind cluster name."),
    ] = "devsecops",
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Local command timeout in seconds."),
    ] = 120,
) -> None:
    """Create a local kind cluster if it does not already exist."""
    clusters = _kind_clusters_or_exit(timeout)
    if name in clusters:
        console.print(
            f"[yellow]kind cluster {name} already exists; skipping create.[/yellow]"
        )
        _print_context_and_nodes(timeout)
        return

    try:
        result = create_kind_cluster(name, timeout)
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    _run_local_or_exit(result)

    console.print("[bold]Waiting for nodes to become Ready[/bold]")
    try:
        wait_result = wait_for_nodes_ready(timeout)
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("[yellow]Check cluster state with: kubectl get nodes[/yellow]")
        console.print("[yellow]Inspect system pods with: kubectl get pods -A[/yellow]")
        raise typer.Exit(code=1) from exc
    _print_local_result(wait_result)
    if not wait_result.ok:
        console.print(
            "[red]Timed out or failed while waiting for nodes to be Ready.[/red]"
        )
        console.print("[yellow]Check cluster state with: kubectl get nodes[/yellow]")
        console.print("[yellow]Inspect system pods with: kubectl get pods -A[/yellow]")
        raise typer.Exit(code=wait_result.returncode or 1)

    _print_context_and_nodes(timeout)


@cluster_app.command("status")
def cluster_status(
    name: Annotated[
        str,
        typer.Option("--name", help="kind cluster name."),
    ] = "devsecops",
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Local command timeout in seconds."),
    ] = 30,
) -> None:
    """Show local kind cluster status."""
    _print_step("Checking kind cluster status...")
    _print_hint("A Ready node means Kubernetes can schedule and run pods.")
    clusters = _kind_clusters_or_exit(timeout)
    if name not in clusters:
        console.print(f"[red]kind cluster {name} does not exist.[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]kind cluster {name} exists.[/green]")
    _print_context_and_nodes(timeout)


@cluster_app.command("delete")
def cluster_delete(
    name: Annotated[
        str,
        typer.Option("--name", help="kind cluster name."),
    ] = "devsecops",
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Delete without interactive confirmation."),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Local command timeout in seconds."),
    ] = 120,
) -> None:
    """Delete a local kind cluster."""
    if not yes and not typer.confirm(f"Delete kind cluster {name}?"):
        console.print("cluster delete cancelled")
        return

    try:
        result = delete_kind_cluster(name, timeout)
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    _run_local_or_exit(result)


@image_app.command("load")
def image_load(
    image: Annotated[str, typer.Argument(help="Local Docker image to load.")],
    cluster: Annotated[
        str,
        typer.Option("--cluster", help="kind cluster name."),
    ] = "devsecops",
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Local command timeout in seconds."),
    ] = 120,
) -> None:
    """Load a local Docker image into a kind cluster."""
    _print_step("Loading Docker image into kind cluster...")
    _print_hint(
        "kind nodes use their own containerd image store. Loading the image "
        "makes it available to pods without pushing it to a registry."
    )
    try:
        inspect = docker_image_inspect(image, timeout)
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not inspect.ok:
        _print_local_result(inspect)
        console.print(f"[red]Docker image {image} was not found locally.[/red]")
        raise typer.Exit(code=1)

    try:
        result = load_docker_image(image, cluster, timeout)
    except LocalCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    _run_local_or_exit(result)
    console.print(f"[green]Loaded {image} into kind cluster {cluster}.[/green]")


@helm_app.command("render")
def helm_render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for charts."),
    ] = Path("charts"),
    chart_name: Annotated[
        str | None,
        typer.Option("--chart-name", help="Generated chart directory name."),
    ] = None,
) -> None:
    """Render a local Helm chart from app.yaml."""
    _print_step("Rendering a Helm chart from app.yaml...")
    _print_hint(
        "Helm packages Kubernetes manifests into a reusable and configurable chart."
    )
    _print_hint("This step does not contact the cluster and does not install anything.")
    try:
        loaded = load_app_config(config_path)
        generated = render_helm_chart(loaded, output, chart_name)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    resolved_chart_name = chart_name or loaded.app.name
    chart_dir = output / resolved_chart_name
    console.print(f"[green]Helm chart generated in {chart_dir}.[/green]")
    _print_helm_chart_summary(generated)
    _print_helm_ingress_hint(loaded)
    _print_mesh_runtime_hint(loaded)
    _print_network_policy_runtime_hint(loaded)
    _print_policy_runtime_hint(loaded)
    _print_warning(
        "If raw Kubernetes resources already exist from k8s-forge apply, Helm "
        "may refuse to import them because of ownership metadata."
    )
    _print_hint(
        "For a clean lab migration, delete the raw resources first or use a "
        "fresh namespace."
    )
    _print_hint("Next validation commands:")
    _print_hint(f"  helm lint {chart_dir}")
    _print_hint(
        f"  helm template {resolved_chart_name} {chart_dir} -n {loaded.app.namespace}"
    )
    _print_hint(
        "  helm upgrade --install "
        f"{resolved_chart_name} {chart_dir} -n {loaded.app.namespace} "
        "--create-namespace"
    )


@supply_chain_app.command("render")
def supply_chain_render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for supply chain files."),
    ] = Path("generated-supply-chain"),
) -> None:
    """Render supply chain readiness scripts from app.yaml."""
    _print_step("Rendering supply chain readiness files from app.yaml...")
    _print_hint(
        "This creates local helper scripts for image scanning, SBOM generation, "
        "and optional signing."
    )
    _print_hint("This step does not install Trivy, Syft, or Cosign.")
    try:
        loaded = load_app_config(config_path)
    except ConfigLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not loaded.supplyChain.enabled:
        _print_hint("Supply chain readiness is disabled in app.yaml.")
        _print_hint("No supply chain files were generated.")
        return

    try:
        generated = render_supply_chain_files(loaded, output)
    except RenderError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Supply chain files generated in {output}.[/green]")
    _print_supply_chain_summary(loaded)
    _print_supply_chain_summary_table(generated)
    _print_supply_chain_next_steps(generated)


@ci_app.command("render")
def ci_render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for CI files."),
    ] = Path("generated-ci"),
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite generated CI files if they exist."),
    ] = False,
) -> None:
    """Render GitHub Actions CI readiness files from app.yaml."""
    _print_step("Rendering GitHub Actions CI readiness files from app.yaml...")
    _print_hint(
        "This creates readable workflow files for Python checks and container "
        "supply-chain validation."
    )
    _print_hint(
        "This step does not push code, publish images, deploy Kubernetes "
        "resources, or create secrets."
    )
    if _is_direct_workflows_output(output):
        _print_warning(
            "The output target is .github/workflows/. Existing workflow files "
            "will not be overwritten unless --force is used."
        )

    try:
        loaded = load_app_config(config_path)
    except ConfigLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not loaded.ci.enabled:
        _print_hint("CI readiness is disabled in app.yaml.")
        _print_hint("No CI workflow files were generated.")
        return

    try:
        generated = render_ci_files(loaded, output, force=force)
    except RenderError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]CI files generated in {output}.[/green]")
    _print_ci_summary(loaded)
    _print_ci_summary_table(generated, output)
    _print_ci_next_steps(output)


@gitops_app.command("render")
def gitops_render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for GitOps files."),
    ] = Path("generated-gitops"),
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite generated GitOps files if they exist."),
    ] = False,
) -> None:
    """Render ArgoCD GitOps readiness files from app.yaml."""
    _print_step("Rendering GitOps readiness files from app.yaml...")
    _print_hint("This creates local ArgoCD manifest examples.")
    _print_hint("This step does not contact the cluster and does not install ArgoCD.")
    try:
        loaded = load_app_config(config_path)
    except ConfigLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not loaded.gitops.enabled:
        _print_hint("GitOps readiness is disabled in app.yaml.")
        _print_hint("No GitOps files were generated.")
        return

    try:
        generated = render_gitops_files(loaded, output, force=force)
    except RenderError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]GitOps files generated in {output}.[/green]")
    _print_gitops_summary(loaded)
    _print_gitops_summary_table(generated, output)
    _print_gitops_next_steps(output)


@observability_app.command("render")
def observability_render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o", help="Output directory for observability files."
        ),
    ] = Path("generated-observability"),
    force: Annotated[
        bool,
        typer.Option(
            "--force", help="Overwrite generated observability files if they exist."
        ),
    ] = False,
) -> None:
    """Render observability readiness files from app.yaml."""
    _print_step("Rendering observability readiness files from app.yaml...")
    _print_hint("This creates local Prometheus and Grafana examples.")
    _print_hint(
        "This step does not contact the cluster and does not install monitoring "
        "components."
    )
    try:
        loaded = load_app_config(config_path)
    except ConfigLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not loaded.observability.enabled:
        _print_hint("Observability readiness is disabled in app.yaml.")
        _print_hint("No observability files were generated.")
        return

    try:
        generated = render_observability_files(loaded, output, force=force)
    except RenderError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Observability files generated in {output}.[/green]")
    _print_observability_summary(loaded)
    _print_hint(f"Grafana dashboard title: {resolve_dashboard_title(loaded)}")
    _print_observability_summary_table(generated, output)
    _print_observability_next_steps(output)


@logging_app.command("render")
def logging_render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for logging files."),
    ] = Path("generated-logging"),
    force: Annotated[
        bool,
        typer.Option(
            "--force", help="Overwrite generated logging files if they exist."
        ),
    ] = False,
) -> None:
    """Render logging readiness files from app.yaml."""
    _print_step("Rendering logging readiness files from app.yaml...")
    _print_hint("This creates local Loki, LogQL, and Grafana examples.")
    _print_hint(
        "This step does not contact the cluster and does not install logging "
        "components."
    )
    try:
        loaded = load_app_config(config_path)
    except ConfigLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not loaded.logging.enabled:
        _print_hint("Logging readiness is disabled in app.yaml.")
        _print_hint("No logging files were generated.")
        return

    try:
        generated = render_logging_files(loaded, output, force=force)
    except RenderError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Logging files generated in {output}.[/green]")
    _print_logging_summary(loaded)
    _print_hint(
        f"Grafana logs dashboard title: {resolve_logging_dashboard_title(loaded)}"
    )
    _print_logging_summary_table(generated, output)
    _print_logging_next_steps(output)


@tracing_app.command("render")
def tracing_render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for tracing files."),
    ] = Path("generated-tracing"),
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing tracing files."),
    ] = False,
) -> None:
    """Render local tracing readiness files."""
    _print_step("Rendering tracing readiness files from app.yaml...")
    _print_hint(
        "This creates local OpenTelemetry, OTLP, Tempo, TraceQL, and Grafana examples."
    )
    _print_hint(
        "This step does not contact the cluster and does not install tracing "
        "components."
    )
    try:
        loaded = load_app_config(config_path)
        generated = render_tracing_files(loaded, output, force=force)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not loaded.tracing.enabled:
        _print_hint("Tracing readiness is disabled; no tracing files were generated.")
        return

    _print_tracing_summary(loaded)
    _print_hint(f"Tracing service name: {resolve_tracing_service_name(loaded)}")
    _print_hint(f"Grafana dashboard title: {resolve_tracing_dashboard_title(loaded)}")
    console.print(f"[green]Tracing files generated in {output}.[/green]")
    _print_tracing_summary_table(generated, output)
    _print_tracing_next_steps(output)


@terraform_app.command("render")
def terraform_render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for Terraform files."),
    ] = Path("generated-terraform"),
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing Terraform files."),
    ] = False,
) -> None:
    """Render local Terraform readiness files."""
    _print_step("Rendering Terraform readiness files from app.yaml...")
    _print_hint("This creates local Infrastructure as Code examples.")
    _print_hint(
        "This step does not contact the cluster, does not contact any cloud "
        "provider, and does not run Terraform."
    )
    try:
        loaded = load_app_config(config_path)
        generated = render_terraform_files(loaded, output, force=force)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not loaded.terraform.enabled:
        _print_hint(
            "Terraform readiness is disabled; no Terraform files were generated."
        )
        return

    _print_terraform_summary(loaded)
    console.print(f"[green]Terraform files generated in {output}.[/green]")
    _print_terraform_summary_table(generated, output)
    _print_terraform_next_steps(output)


@ansible_app.command("render")
def ansible_render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for Ansible files."),
    ] = Path("generated-ansible"),
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing Ansible files."),
    ] = False,
) -> None:
    """Render local Ansible readiness files."""
    _print_step("Rendering Ansible readiness files from app.yaml...")
    _print_hint("This creates local automation examples.")
    _print_hint(
        "This step does not contact hosts, does not open SSH connections, "
        "and does not run Ansible."
    )
    try:
        loaded = load_app_config(config_path)
        generated = render_ansible_files(loaded, output, force=force)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not loaded.ansible.enabled:
        _print_hint("Ansible readiness is disabled; no Ansible files were generated.")
        return

    _print_ansible_summary(loaded)
    console.print(f"[green]Ansible files generated in {output}.[/green]")
    _print_ansible_summary_table(generated, output)
    _print_ansible_next_steps(output, loaded.ansible.playbook.name)


@security_app.command("render")
def security_render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o", help="Output directory for Security Audit files."
        ),
    ] = Path("generated-security-audit"),
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing Security Audit files."),
    ] = False,
) -> None:
    """Render local Security Audit readiness files."""
    _print_step("Rendering Security Audit readiness files from app.yaml...")
    _print_hint("This creates a local security review and checklist.")
    _print_hint(
        "This step does not run scanners, does not contact the cluster, "
        "and does not modify any external system."
    )
    try:
        loaded = load_app_config(config_path)
        generated = render_security_files(loaded, output, force=force)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not loaded.security.enabled:
        _print_hint(
            "Security Audit readiness is disabled; no Security Audit files were "
            "generated."
        )
        return

    _print_security_summary(loaded)
    console.print(f"[green]Security Audit files generated in {output}.[/green]")
    _print_security_summary_table(generated, output)
    _print_security_next_steps(output)


@capstone_app.command("render")
def capstone_render(
    config_path: Annotated[Path, typer.Argument(help="Path to app.yaml.")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for Capstone files."),
    ] = Path("generated-capstone"),
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing Capstone files."),
    ] = False,
) -> None:
    """Render local Capstone readiness files."""
    _print_step("Rendering Capstone readiness files from app.yaml...")
    _print_hint("This creates a final local DevSecOps lab summary.")
    _print_hint(
        "This step does not contact the cluster, does not run deployment "
        "commands, and does not modify any external system."
    )
    try:
        loaded = load_app_config(config_path)
        generated = render_capstone_files(loaded, output, force=force)
    except (ConfigLoadError, RenderError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not loaded.capstone.enabled:
        _print_hint("Capstone readiness is disabled; no Capstone files were generated.")
        return

    _print_capstone_summary(loaded)
    _print_hint(f"Capstone report title: {resolve_capstone_report_title(loaded)}")
    console.print(f"[green]Capstone files generated in {output}.[/green]")
    _print_capstone_summary_table(generated, output)
    _print_capstone_next_steps(output)


app.add_typer(cluster_app, name="cluster")
app.add_typer(image_app, name="image")
app.add_typer(helm_app, name="helm")
app.add_typer(supply_chain_app, name="supply-chain")
app.add_typer(ci_app, name="ci")
app.add_typer(gitops_app, name="gitops")
app.add_typer(observability_app, name="observability")
app.add_typer(logging_app, name="logging")
app.add_typer(tracing_app, name="tracing")
app.add_typer(terraform_app, name="terraform")
app.add_typer(ansible_app, name="ansible")
app.add_typer(security_app, name="security")
app.add_typer(capstone_app, name="capstone")
