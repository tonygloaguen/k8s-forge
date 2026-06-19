from pathlib import Path

import pytest
from typer.testing import CliRunner

from k8s_forge.cli import app
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
