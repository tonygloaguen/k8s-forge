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

METRICS_SERVER_COMMAND = [
    "kubectl",
    "-n",
    "kube-system",
    "get",
    "deploy",
    "metrics-server",
]
INGRESS_NGINX_COMMAND = [
    "kubectl",
    "-n",
    "ingress-nginx",
    "get",
    "deploy",
    "ingress-nginx-controller",
]
CERT_MANAGER_COMMAND = [
    "kubectl",
    "-n",
    "cert-manager",
    "get",
    "deploy",
    "cert-manager",
]

LINKERD_CLI_COMMAND = ["linkerd", "version", "--client"]
LINKERD_NAMESPACE_COMMAND = ["kubectl", "get", "ns", "linkerd"]
LINKERD_CONTROL_PLANE_COMMAND = ["kubectl", "-n", "linkerd", "get", "deploy"]
LINKERD_VIZ_COMMAND = ["kubectl", "get", "ns", "linkerd-viz"]


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
    assert report.metrics_server.status == "unavailable"
    assert report.ingress_nginx.status == "unavailable"
    assert report.cert_manager.status == "unavailable"
    assert report.linkerd_cli.status == "OK"
    assert report.linkerd_namespace.status == "unavailable"
    assert report.linkerd_control_plane.status == "unavailable"
    assert report.linkerd_viz.status == "unavailable"
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


def test_check_environment_reports_metrics_server_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        outputs = {
            ("docker", "version"): "Docker",
            ("kind", "version"): "kind",
            ("kubectl", "version", "--client"): "kubectl",
            ("kubectl", "config", "current-context"): "kind-devsecops",
            ("kubectl", "get", "nodes"): "node Ready",
            (
                "kubectl",
                "-n",
                "kube-system",
                "get",
                "deploy",
                "metrics-server",
            ): "metrics-server",
            (
                "kubectl",
                "-n",
                "ingress-nginx",
                "get",
                "deploy",
                "ingress-nginx-controller",
            ): "ingress-nginx-controller",
            (
                "kubectl",
                "-n",
                "cert-manager",
                "get",
                "deploy",
                "cert-manager",
            ): "cert-manager",
            ("linkerd", "version", "--client"): "Client version: stable",
            ("kubectl", "get", "ns", "linkerd"): "linkerd",
            ("kubectl", "-n", "linkerd", "get", "deploy"): "linkerd-control-plane",
            ("kubectl", "get", "ns", "linkerd-viz"): "linkerd-viz",
        }
        return subprocess.CompletedProcess(command, 0, outputs[tuple(command)], "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = check_environment()

    assert report.metrics_server.status == "OK"
    assert report.metrics_server.details == "metrics-server"
    assert report.ingress_nginx.status == "OK"
    assert report.cert_manager.status == "OK"
    assert report.linkerd_cli.status == "OK"
    assert report.linkerd_namespace.status == "OK"
    assert report.linkerd_control_plane.status == "OK"
    assert report.linkerd_viz.status == "OK"


def test_check_environment_reports_metrics_server_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == METRICS_SERVER_COMMAND:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = check_environment()

    assert report.metrics_server.status == "error"
    assert report.metrics_server.details == "not found"


def test_check_environment_reports_ingress_nginx_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == INGRESS_NGINX_COMMAND:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = check_environment()

    assert report.ingress_nginx.status == "error"
    assert report.ingress_nginx.details == "not found"
    assert report.ready is True


def test_check_environment_reports_cert_manager_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == CERT_MANAGER_COMMAND:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = check_environment()

    assert report.cert_manager.status == "error"
    assert report.cert_manager.details == "not found"
    assert report.ready is True


def test_check_environment_reports_linkerd_cli_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == LINKERD_CLI_COMMAND:
            raise FileNotFoundError
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = check_environment()

    assert report.linkerd_cli.status == "missing"
    assert report.ready is True


def test_check_environment_reports_linkerd_namespace_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == LINKERD_NAMESPACE_COMMAND:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = check_environment()

    assert report.linkerd_namespace.status == "error"
    assert report.linkerd_namespace.details == "not found"
    assert report.ready is True


def test_check_environment_reports_linkerd_control_plane_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == LINKERD_CONTROL_PLANE_COMMAND:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = check_environment()

    assert report.linkerd_control_plane.status == "error"
    assert report.linkerd_control_plane.details == "not found"
    assert report.ready is True


def test_check_environment_reports_linkerd_viz_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == LINKERD_VIZ_COMMAND:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    report = check_environment()

    assert report.linkerd_viz.status == "error"
    assert report.linkerd_viz.details == "not found"
    assert report.ready is True
