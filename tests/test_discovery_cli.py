from pathlib import Path

from typer.testing import CliRunner

from k8s_forge.cli import app
from k8s_forge.config_loader import load_app_config

runner = CliRunner()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def create_fastapi_repo(root: Path) -> Path:
    repo = root / "cli-fastapi"
    write(repo / "requirements.txt", "fastapi\nuvicorn\npytest\n")
    write(repo / "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    write(repo / "Dockerfile", "FROM python:3.12-slim\nEXPOSE 8000\n")
    write(repo / "tests" / "test_app.py", "def test_ok():\n    assert True\n")
    return repo


def create_low_confidence_repo(root: Path) -> Path:
    repo = root / "ambiguous"
    write(repo / "README.md", "A utility repository without a web server.\n")
    return repo


def test_cli_discover_help() -> None:
    result = runner.invoke(app, ["discover", "--help"])

    assert result.exit_code == 0
    assert "Repository path to inspect" in result.output
    assert "--output" in result.output
    assert "--force" in result.output


def test_cli_discover_errors_for_missing_path(tmp_path: Path) -> None:
    result = runner.invoke(app, ["discover", str(tmp_path / "missing")])

    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_cli_discover_errors_for_file_path(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("not a directory", encoding="utf-8")

    result = runner.invoke(app, ["discover", str(path)])

    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_cli_discover_generates_files_for_fastapi(tmp_path: Path) -> None:
    repo = create_fastapi_repo(tmp_path)
    output = tmp_path / "generated-discovery"

    result = runner.invoke(app, ["discover", str(repo), "--output", str(output)])

    assert result.exit_code == 0
    assert "This performs static analysis only." in result.output
    assert "Repository discovery completed." in result.output
    assert "Detected language: Python" in result.output
    assert "Detected framework: FastAPI" in result.output
    assert "Confidence:" in result.output
    assert (output / "discovery-report.md").exists()
    assert (output / "warnings.md").exists()
    generated_yaml = output / "k8s-forge-app.yaml"
    assert generated_yaml.exists()
    config = load_app_config(generated_yaml)
    assert config.app.name == "cli-fastapi"
    assert config.config == {"DISCOVERY_REVIEW": "required"}

    check_result = runner.invoke(app, ["check", str(generated_yaml)])
    assert check_result.exit_code == 0


def test_cli_discover_refuses_overwrite_without_force(tmp_path: Path) -> None:
    repo = create_fastapi_repo(tmp_path)
    output = tmp_path / "generated-discovery"

    first = runner.invoke(app, ["discover", str(repo), "--output", str(output)])
    second = runner.invoke(app, ["discover", str(repo), "--output", str(output)])

    assert first.exit_code == 0
    assert second.exit_code == 1
    assert "already exists" in second.output


def test_cli_discover_allows_overwrite_with_force(tmp_path: Path) -> None:
    repo = create_fastapi_repo(tmp_path)
    output = tmp_path / "generated-discovery"
    runner.invoke(app, ["discover", str(repo), "--output", str(output)])
    (output / "warnings.md").write_text("custom", encoding="utf-8")

    result = runner.invoke(
        app,
        ["discover", str(repo), "--output", str(output), "--force"],
    )

    assert result.exit_code == 0
    assert "custom" not in (output / "warnings.md").read_text(encoding="utf-8")


def test_cli_discover_low_confidence_is_report_only(tmp_path: Path) -> None:
    repo = create_low_confidence_repo(tmp_path)
    output = tmp_path / "generated-discovery"

    result = runner.invoke(app, ["discover", str(repo), "--output", str(output)])

    assert result.exit_code == 0
    assert "Confidence: low" in result.output
    assert "Recommended mode: report-only" in result.output
    assert (output / "discovery-report.md").exists()
    assert (output / "warnings.md").exists()
    assert not (output / "k8s-forge-app.yaml").exists()
