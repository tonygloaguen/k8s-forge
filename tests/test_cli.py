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


def test_placeholder_command_outputs_not_implemented() -> None:
    result = runner.invoke(app, ["render", "app.yaml"])

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
