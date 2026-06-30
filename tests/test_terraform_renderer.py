from pathlib import Path

import pytest

from k8s_forge.exceptions import RenderError
from k8s_forge.models import AppConfig
from k8s_forge.terraform_renderer import (
    render_terraform_files,
    resolve_terraform_project_name,
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
    }


def _enabled_config() -> dict[str, object]:
    config = _base_config()
    config["terraform"] = {
        "enabled": True,
        "projectName": "",
        "backend": {"type": "local"},
        "providers": {
            "kubernetes": {"enabled": True},
            "helm": {"enabled": True},
            "cloud": {"enabled": False},
        },
        "modules": {"enabled": True},
        "examples": {"enabled": True},
    }
    return config


def _read_generated_text(root: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(root.glob("*"))
        if path.is_file()
    )


def test_resolve_terraform_project_name_falls_back_to_app_name() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_terraform_project_name(config) == "weatherapi"


def test_resolve_terraform_project_name_uses_configured_name() -> None:
    config_data = _enabled_config()
    terraform = config_data["terraform"]
    assert isinstance(terraform, dict)
    terraform["projectName"] = "weather-platform"
    config = AppConfig.model_validate(config_data)

    assert resolve_terraform_project_name(config) == "weather-platform"


def test_no_files_generated_when_terraform_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    generated = render_terraform_files(config, tmp_path)

    assert generated == []
    assert not (tmp_path / "README.md").exists()


def test_terraform_renderer_generates_expected_files(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    generated = render_terraform_files(config, tmp_path)

    assert {path.name for path in generated} == {
        "README.md",
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "outputs.tf",
    }
    assert "Terraform Readiness" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_terraform_files_contain_app_context_and_local_backend(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_terraform_files(config, tmp_path)

    combined = _read_generated_text(tmp_path)
    assert "weatherapi" in combined
    assert "weather" in combined
    assert 'backend "local"' in (tmp_path / "versions.tf").read_text(encoding="utf-8")
    assert 'provider "kubernetes"' in (tmp_path / "providers.tf").read_text(
        encoding="utf-8"
    )
    assert 'provider "helm"' in (tmp_path / "providers.tf").read_text(encoding="utf-8")
    assert 'resource "kubernetes_namespace"' in (tmp_path / "main.tf").read_text(
        encoding="utf-8"
    )
    assert 'resource "helm_release"' in (tmp_path / "main.tf").read_text(
        encoding="utf-8"
    )


def test_terraform_renderer_respects_disabled_examples(tmp_path: Path) -> None:
    config_data = _enabled_config()
    terraform = config_data["terraform"]
    assert isinstance(terraform, dict)
    examples = terraform["examples"]
    assert isinstance(examples, dict)
    examples["enabled"] = False
    config = AppConfig.model_validate(config_data)

    generated = render_terraform_files(config, tmp_path)

    assert "main.tf" not in {path.name for path in generated}
    assert not (tmp_path / "main.tf").exists()


def test_terraform_renderer_respects_disabled_providers(tmp_path: Path) -> None:
    config_data = _enabled_config()
    terraform = config_data["terraform"]
    assert isinstance(terraform, dict)
    providers = terraform["providers"]
    assert isinstance(providers, dict)
    kubernetes = providers["kubernetes"]
    helm = providers["helm"]
    assert isinstance(kubernetes, dict)
    assert isinstance(helm, dict)
    kubernetes["enabled"] = False
    helm["enabled"] = False
    config = AppConfig.model_validate(config_data)

    render_terraform_files(config, tmp_path)

    versions = (tmp_path / "versions.tf").read_text(encoding="utf-8")
    providers_text = (tmp_path / "providers.tf").read_text(encoding="utf-8")
    main_text = (tmp_path / "main.tf").read_text(encoding="utf-8")
    assert "hashicorp/kubernetes" not in versions
    assert "hashicorp/helm" not in versions
    assert 'provider "kubernetes"' not in providers_text
    assert 'provider "helm"' not in providers_text
    assert "kubernetes_namespace" not in main_text
    assert "helm_release" not in main_text


def test_terraform_output_contains_no_sensitive_or_mutating_content(
    tmp_path: Path,
) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_terraform_files(config, tmp_path)

    combined = _read_generated_text(tmp_path).lower()
    forbidden = [
        "terraform apply",
        "terraform destroy",
        "terraform init",
        "terraform plan",
        "kubectl apply",
        "helm install",
        "helm upgrade",
        'backend "s3"',
        'backend "remote"',
        "aws_access_key",
        "cloud_access_key",
        "client_secret",
        "password",
        "api_key",
        "bearer ",
        "token",
        "credential",
    ]
    for value in forbidden:
        assert value not in combined
    assert "kubeconfig =" not in combined


def test_terraform_renderer_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_terraform_files(config, tmp_path)

    with pytest.raises(RenderError, match="use --force"):
        render_terraform_files(config, tmp_path)


def test_terraform_renderer_overwrites_with_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_terraform_files(config, tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("old", encoding="utf-8")

    render_terraform_files(config, tmp_path, force=True)

    assert "Terraform Readiness" in readme.read_text(encoding="utf-8")
