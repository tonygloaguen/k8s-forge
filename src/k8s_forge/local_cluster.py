"""Local Docker/kind/kubectl helper commands."""

import subprocess  # nosec B404
from dataclasses import dataclass
from typing import Literal

from k8s_forge.exceptions import LocalCommandError

CheckStatus = Literal["OK", "missing", "error", "unavailable"]


@dataclass(frozen=True)
class LocalCommandResult:
    """Captured result from a local command."""

    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        """Return True when the command exited successfully."""
        return self.returncode == 0


@dataclass(frozen=True)
class ToolCheck:
    """Status for one local prerequisite or cluster query."""

    name: str
    status: CheckStatus
    details: str = ""


@dataclass(frozen=True)
class DoctorReport:
    """Combined local prerequisite check results."""

    docker: ToolCheck
    kind: ToolCheck
    kubectl: ToolCheck
    current_context: ToolCheck
    nodes: ToolCheck
    metrics_server: ToolCheck
    ingress_nginx: ToolCheck
    cert_manager: ToolCheck
    linkerd_cli: ToolCheck
    linkerd_namespace: ToolCheck
    linkerd_control_plane: ToolCheck
    linkerd_viz: ToolCheck
    cni_pods: ToolCheck
    network_policies: ToolCheck
    kyverno_namespace: ToolCheck
    kyverno_deployments: ToolCheck
    kyverno_crds: ToolCheck
    policy_reports: ToolCheck

    @property
    def ready(self) -> bool:
        """Return True when local tools required for kind workflows are available."""
        return all(
            check.status == "OK" for check in (self.docker, self.kind, self.kubectl)
        )


def _text_output(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    if isinstance(value, str):
        return value
    return ""


def _compact_output(result: LocalCommandResult) -> str:
    return (result.stdout or result.stderr).strip()


def run_local_command(command: list[str], timeout: int = 30) -> LocalCommandResult:
    """Run a local command with captured output and no shell."""
    try:
        completed = subprocess.run(  # nosec B603
            command,
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        tool = command[0] if command else "command"
        msg = (
            f"{tool} executable was not found. "
            f"Install {tool} and ensure it is available in PATH."
        )
        raise LocalCommandError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        stdout = _text_output(exc.stdout)
        stderr = _text_output(exc.stderr)
        details = stderr or stdout
        suffix = f" Output: {details}" if details else ""
        command_text = " ".join(command)
        msg = f"Command timed out after {timeout} seconds: {command_text}.{suffix}"
        raise LocalCommandError(msg) from exc

    return LocalCommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def check_command(name: str, command: list[str], timeout: int = 30) -> ToolCheck:
    """Run one diagnostic command and convert it to a ToolCheck."""
    try:
        result = run_local_command(command, timeout=timeout)
    except LocalCommandError as exc:
        status: CheckStatus = "missing" if "not found" in str(exc) else "error"
        return ToolCheck(name, status, str(exc))

    if result.ok:
        return ToolCheck(name, "OK", _compact_output(result))
    return ToolCheck(name, "error", _compact_output(result))


def _looks_missing(details: str) -> bool:
    normalized = details.lower()
    return "not found" in normalized or "notfound" in normalized


def _linkerd_optional_check(
    name: str, command: list[str], timeout: int = 30
) -> ToolCheck:
    check = check_command(name, command, timeout)
    if check.status == "error" and _looks_missing(check.details):
        return ToolCheck(name, "missing", check.details)
    return check


def _linkerd_control_plane_check(timeout: int = 30) -> ToolCheck:
    check = _linkerd_optional_check(
        "Linkerd control plane",
        ["kubectl", "-n", "linkerd", "get", "deploy"],
        timeout,
    )
    if check.status == "OK" and "no resources found" in check.details.lower():
        return ToolCheck("Linkerd control plane", "missing", check.details)
    return check


def _kyverno_crd_check(timeout: int = 30) -> ToolCheck:
    check = check_command("Kyverno CRDs", ["kubectl", "get", "crd"], timeout)
    if check.status != "OK":
        if _looks_missing(check.details):
            return ToolCheck("Kyverno CRDs", "missing", check.details)
        return check
    if "kyverno.io" not in check.details.lower():
        return ToolCheck("Kyverno CRDs", "missing", "No kyverno.io CRDs found")
    return check


def _policy_reports_check(timeout: int = 30) -> ToolCheck:
    check = _linkerd_optional_check(
        "PolicyReports",
        ["kubectl", "get", "policyreport", "--all-namespaces"],
        timeout,
    )
    if check.status == "error":
        normalized = check.details.lower()
        if (
            "doesn't have a resource type" in normalized
            or "does not have a resource type" in normalized
        ):
            return ToolCheck(
                "PolicyReports",
                "missing",
                "PolicyReport resource type is not available because "
                "Kyverno CRDs are not installed.",
            )
    return check


def check_environment(timeout: int = 30) -> DoctorReport:
    """Check Docker, kind, kubectl, current context, and nodes."""
    docker = check_command("Docker", ["docker", "version"], timeout)
    kind = check_command("kind", ["kind", "version"], timeout)
    kubectl = check_command("kubectl", ["kubectl", "version", "--client"], timeout)
    linkerd_cli = check_command(
        "Linkerd CLI", ["linkerd", "version", "--client"], timeout
    )

    if kubectl.status == "OK":
        current_context = check_command(
            "current context", ["kubectl", "config", "current-context"], timeout
        )
        nodes = check_command("nodes", ["kubectl", "get", "nodes"], timeout)
        metrics_server = check_command(
            "metrics-server",
            ["kubectl", "-n", "kube-system", "get", "deploy", "metrics-server"],
            timeout,
        )
        ingress_nginx = check_command(
            "ingress-nginx",
            [
                "kubectl",
                "-n",
                "ingress-nginx",
                "get",
                "deploy",
                "ingress-nginx-controller",
            ],
            timeout,
        )
        cert_manager = check_command(
            "cert-manager",
            ["kubectl", "-n", "cert-manager", "get", "deploy", "cert-manager"],
            timeout,
        )
        linkerd_namespace = _linkerd_optional_check(
            "Linkerd namespace", ["kubectl", "get", "ns", "linkerd"], timeout
        )
        if linkerd_namespace.status == "OK":
            linkerd_control_plane = _linkerd_control_plane_check(timeout)
        else:
            linkerd_control_plane = ToolCheck(
                "Linkerd control plane",
                "missing",
                "Linkerd namespace is missing; control plane was not checked",
            )
        linkerd_viz = _linkerd_optional_check(
            "Linkerd Viz", ["kubectl", "get", "ns", "linkerd-viz"], timeout
        )
        cni_pods = check_command(
            "CNI pods", ["kubectl", "-n", "kube-system", "get", "pods"], timeout
        )
        network_policies = check_command(
            "NetworkPolicy objects",
            ["kubectl", "get", "networkpolicy", "--all-namespaces"],
            timeout,
        )
        kyverno_namespace = _linkerd_optional_check(
            "Kyverno namespace", ["kubectl", "get", "ns", "kyverno"], timeout
        )
        if kyverno_namespace.status == "OK":
            kyverno_deployments = _linkerd_optional_check(
                "Kyverno deployments",
                ["kubectl", "-n", "kyverno", "get", "deploy"],
                timeout,
            )
        else:
            kyverno_deployments = ToolCheck(
                "Kyverno deployments",
                "missing",
                "Kyverno namespace is missing; deployments were not checked",
            )
        kyverno_crds = _kyverno_crd_check(timeout)
        policy_reports = _policy_reports_check(timeout)
    else:
        current_context = ToolCheck(
            "current context", "unavailable", "kubectl is not available"
        )
        nodes = ToolCheck("nodes", "unavailable", "kubectl is not available")
        metrics_server = ToolCheck(
            "metrics-server", "unavailable", "kubectl is not available"
        )
        ingress_nginx = ToolCheck(
            "ingress-nginx", "unavailable", "kubectl is not available"
        )
        cert_manager = ToolCheck(
            "cert-manager", "unavailable", "kubectl is not available"
        )
        linkerd_namespace = ToolCheck(
            "Linkerd namespace", "unavailable", "kubectl is not available"
        )
        linkerd_control_plane = ToolCheck(
            "Linkerd control plane", "unavailable", "kubectl is not available"
        )
        linkerd_viz = ToolCheck(
            "Linkerd Viz", "unavailable", "kubectl is not available"
        )
        cni_pods = ToolCheck("CNI pods", "unavailable", "kubectl is not available")
        network_policies = ToolCheck(
            "NetworkPolicy objects", "unavailable", "kubectl is not available"
        )
        kyverno_namespace = ToolCheck(
            "Kyverno namespace", "unavailable", "kubectl is not available"
        )
        kyverno_deployments = ToolCheck(
            "Kyverno deployments", "unavailable", "kubectl is not available"
        )
        kyverno_crds = ToolCheck(
            "Kyverno CRDs", "unavailable", "kubectl is not available"
        )
        policy_reports = ToolCheck(
            "PolicyReports", "unavailable", "kubectl is not available"
        )

    return DoctorReport(
        docker,
        kind,
        kubectl,
        current_context,
        nodes,
        metrics_server,
        ingress_nginx,
        cert_manager,
        linkerd_cli,
        linkerd_namespace,
        linkerd_control_plane,
        linkerd_viz,
        cni_pods,
        network_policies,
        kyverno_namespace,
        kyverno_deployments,
        kyverno_crds,
        policy_reports,
    )


def get_kind_clusters(timeout: int = 30) -> list[str]:
    """Return the kind cluster names visible locally."""
    result = run_local_command(["kind", "get", "clusters"], timeout=timeout)
    if not result.ok:
        details = _compact_output(result) or "kind get clusters failed"
        raise LocalCommandError(details)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def create_kind_cluster(name: str, timeout: int = 120) -> LocalCommandResult:
    """Create a kind cluster by name."""
    return run_local_command(["kind", "create", "cluster", "--name", name], timeout)


def delete_kind_cluster(name: str, timeout: int = 120) -> LocalCommandResult:
    """Delete a kind cluster by name."""
    return run_local_command(["kind", "delete", "cluster", "--name", name], timeout)


def current_context(timeout: int = 30) -> LocalCommandResult:
    """Return the current kubectl context."""
    return run_local_command(["kubectl", "config", "current-context"], timeout)


def get_nodes(timeout: int = 30) -> LocalCommandResult:
    """Return Kubernetes nodes visible from kubectl."""
    return run_local_command(["kubectl", "get", "nodes"], timeout)


def wait_for_nodes_ready(timeout: int = 120) -> LocalCommandResult:
    """Wait until all Kubernetes nodes visible from kubectl are Ready."""
    return run_local_command(
        [
            "kubectl",
            "wait",
            "--for=condition=Ready",
            "nodes",
            "--all",
            f"--timeout={timeout}s",
        ],
        timeout=timeout,
    )


def docker_image_inspect(image: str, timeout: int = 30) -> LocalCommandResult:
    """Inspect a local Docker image."""
    return run_local_command(["docker", "image", "inspect", image], timeout)


def load_docker_image(
    image: str, cluster: str, timeout: int = 120
) -> LocalCommandResult:
    """Load a local Docker image into a kind cluster."""
    return run_local_command(
        ["kind", "load", "docker-image", image, "--name", cluster], timeout
    )
