import pytest
from pydantic import ValidationError

from k8s_forge.models import AppConfig


def _valid_config(name: str = "demo-app") -> dict[str, object]:
    return {
        "app": {
            "name": name,
            "namespace": "demo",
            "image": f"ghcr.io/example/{name}:1.0.0",
            "containerPort": 8000,
            "replicas": 2,
        },
        "config": {
            "APP_ENV": "dev",
        },
        "secrets": {
            "API_TOKEN": "change-me",
        },
        "service": {
            "enabled": True,
            "port": 80,
        },
        "resources": {
            "requests": {
                "cpu": "50m",
                "memory": "64Mi",
            },
            "limits": {
                "cpu": "250m",
                "memory": "128Mi",
            },
        },
        "probes": {
            "liveness": "/healthz",
            "readiness": "/readyz",
        },
        "ingress": {
            "enabled": False,
            "host": "demo.local",
        },
    }


def test_demo_app_config_is_valid() -> None:
    config = AppConfig.model_validate(_valid_config("demo-app"))

    assert config.app.name == "demo-app"
    assert config.app.namespace == "demo"
    assert config.app.image == "ghcr.io/example/demo-app:1.0.0"
    assert config.app.containerPort == 8000
    assert config.app.replicas == 2
    assert config.service.enabled is True
    assert config.service.port == 80


def test_admin_api_config_is_valid() -> None:
    config_data = _valid_config("admin-api")
    app_data = config_data["app"]
    assert isinstance(app_data, dict)
    app_data["namespace"] = "admin"
    app_data["image"] = "ghcr.io/example/admin-api:2.1.0"
    app_data["containerPort"] = 8080
    app_data["replicas"] = 1
    service_data = config_data["service"]
    assert isinstance(service_data, dict)
    service_data["port"] = 8081

    config = AppConfig.model_validate(config_data)

    assert config.app.name == "admin-api"
    assert config.app.namespace == "admin"
    assert config.app.containerPort == 8080
    assert config.app.replicas == 1
    assert config.service.port == 8081


def test_app_config_rejects_invalid_container_port() -> None:
    config_data = _valid_config()
    app_data = config_data["app"]
    assert isinstance(app_data, dict)
    app_data["containerPort"] = 70000

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_app_config_rejects_zero_replicas() -> None:
    config_data = _valid_config()
    app_data = config_data["app"]
    assert isinstance(app_data, dict)
    app_data["replicas"] = 0

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_app_config_rejects_missing_required_field() -> None:
    config_data = _valid_config()
    app_data = config_data["app"]
    assert isinstance(app_data, dict)
    del app_data["image"]

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_config_and_secrets_can_be_empty() -> None:
    config_data = _valid_config()
    config_data["config"] = {}
    config_data["secrets"] = {}

    config = AppConfig.model_validate(config_data)

    assert config.config == {}
    assert config.secrets == {}
