from pathlib import Path

import pytest

from k8s_forge.capstone_renderer import (
    GENERATED_CAPSTONE_FILES,
    render_capstone_files,
    resolve_capstone_project_name,
    resolve_capstone_report_title,
)
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
        "ingress": {
            "enabled": True,
            "host": "weather.local",
            "tls": {"enabled": True, "secretName": "weather-tls"},
            "certManager": {"enabled": True, "clusterIssuer": "selfsigned"},
        },
        "mesh": {"enabled": True, "provider": "linkerd", "inject": True},
        "networkPolicy": {"enabled": True, "profile": "ingress-only"},
        "policy": {"enabled": True, "provider": "kyverno"},
        "supplyChain": {"enabled": True},
        "ci": {"enabled": True},
        "gitops": {
            "enabled": True,
            "source": {
                "repoURL": "https://github.com/example/weatherapi.git",
                "path": "charts-generated/weatherapi",
            },
        },
        "observability": {"enabled": True},
        "logging": {"enabled": True},
        "tracing": {"enabled": True},
        "terraform": {"enabled": True},
        "ansible": {"enabled": True},
        "security": {"enabled": True},
    }


def _enabled_config() -> dict[str, object]:
    config = _base_config()
    config["capstone"] = {
        "enabled": True,
        "projectName": "",
        "report": {"title": "", "audience": "technical"},
        "checklist": {"enabled": True},
        "architecture": {"enabled": True},
        "devsecopsMatrix": {"enabled": True},
        "modulesSummary": {"enabled": True},
        "manualSteps": {"enabled": True},
        "runtimeDependencies": {"enabled": True},
        "securitySummary": {"enabled": True},
        "v1Readiness": {"enabled": True},
        "examples": {"enabled": True},
    }
    return config


def _read_generated_text(root: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_resolve_capstone_project_name_falls_back_to_app_name() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_capstone_project_name(config) == "weatherapi"


def test_resolve_capstone_project_name_uses_configured_name() -> None:
    config_data = _enabled_config()
    capstone = config_data["capstone"]
    assert isinstance(capstone, dict)
    capstone["projectName"] = "weather-capstone"
    config = AppConfig.model_validate(config_data)

    assert resolve_capstone_project_name(config) == "weather-capstone"


def test_resolve_capstone_report_title_falls_back_to_app_name() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_capstone_report_title(config) == (
        "weatherapi DevSecOps Cloud-Native Lab"
    )


def test_resolve_capstone_report_title_uses_configured_title() -> None:
    config_data = _enabled_config()
    capstone = config_data["capstone"]
    assert isinstance(capstone, dict)
    report = capstone["report"]
    assert isinstance(report, dict)
    report["title"] = "WeatherAPI Final Lab"
    config = AppConfig.model_validate(config_data)

    assert resolve_capstone_report_title(config) == "WeatherAPI Final Lab"


def test_no_files_generated_when_capstone_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    generated = render_capstone_files(config, tmp_path)

    assert generated == []
    assert not (tmp_path / "README.md").exists()


def test_capstone_renderer_generates_expected_files(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    generated = render_capstone_files(config, tmp_path)

    assert {str(path.relative_to(tmp_path)) for path in generated} == set(
        GENERATED_CAPSTONE_FILES
    )
    assert "Capstone Readiness" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_capstone_files_contain_context_modules_and_v1_readiness(
    tmp_path: Path,
) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_capstone_files(config, tmp_path)

    combined = _read_generated_text(tmp_path)
    assert "weatherapi" in combined
    assert "weather" in combined
    for module in (
        "Kubernetes raw",
        "Helm",
        "Ingress / TLS",
        "Linkerd",
        "NetworkPolicy",
        "Kyverno",
        "Supply Chain",
        "CI GitHub Actions",
        "GitOps ArgoCD",
        "Observability",
        "Logging",
        "Tracing",
        "Terraform",
        "Ansible",
        "Security Audit readiness",
    ):
        assert module in combined
    assert "v1.0.0 readiness" in combined
    assert "Code" in combined
    assert "Build" in combined
    assert "Test" in combined
    assert "Scan" in combined
    assert "Package" in combined
    assert "Document" in combined
    assert "install ingress-nginx" in combined
    assert "Kubernetes cluster" in combined
    assert "OpenTelemetry Collector" in combined


def test_capstone_renderer_does_not_render_sensitive_values_or_active_commands(
    tmp_path: Path,
) -> None:
    config_data = _enabled_config()
    config_data["secrets"] = {"API_TOKEN": "change-me"}
    config = AppConfig.model_validate(config_data)

    render_capstone_files(config, tmp_path)

    combined = _read_generated_text(tmp_path).lower()
    forbidden = [
        "change-me",
        "credential",
        "token",
        "kubectl apply",
        "helm install",
        "terraform apply",
        "ansible-playbook",
        "trivy image",
        "scan has passed",
        "rm -rf",
    ]
    for value in forbidden:
        assert value not in combined


def test_capstone_renderer_respects_disabled_sections(tmp_path: Path) -> None:
    config_data = _enabled_config()
    capstone = config_data["capstone"]
    assert isinstance(capstone, dict)
    architecture = capstone["architecture"]
    assert isinstance(architecture, dict)
    architecture["enabled"] = False
    config = AppConfig.model_validate(config_data)

    generated = render_capstone_files(config, tmp_path)

    generated_names = {str(path.relative_to(tmp_path)) for path in generated}
    assert "architecture-overview.md" not in generated_names
    assert not (tmp_path / "architecture-overview.md").exists()


def test_capstone_renderer_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_capstone_files(config, tmp_path)

    with pytest.raises(RenderError, match="use --force"):
        render_capstone_files(config, tmp_path)


def test_capstone_renderer_overwrites_with_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_capstone_files(config, tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("old", encoding="utf-8")

    render_capstone_files(config, tmp_path, force=True)

    assert "Capstone Readiness" in readme.read_text(encoding="utf-8")
