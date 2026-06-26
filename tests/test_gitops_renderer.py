from pathlib import Path

import pytest
import yaml

from k8s_forge.exceptions import RenderError
from k8s_forge.gitops_renderer import (
    render_gitops_files,
    resolve_gitops_application_name,
    resolve_gitops_destination_namespace,
)
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
    config["gitops"] = {
        "enabled": True,
        "provider": "argocd",
        "application": {
            "name": "",
            "namespace": "argocd",
            "project": "default",
        },
        "destination": {
            "server": "https://kubernetes.default.svc",
            "namespace": "",
        },
        "source": {
            "repoURL": "https://github.com/example/weatherapi-platform.git",
            "targetRevision": "main",
            "path": "charts-generated/weatherapi",
            "type": "helm",
        },
        "syncPolicy": {
            "automated": False,
            "prune": False,
            "selfHeal": False,
        },
    }
    return config


def test_resolve_gitops_application_name_falls_back_to_app_name() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_gitops_application_name(config) == "weatherapi"


def test_resolve_gitops_destination_namespace_falls_back_to_app_namespace() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_gitops_destination_namespace(config) == "weather"


def test_no_files_generated_when_gitops_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    generated = render_gitops_files(config, tmp_path)

    assert generated == []
    assert not (tmp_path / "README.md").exists()


def test_gitops_renderer_generates_readme_and_application(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    generated = render_gitops_files(config, tmp_path)

    assert {str(path.relative_to(tmp_path)) for path in generated} == {
        "README.md",
        "argocd/application.yaml",
    }
    assert "ArgoCD GitOps Readiness" in (tmp_path / "README.md").read_text(
        encoding="utf-8"
    )
    assert (tmp_path / "argocd" / "application.yaml").exists()


def test_gitops_application_yaml_is_parseable_and_minimal(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_gitops_files(config, tmp_path)

    app = yaml.safe_load(
        (tmp_path / "argocd" / "application.yaml").read_text(encoding="utf-8")
    )
    assert app["apiVersion"] == "argoproj.io/v1alpha1"
    assert app["kind"] == "Application"
    assert app["metadata"] == {"name": "weatherapi", "namespace": "argocd"}
    assert app["spec"]["project"] == "default"
    assert app["spec"]["source"] == {
        "repoURL": "https://github.com/example/weatherapi-platform.git",
        "targetRevision": "main",
        "path": "charts-generated/weatherapi",
    }
    assert app["spec"]["destination"]["namespace"] == "weather"
    assert app["spec"]["syncPolicy"] == {}


def test_gitops_application_uses_configured_namespaces_and_auto_sync(
    tmp_path: Path,
) -> None:
    config_data = _enabled_config()
    gitops = config_data["gitops"]
    assert isinstance(gitops, dict)
    application = gitops["application"]
    destination = gitops["destination"]
    sync_policy = gitops["syncPolicy"]
    assert isinstance(application, dict)
    assert isinstance(destination, dict)
    assert isinstance(sync_policy, dict)
    application["name"] = "weatherapi-prod"
    destination["namespace"] = "weather-helm"
    sync_policy["automated"] = True
    sync_policy["prune"] = True
    sync_policy["selfHeal"] = True
    config = AppConfig.model_validate(config_data)

    render_gitops_files(config, tmp_path)

    app = yaml.safe_load(
        (tmp_path / "argocd" / "application.yaml").read_text(encoding="utf-8")
    )
    assert app["metadata"]["name"] == "weatherapi-prod"
    assert app["spec"]["destination"]["namespace"] == "weather-helm"
    assert app["spec"]["syncPolicy"] == {"automated": {"prune": True, "selfHeal": True}}


def test_gitops_output_contains_no_secret_token_or_sync_commands(
    tmp_path: Path,
) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_gitops_files(config, tmp_path)

    application_text = (tmp_path / "argocd" / "application.yaml").read_text(
        encoding="utf-8"
    )
    application = yaml.safe_load(application_text)
    normalized_application = application_text.lower()

    assert "secret" not in application
    assert "token" not in normalized_application
    assert "kubectl apply" not in normalized_application
    assert "argocd app sync" not in normalized_application


def test_gitops_renderer_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_gitops_files(config, tmp_path)

    with pytest.raises(RenderError, match="use --force"):
        render_gitops_files(config, tmp_path)


def test_gitops_renderer_overwrites_with_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_gitops_files(config, tmp_path)
    application = tmp_path / "argocd" / "application.yaml"
    application.write_text("old", encoding="utf-8")

    render_gitops_files(config, tmp_path, force=True)

    assert "kind: Application" in application.read_text(encoding="utf-8")
