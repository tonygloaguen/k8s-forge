from typer.testing import CliRunner

from k8s_forge.cli import app

runner = CliRunner()


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
