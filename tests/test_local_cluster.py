import subprocess
from typing import Any

import pytest

from k8s_forge.exceptions import LocalCommandError
from k8s_forge.local_cluster import (
    check_environment,
    get_kind_clusters,
    run_local_command,
    wait_for_nodes_ready,
)


def test_run_local_command_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_local_command(["kind", "version"], timeout=11)

    assert result.ok is True
    assert result.stdout == "ok"
    assert captured["command"] == ["kind", "version"]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["timeout"] == 11


def test_run_local_command_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(LocalCommandError, match="Install docker"):
        run_local_command(["docker", "version"])


def test_run_local_command_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, timeout=3, stderr="slow")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(LocalCommandError, match="timed out after 3 seconds"):
        run_local_command(["kubectl", "get", "nodes"], timeout=3)


def test_check_environment_reports_multiple_missing_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[0] in {"docker", "kind", "kubectl"}:
            raise FileNotFoundError
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = check_environment()

    assert report.docker.status == "missing"
    assert report.kind.status == "missing"
    assert report.kubectl.status == "missing"
    assert report.current_context.status == "unavailable"
    assert report.nodes.status == "unavailable"
    assert report.ready is False


def test_get_kind_clusters_parses_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "devsecops\nother\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert get_kind_clusters() == ["devsecops", "other"]


def test_wait_for_nodes_ready_calls_kubectl_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "nodes ready", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = wait_for_nodes_ready(timeout=120)

    assert result.ok is True
    assert captured["command"] == [
        "kubectl",
        "wait",
        "--for=condition=Ready",
        "nodes",
        "--all",
        "--timeout=120s",
    ]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["timeout"] == 120
