from pathlib import Path

import pytest
import yaml

from k8s_forge.ci_renderer import render_ci_files, resolve_ci_image
from k8s_forge.exceptions import RenderError
from k8s_forge.models import AppConfig


def _base_config() -> dict[str, object]:
    return {
        "app": {
            "name": "weatherapi",
            "namespace": "weather",
            "image": "weatherapi:0.1.0",
            "containerPort": 8000,
            "replicas": 2,
        },
        "service": {"enabled": True, "port": 80},
    }


def _enabled_config() -> dict[str, object]:
    config = _base_config()
    config["ci"] = {
        "enabled": True,
        "provider": "github-actions",
        "python": {
            "enabled": True,
            "version": "3.12",
            "quality": {
                "ruff": True,
                "mypy": True,
                "bandit": True,
                "pipAudit": True,
                "pytest": True,
                "build": True,
            },
        },
        "container": {
            "enabled": True,
            "image": "weatherapi:0.1.0",
            "dockerfile": "Dockerfile",
            "context": ".",
            "scan": {
                "enabled": True,
                "tool": "trivy",
                "severity": ["HIGH", "CRITICAL"],
            },
            "sbom": {
                "enabled": True,
                "tool": "syft",
                "format": "cyclonedx-json",
            },
        },
        "artifacts": {"enabled": True},
    }
    return config


def test_resolve_ci_image_prefers_ci_container_image() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_ci_image(config) == "weatherapi:0.1.0"


def test_resolve_ci_image_falls_back_to_supply_chain_image() -> None:
    config_data = _enabled_config()
    ci = config_data["ci"]
    assert isinstance(ci, dict)
    container = ci["container"]
    assert isinstance(container, dict)
    container["image"] = ""
    config_data["supplyChain"] = {
        "enabled": True,
        "image": "registry.example/weather:1.2.3",
    }
    config = AppConfig.model_validate(config_data)

    assert resolve_ci_image(config) == "registry.example/weather:1.2.3"


def test_resolve_ci_image_falls_back_to_app_image() -> None:
    config_data = _enabled_config()
    ci = config_data["ci"]
    assert isinstance(ci, dict)
    container = ci["container"]
    assert isinstance(container, dict)
    container["image"] = ""
    config = AppConfig.model_validate(config_data)

    assert resolve_ci_image(config) == "weatherapi:0.1.0"


def test_no_files_generated_when_ci_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    generated = render_ci_files(config, tmp_path)

    assert generated == []
    assert not (tmp_path / "README.md").exists()


def test_ci_renderer_generates_readme_and_workflows(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    generated = render_ci_files(config, tmp_path)

    generated_names = {str(path.relative_to(tmp_path)) for path in generated}
    assert generated_names == {
        "README.md",
        ".github/workflows/ci.yml",
        ".github/workflows/security.yml",
    }
    assert "GitHub Actions CI Readiness" in (tmp_path / "README.md").read_text(
        encoding="utf-8"
    )
    assert "python -m pytest -q" in (
        tmp_path / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")
    assert "docker build -t weatherapi:0.1.0 -f Dockerfile ." in (
        tmp_path / ".github" / "workflows" / "security.yml"
    ).read_text(encoding="utf-8")


def test_security_workflow_absent_when_container_disabled(tmp_path: Path) -> None:
    config_data = _enabled_config()
    ci = config_data["ci"]
    assert isinstance(ci, dict)
    container = ci["container"]
    assert isinstance(container, dict)
    container["enabled"] = False
    config = AppConfig.model_validate(config_data)

    generated = render_ci_files(config, tmp_path)

    generated_names = {str(path.relative_to(tmp_path)) for path in generated}
    assert ".github/workflows/ci.yml" in generated_names
    assert ".github/workflows/security.yml" not in generated_names
    assert not (tmp_path / ".github" / "workflows" / "security.yml").exists()


def test_ci_workflows_are_parseable_yaml(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_ci_files(config, tmp_path)

    ci_workflow = yaml.safe_load(
        (tmp_path / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    security_workflow = yaml.safe_load(
        (tmp_path / ".github" / "workflows" / "security.yml").read_text(
            encoding="utf-8"
        )
    )
    assert "jobs" in ci_workflow
    assert "jobs" in security_workflow
    assert ci_workflow["jobs"]["python-quality"]["steps"]
    assert security_workflow["jobs"]["image-security"]["steps"]


def test_ci_workflows_do_not_push_deploy_or_use_secrets(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_ci_files(config, tmp_path)

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            tmp_path / ".github" / "workflows" / "ci.yml",
            tmp_path / ".github" / "workflows" / "security.yml",
        ]
    )
    assert "docker push" not in combined
    assert "kubectl apply" not in combined
    assert "helm upgrade" not in combined
    assert "secrets." not in combined


def test_ci_renderer_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_ci_files(config, tmp_path)

    with pytest.raises(RenderError, match="use --force"):
        render_ci_files(config, tmp_path)


def test_ci_renderer_overwrites_with_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_ci_files(config, tmp_path)
    ci_file = tmp_path / ".github" / "workflows" / "ci.yml"
    ci_file.write_text("old", encoding="utf-8")

    render_ci_files(config, tmp_path, force=True)

    assert "python -m pytest -q" in ci_file.read_text(encoding="utf-8")


def test_ci_renderer_uses_configured_severity_and_sbom_format(tmp_path: Path) -> None:
    config_data = _enabled_config()
    ci = config_data["ci"]
    assert isinstance(ci, dict)
    container = ci["container"]
    assert isinstance(container, dict)
    scan = container["scan"]
    sbom = container["sbom"]
    assert isinstance(scan, dict)
    assert isinstance(sbom, dict)
    scan["severity"] = ["MEDIUM", "HIGH"]
    sbom["format"] = "spdx-json"
    config = AppConfig.model_validate(config_data)

    render_ci_files(config, tmp_path)

    security = (tmp_path / ".github" / "workflows" / "security.yml").read_text(
        encoding="utf-8"
    )
    assert "--severity MEDIUM,HIGH" in security
    assert "spdx-json=reports/sbom.spdx.json" in security
