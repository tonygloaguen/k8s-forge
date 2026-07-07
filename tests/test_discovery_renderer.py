from pathlib import Path

import pytest

from k8s_forge.config_loader import load_app_config
from k8s_forge.discovery import discover_repository
from k8s_forge.discovery_renderer import render_discovery_files
from k8s_forge.exceptions import RenderError


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def create_fastapi_repo(root: Path) -> Path:
    repo = root / "sample-fastapi"
    write(repo / "requirements.txt", "fastapi\nuvicorn\npytest\n")
    write(repo / "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    write(repo / "Dockerfile", "FROM python:3.12-slim\nEXPOSE 8080\n")
    write(repo / "tests" / "test_app.py", "def test_ok():\n    assert True\n")
    return repo


def create_low_confidence_repo(root: Path) -> Path:
    repo = root / "batch-job"
    write(repo / "worker.py", "print('background')\n")
    write(repo / "helper.py", "print('helper')\n")
    return repo


def generated_text(output: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(output.rglob("*"))
        if path.is_file()
    )


def test_render_discovery_files_generates_report_warnings_and_yaml(
    tmp_path: Path,
) -> None:
    repo = create_fastapi_repo(tmp_path)
    result = discover_repository(repo)

    output = tmp_path / "generated-discovery"
    generated = render_discovery_files(result, output)

    assert [path.relative_to(output).as_posix() for path in generated] == [
        "discovery-report.md",
        "warnings.md",
        "k8s-forge-app.yaml",
    ]
    config = load_app_config(output / "k8s-forge-app.yaml")
    assert config.app.name == "sample-fastapi"
    assert config.app.namespace == "sample-fastapi"
    assert config.app.containerPort == 8080
    assert config.service.port == 80
    assert config.workload.type == "deployment"
    yaml_text = (output / "k8s-forge-app.yaml").read_text(encoding="utf-8")
    assert "config:\n  enabled: true\n  data:" in yaml_text
    text = generated_text(output)
    assert "starter configuration" in text
    assert "readiness scaffold" in text
    assert "not deployment-ready by default" in text
    assert "ghcr.io/example/sample-fastapi:0.1.0" in text


def test_render_discovery_files_skips_yaml_when_confidence_low(tmp_path: Path) -> None:
    repo = create_low_confidence_repo(tmp_path)
    result = discover_repository(repo)

    output = tmp_path / "generated-discovery"
    generated = render_discovery_files(result, output)

    names = {path.name for path in generated}
    assert names == {"discovery-report.md", "warnings.md"}
    assert not (output / "k8s-forge-app.yaml").exists()
    assert "report-only" in (output / "discovery-report.md").read_text(encoding="utf-8")


def test_render_discovery_files_refuses_overwrite_without_force(tmp_path: Path) -> None:
    repo = create_fastapi_repo(tmp_path)
    result = discover_repository(repo)
    output = tmp_path / "generated-discovery"
    render_discovery_files(result, output)

    with pytest.raises(RenderError, match="already exists"):
        render_discovery_files(result, output)


def test_render_discovery_files_allows_overwrite_with_force(tmp_path: Path) -> None:
    repo = create_fastapi_repo(tmp_path)
    result = discover_repository(repo)
    output = tmp_path / "generated-discovery"
    render_discovery_files(result, output)
    (output / "warnings.md").write_text("custom", encoding="utf-8")

    render_discovery_files(result, output, force=True)

    assert "custom" not in (output / "warnings.md").read_text(encoding="utf-8")


def test_render_discovery_files_does_not_generate_forbidden_commands(
    tmp_path: Path,
) -> None:
    repo = create_fastapi_repo(tmp_path)
    output = tmp_path / "generated-discovery"

    render_discovery_files(discover_repository(repo), output)

    text = generated_text(output)
    for forbidden in (
        "kubectl apply",
        "helm install",
        "terraform apply",
        "ansible-playbook",
    ):
        assert forbidden not in text
    for forbidden_secret in ("change-me", "real-secret", "API_TOKEN:"):
        assert forbidden_secret not in text


def test_render_discovery_files_generates_job_yaml_for_cli_repo(tmp_path: Path) -> None:
    repo = tmp_path / "cli-tool"
    write(repo / "requirements.txt", "pytest\n")
    write(repo / "mapper.py", "print('scan')\n")

    output = tmp_path / "generated-discovery"
    render_discovery_files(discover_repository(repo), output)

    config = load_app_config(output / "k8s-forge-app.yaml")
    assert config.workload.type == "job"
    assert config.workload.command == ["python"]
    assert config.workload.args == ["mapper.py"]
    assert config.service.enabled is False
