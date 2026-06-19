import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from k8s_forge.cli import app
from k8s_forge.config_loader import load_app_config
from k8s_forge.kubectl import KubectlResult

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def test_cli_help_responds() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "k8s-forge" in result.output


def test_cli_commands_exist() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("init", "check", "render", "dry-run", "diff", "apply", "status"):
        assert command in result.output


def test_cli_init_creates_default_app_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "demo-app"])

    assert result.exit_code == 0
    config_path = Path("app.yaml")
    assert config_path.exists()
    config = load_app_config(config_path)
    assert config.app.name == "demo-app"
    assert config.app.namespace == "demo-app"
    assert config.app.image == "demo-app:latest"
    assert config.app.containerPort == 8000
    assert config.app.replicas == 1
    assert config.service.port == 80
    assert config.ingress.host is None
    text = config_path.read_text(encoding="utf-8")
    assert 'API_TOKEN: "change-me"' in text
    assert "host: null" in text


def test_cli_init_options_override_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "init",
            "admin-api",
            "--namespace",
            "admin",
            "--image",
            "ghcr.io/example/admin-api:1.0.0",
            "--port",
            "8080",
            "--replicas",
            "1",
            "--service-port",
            "8081",
            "--output",
            "custom.yaml",
        ],
    )

    assert result.exit_code == 0
    config = load_app_config(Path("custom.yaml"))
    assert config.app.name == "admin-api"
    assert config.app.namespace == "admin"
    assert config.app.image == "ghcr.io/example/admin-api:1.0.0"
    assert config.app.containerPort == 8080
    assert config.app.replicas == 1
    assert config.service.port == 8081


def test_cli_init_custom_output_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "sample-web", "--output", "custom.yaml"])

    assert result.exit_code == 0
    assert Path("custom.yaml").exists()
    assert not Path("app.yaml").exists()


def test_cli_init_existing_file_fails_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("app.yaml")
    config_path.write_text("existing content", encoding="utf-8")

    result = runner.invoke(app, ["init", "demo-app"])

    assert result.exit_code == 1
    assert "file already exists, use --force to overwrite" in result.output
    assert config_path.read_text(encoding="utf-8") == "existing content"


def test_cli_init_force_overwrites_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("app.yaml")
    config_path.write_text("existing content", encoding="utf-8")

    result = runner.invoke(app, ["init", "demo-app", "--force"])

    assert result.exit_code == 0
    assert "existing content" not in config_path.read_text(encoding="utf-8")
    assert load_app_config(config_path).app.name == "demo-app"


def test_cli_init_does_not_call_kubectl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        raise AssertionError("init must not call kubectl")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fail_run_kubectl)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "generic-api"])

    assert result.exit_code == 0
    assert load_app_config(Path("app.yaml")).app.name == "generic-api"


def test_cli_check_success() -> None:
    result = runner.invoke(app, ["check", str(ROOT / "examples" / "demo-app.yaml")])

    assert result.exit_code == 0
    assert "configuration is valid" in result.output
    assert "demo-app" in result.output
    assert "demo" in result.output
    assert "ghcr.io/example/demo-app:1.0.0" in result.output
    assert "8000" in result.output
    assert "enabled on port 80" in result.output


def test_cli_check_error(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
app:
  name: broken-app
  namespace: broken
  containerPort: 8000
  replicas: 1
service:
  enabled: true
  port: 80
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 1
    assert "Configuration validation failed" in result.output
    assert "app.image" in result.output


def test_cli_render_success(tmp_path: Path) -> None:
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "render",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert "manifests generated" in result.output
    assert "00-namespace.yaml" in result.output
    assert "40-service.yaml" in result.output
    assert (output_dir / "30-deployment.yaml").exists()


def test_cli_render_validation_error_does_not_generate(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    config_path.write_text(
        """
app:
  name: broken-app
  namespace: broken
  image: ghcr.io/example/broken-app:1.0.0
  containerPort: 70000
  replicas: 1
service:
  enabled: true
  port: 80
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 1
    assert "Configuration validation failed" in result.output
    assert not output_dir.exists()


def test_cli_dry_run_calls_kubectl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], int]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append((args, timeout))
        return KubectlResult(["kubectl", *args], 0, "dry run ok", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "dry-run",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
            "--timeout",
            "7",
        ],
    )

    assert result.exit_code == 0
    assert calls == [(["apply", "--dry-run=server", "-f", str(output_dir)], 7)]
    assert "dry run ok" in result.output


def test_cli_diff_calls_kubectl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append(args)
        return KubectlResult(["kubectl", *args], 1, "diff output", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        ["diff", str(ROOT / "examples" / "demo-app.yaml"), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert calls == [["diff", "-f", str(output_dir)]]
    assert "diff output" in result.output
    assert "found changes" in result.output


def test_cli_apply_refusal_does_not_call_kubectl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append(args)
        return KubectlResult(["kubectl", *args], 0, "applied", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "apply",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
        input="n\n",
    )

    assert result.exit_code == 0
    assert calls == []
    assert "apply cancelled" in result.output


def test_cli_apply_confirmation_calls_kubectl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append(args)
        return KubectlResult(["kubectl", *args], 0, "applied", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "apply",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
        input="y\n",
    )

    assert result.exit_code == 0
    assert calls == [["apply", "-f", str(output_dir)]]
    assert "applied" in result.output


def test_cli_apply_yes_calls_kubectl_without_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append(args)
        return KubectlResult(["kubectl", *args], 0, "applied", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "apply",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert calls == [["apply", "-f", str(output_dir)]]
    assert "Continue with kubectl apply?" not in result.output


def test_cli_status_calls_kubectl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], int]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append((args, timeout))
        return KubectlResult(["kubectl", *args], 0, "status output", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)

    result = runner.invoke(app, ["status", "demo-app", "-n", "demo", "--timeout", "9"])

    assert result.exit_code == 0
    assert calls == [(["-n", "demo", "get", "deploy,po,svc", "-l", "app=demo-app"], 9)]
    assert "status output" in result.output


def test_cli_dry_run_missing_kubectl_reports_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "dry-run",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 1
    assert "kubectl executable was not found" in result.output
    assert "Install kubectl" in result.output
    assert "PATH" in result.output


def test_cli_status_timeout_reports_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, timeout=5, stderr="cluster too slow")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["status", "demo-app", "-n", "demo", "--timeout", "5"])

    assert result.exit_code == 1
    assert "kubectl timed out after 5 seconds" in result.output
    assert "cluster too slow" in result.output


def test_cli_dry_run_nonzero_return_shows_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 3, "", "server rejected manifest")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "dry-run",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 3
    assert "server rejected manifest" in result.output


def test_cli_apply_nonzero_return_shows_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 4, "", "forbidden by RBAC")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "apply",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
            "--yes",
        ],
    )

    assert result.exit_code == 4
    assert "forbidden by RBAC" in result.output


def test_cli_status_nonzero_return_shows_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "namespace demo not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["status", "demo-app", "-n", "demo"])

    assert result.exit_code == 1
    assert "namespace demo not found" in result.output


def test_cli_diff_zero_return_is_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "no differences", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        ["diff", str(ROOT / "examples" / "demo-app.yaml"), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "no differences" in result.output
    assert "found changes" not in result.output


def test_cli_diff_return_one_is_not_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "diff content", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        ["diff", str(ROOT / "examples" / "demo-app.yaml"), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "diff content" in result.output
    assert "found changes" in result.output


def test_cli_diff_return_above_one_is_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, "", "diff failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        ["diff", str(ROOT / "examples" / "demo-app.yaml"), "--output", str(output_dir)],
    )

    assert result.exit_code == 2
    assert "diff failed" in result.output
