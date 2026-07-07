from pathlib import Path

from typer.testing import CliRunner

import k8s_forge.cli as cli
from k8s_forge.cli import app
from k8s_forge.studio.server import StudioDependencyError

runner = CliRunner()


def test_cli_studio_help() -> None:
    result = runner.invoke(app, ["studio", "--help"])

    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--workspace" in result.output


def test_cli_studio_defaults(monkeypatch: object) -> None:
    captured: dict[str, object] = {}

    def fake_run_studio(host: str, port: int, workspace: Path) -> None:
        captured["host"] = host
        captured["port"] = port
        captured["workspace"] = workspace

    monkeypatch.setattr(cli, "run_studio", fake_run_studio)

    result = runner.invoke(app, ["studio"])

    assert result.exit_code == 0
    assert captured == {
        "host": "127.0.0.1",
        "port": 8765,
        "workspace": Path(".k8s-forge-studio"),
    }


def test_cli_studio_missing_dependencies_message(monkeypatch: object) -> None:
    def fake_run_studio(host: str, port: int, workspace: Path) -> None:
        message = (
            "Studio dependencies are missing.\n"
            "Install with:\n"
            'pip install -e ".[studio]"'
        )
        raise StudioDependencyError(message)

    monkeypatch.setattr(cli, "run_studio", fake_run_studio)

    result = runner.invoke(app, ["studio"])

    assert result.exit_code == 1
    assert "Studio dependencies are missing" in result.output
    assert 'pip install -e ".[studio]"' in result.output
