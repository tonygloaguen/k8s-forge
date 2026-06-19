from pathlib import Path

from typer.testing import CliRunner

from k8s_forge.cli import app

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


def test_kubectl_backed_placeholder_command_outputs_not_implemented() -> None:
    result = runner.invoke(app, ["dry-run", "app.yaml"])

    assert result.exit_code == 0
    assert "not implemented yet" in result.output


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
