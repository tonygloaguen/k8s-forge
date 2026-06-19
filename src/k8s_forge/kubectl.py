"""Safe kubectl command execution."""

import subprocess  # nosec B404
from dataclasses import dataclass

from k8s_forge.exceptions import KubectlError


@dataclass(frozen=True)
class KubectlResult:
    """Captured result from a kubectl command."""

    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        """Return True when kubectl exited successfully."""
        return self.returncode == 0


def _text_output(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    if isinstance(value, str):
        return value
    return ""


def run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
    """Run kubectl with captured output and no shell."""
    command = ["kubectl", *args]
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
        msg = "kubectl executable was not found in PATH."
        raise KubectlError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        stdout = _text_output(exc.stdout)
        stderr = _text_output(exc.stderr)
        details = stderr or stdout
        suffix = f" Output: {details}" if details else ""
        msg = f"kubectl timed out after {timeout} seconds.{suffix}"
        raise KubectlError(msg) from exc

    return KubectlResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
