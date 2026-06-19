import pytest
from pydantic import ValidationError

from k8s_forge.models import AppConfig


def test_minimal_app_config_is_valid() -> None:
    config = AppConfig.model_validate(
        {
            "app": {
                "name": "demo-app",
                "namespace": "demo",
            },
            "image": {
                "repository": "nginx",
                "tag": "1.27",
            },
        }
    )

    assert config.app.name == "demo-app"
    assert config.app.namespace == "demo"
    assert config.deployment.replicas == 1
    assert config.service.type == "ClusterIP"


def test_app_config_rejects_invalid_port() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate(
            {
                "app": {
                    "name": "demo-app",
                    "namespace": "demo",
                },
                "image": {
                    "repository": "nginx",
                    "tag": "1.27",
                },
                "service": {
                    "port": 70000,
                },
            }
        )
