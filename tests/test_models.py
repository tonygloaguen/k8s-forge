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
        "autoscaling": {
            "enabled": False,
            "minReplicas": 2,
            "maxReplicas": 6,
            "targetCPUUtilizationPercentage": 70,
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


def test_autoscaling_defaults_when_section_absent() -> None:
    config_data = _valid_config()
    del config_data["autoscaling"]

    config = AppConfig.model_validate(config_data)

    assert config.autoscaling.enabled is False
    assert config.autoscaling.minReplicas == 2
    assert config.autoscaling.maxReplicas == 6
    assert config.autoscaling.targetCPUUtilizationPercentage == 70


def test_autoscaling_enabled_config_is_valid() -> None:
    config_data = _valid_config()
    autoscaling = config_data["autoscaling"]
    assert isinstance(autoscaling, dict)
    autoscaling["enabled"] = True
    autoscaling["minReplicas"] = 2
    autoscaling["maxReplicas"] = 5
    autoscaling["targetCPUUtilizationPercentage"] = 60

    config = AppConfig.model_validate(config_data)

    assert config.autoscaling.enabled is True
    assert config.autoscaling.minReplicas == 2
    assert config.autoscaling.maxReplicas == 5
    assert config.autoscaling.targetCPUUtilizationPercentage == 60


def test_autoscaling_rejects_zero_min_replicas() -> None:
    config_data = _valid_config()
    autoscaling = config_data["autoscaling"]
    assert isinstance(autoscaling, dict)
    autoscaling["enabled"] = True
    autoscaling["minReplicas"] = 0

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_autoscaling_rejects_max_below_min() -> None:
    config_data = _valid_config()
    autoscaling = config_data["autoscaling"]
    assert isinstance(autoscaling, dict)
    autoscaling["enabled"] = True
    autoscaling["minReplicas"] = 4
    autoscaling["maxReplicas"] = 3

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_autoscaling_rejects_invalid_cpu_target() -> None:
    config_data = _valid_config()
    autoscaling = config_data["autoscaling"]
    assert isinstance(autoscaling, dict)
    autoscaling["enabled"] = True
    autoscaling["targetCPUUtilizationPercentage"] = 101

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ingress_defaults_when_section_absent() -> None:
    config_data = _valid_config()
    del config_data["ingress"]

    config = AppConfig.model_validate(config_data)

    assert config.ingress.enabled is False
    assert config.ingress.host is None
    assert config.ingress.className == "nginx"
    assert config.ingress.path == "/"
    assert config.ingress.pathType == "Prefix"
    assert config.ingress.tls.enabled is False
    assert config.ingress.certManager.enabled is False
    assert config.ingress.annotations == {}


def test_ingress_disabled_with_null_host_is_valid() -> None:
    config_data = _valid_config()
    config_data["ingress"] = {"enabled": False, "host": None}

    config = AppConfig.model_validate(config_data)

    assert config.ingress.enabled is False
    assert config.ingress.host is None


def test_ingress_enabled_requires_host() -> None:
    config_data = _valid_config()
    config_data["ingress"] = {"enabled": True, "host": None}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ingress_enabled_requires_service() -> None:
    config_data = _valid_config()
    service = config_data["service"]
    assert isinstance(service, dict)
    service["enabled"] = False
    config_data["ingress"] = {"enabled": True, "host": "demo.local"}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ingress_tls_requires_secret_name() -> None:
    config_data = _valid_config()
    config_data["ingress"] = {
        "enabled": True,
        "host": "demo.local",
        "tls": {"enabled": True, "secretName": None},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ingress_cert_manager_requires_cluster_issuer() -> None:
    config_data = _valid_config()
    config_data["ingress"] = {
        "enabled": True,
        "host": "demo.local",
        "certManager": {"enabled": True, "clusterIssuer": None},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ingress_rejects_path_without_slash() -> None:
    config_data = _valid_config()
    config_data["ingress"] = {
        "enabled": True,
        "host": "demo.local",
        "path": "weather",
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ingress_rejects_invalid_path_type() -> None:
    config_data = _valid_config()
    config_data["ingress"] = {
        "enabled": True,
        "host": "demo.local",
        "pathType": "Invalid",
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_mesh_defaults_when_section_absent() -> None:
    config_data = _valid_config()
    config_data.pop("mesh", None)

    config = AppConfig.model_validate(config_data)

    assert config.mesh.enabled is False
    assert config.mesh.provider == "linkerd"
    assert config.mesh.inject is False
    assert config.mesh.annotations == {"linkerd.io/inject": "enabled"}


def test_mesh_accepts_linkerd_provider() -> None:
    config_data = _valid_config()
    config_data["mesh"] = {
        "enabled": True,
        "provider": "linkerd",
        "inject": False,
        "annotations": {"linkerd.io/inject": "enabled"},
    }

    config = AppConfig.model_validate(config_data)

    assert config.mesh.enabled is True
    assert config.mesh.provider == "linkerd"
    assert config.mesh.inject is False


def test_mesh_rejects_invalid_provider() -> None:
    config_data = _valid_config()
    config_data["mesh"] = {
        "enabled": True,
        "provider": "istio",
        "inject": True,
        "annotations": {"sidecar.istio.io/inject": "true"},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_mesh_inject_true_is_valid() -> None:
    config_data = _valid_config()
    config_data["mesh"] = {
        "enabled": True,
        "provider": "linkerd",
        "inject": True,
        "annotations": {"linkerd.io/inject": "enabled"},
    }

    config = AppConfig.model_validate(config_data)

    assert config.mesh.inject is True


def test_mesh_preserves_custom_annotations() -> None:
    config_data = _valid_config()
    config_data["mesh"] = {
        "enabled": True,
        "provider": "linkerd",
        "inject": True,
        "annotations": {
            "linkerd.io/inject": "enabled",
            "config.linkerd.io/proxy-cpu-request": "20m",
        },
    }

    config = AppConfig.model_validate(config_data)

    assert config.mesh.annotations == {
        "linkerd.io/inject": "enabled",
        "config.linkerd.io/proxy-cpu-request": "20m",
    }
