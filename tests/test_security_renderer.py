from pathlib import Path

import pytest

from k8s_forge.exceptions import RenderError
from k8s_forge.models import AppConfig
from k8s_forge.security_renderer import (
    GENERATED_SECURITY_FILES,
    render_security_files,
    resolve_security_project_name,
)


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
        "resources": {
            "requests": {"cpu": "50m", "memory": "64Mi"},
            "limits": {"cpu": "250m", "memory": "128Mi"},
        },
        "probes": {"liveness": "/healthz", "readiness": "/readyz"},
        "networkPolicy": {"enabled": True, "profile": "ingress-only"},
        "policy": {"enabled": True, "provider": "kyverno"},
        "supplyChain": {"enabled": True},
        "ci": {"enabled": True, "container": {"enabled": True}},
    }


def _enabled_config() -> dict[str, object]:
    config = _base_config()
    config["security"] = {
        "enabled": True,
        "projectName": "",
        "container": {"enabled": True},
        "manifests": {"enabled": True},
        "rbac": {"enabled": True},
        "podSecurity": {"enabled": True},
        "network": {"enabled": True},
        "secrets": {"enabled": True},
        "supplyChain": {"enabled": True},
        "checklist": {"enabled": True},
        "examples": {"enabled": True},
    }
    return config


def _read_generated_text(root: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_resolve_security_project_name_falls_back_to_app_name() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_security_project_name(config) == "weatherapi"


def test_resolve_security_project_name_uses_configured_name() -> None:
    config_data = _enabled_config()
    security = config_data["security"]
    assert isinstance(security, dict)
    security["projectName"] = "weather-security"
    config = AppConfig.model_validate(config_data)

    assert resolve_security_project_name(config) == "weather-security"


def test_no_files_generated_when_security_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    generated = render_security_files(config, tmp_path)

    assert generated == []
    assert not (tmp_path / "README.md").exists()


def test_security_renderer_generates_expected_files(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    generated = render_security_files(config, tmp_path)

    assert {str(path.relative_to(tmp_path)) for path in generated} == set(
        GENERATED_SECURITY_FILES
    )
    assert "Security Audit Readiness" in (tmp_path / "README.md").read_text(
        encoding="utf-8"
    )


def test_security_files_contain_app_context_and_core_controls(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_security_files(config, tmp_path)

    combined = _read_generated_text(tmp_path)
    assert "weatherapi" in combined
    assert "weather" in combined
    assert "cluster-admin" in combined
    assert 'verbs: ["*"]' in combined
    assert 'resources: ["*"]' in combined
    assert "impersonate" in combined
    assert "bind" in combined
    assert "escalate" in combined
    assert "ServiceAccount `default`" in combined
    assert "runAsNonRoot" in combined
    assert "allowPrivilegeEscalation" in combined
    assert "readOnlyRootFilesystem" in combined
    assert "capabilities.drop" in combined
    assert "seccompProfile" in combined
    assert "hostNetwork" in combined
    assert "NetworkPolicy" in combined
    assert "Ingress TLS" in combined
    assert "Trivy" in combined
    assert "Syft" in combined
    assert "Cosign" in combined


def test_security_renderer_does_not_render_sensitive_values_or_active_commands(
    tmp_path: Path,
) -> None:
    config_data = _enabled_config()
    config_data["secrets"] = {"API_TOKEN": "change-me"}
    config = AppConfig.model_validate(config_data)

    render_security_files(config, tmp_path)

    combined = _read_generated_text(tmp_path).lower()
    forbidden = [
        "change-me",
        "credential",
        "password",
        "private key",
        "kubectl apply",
        "kubectl auth can-i",
        "helm install",
        "terraform apply",
        "ansible-playbook",
        "trivy image",
        "kube-bench",
        "kube-score",
        "polaris",
        "checkov",
        "terrascan",
    ]
    for value in forbidden:
        assert value not in combined


def test_security_renderer_respects_disabled_sections(tmp_path: Path) -> None:
    config_data = _enabled_config()
    security = config_data["security"]
    assert isinstance(security, dict)
    container = security["container"]
    assert isinstance(container, dict)
    container["enabled"] = False
    config = AppConfig.model_validate(config_data)

    generated = render_security_files(config, tmp_path)

    generated_names = {str(path.relative_to(tmp_path)) for path in generated}
    assert "container-security.md" not in generated_names
    assert not (tmp_path / "container-security.md").exists()


def test_security_renderer_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_security_files(config, tmp_path)

    with pytest.raises(RenderError, match="use --force"):
        render_security_files(config, tmp_path)


def test_security_renderer_overwrites_with_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_security_files(config, tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("old", encoding="utf-8")

    render_security_files(config, tmp_path, force=True)

    assert "Security Audit Readiness" in readme.read_text(encoding="utf-8")
