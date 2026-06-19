import subprocess
from typing import Any

import pytest

from k8s_forge.exceptions import KubectlError
from k8s_forge.kubectl import run_kubectl


def test_run_kubectl_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_kubectl(["version", "--client"], timeout=12)

    assert result.ok is True
    assert result.command == ["kubectl", "version", "--client"]
    assert result.stdout == "ok\n"
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["timeout"] == 12


def test_run_kubectl_nonzero_return_code(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, "", "kubernetes error")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_kubectl(["apply", "-f", "generated"], timeout=30)

    assert result.ok is False
    assert result.returncode == 2
    assert result.stderr == "kubernetes error"


def test_run_kubectl_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, timeout=1, output="partial")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(KubectlError, match="timed out after 1 seconds") as exc_info:
        run_kubectl(["get", "pods"], timeout=1)

    assert "partial" in str(exc_info.value)


def test_run_kubectl_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(
        KubectlError, match="kubectl executable was not found"
    ) as exc_info:
        run_kubectl(["get", "pods"])

    message = str(exc_info.value)
    assert "Install kubectl" in message
    assert "PATH" in message
