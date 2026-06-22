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


def check_environment(timeout: int = 30) -> DoctorReport:
    """Check Docker, kind, kubectl, current context, and nodes."""
    docker = check_command("Docker", ["docker", "version"], timeout)
    kind = check_command("kind", ["kind", "version"], timeout)
    kubectl = check_command("kubectl", ["kubectl", "version", "--client"], timeout)

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
    else:
        current_context = ToolCheck(
            "current context", "unavailable", "kubectl is not available"
        )
        nodes = ToolCheck("nodes", "unavailable", "kubectl is not available")
        metrics_server = ToolCheck(
            "metrics-server", "unavailable", "kubectl is not available"
        )

    return DoctorReport(docker, kind, kubectl, current_context, nodes, metrics_server)


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
