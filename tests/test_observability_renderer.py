import json
from pathlib import Path

import pytest
import yaml

from k8s_forge.exceptions import RenderError
from k8s_forge.models import AppConfig
from k8s_forge.observability_renderer import (
    render_observability_files,
    resolve_dashboard_title,
    resolve_service_monitor_namespace,
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
    config["observability"] = {
        "enabled": True,
        "provider": "prometheus",
        "metrics": {
            "enabled": True,
            "path": "/metrics",
            "portName": "http",
            "interval": "30s",
        },
        "serviceMonitor": {
            "enabled": True,
            "namespace": "",
            "labels": {"release": "kube-prometheus-stack"},
        },
        "grafana": {
            "enabled": True,
            "dashboard": {"enabled": True, "title": ""},
        },
        "alerts": {"enabled": False},
    }
    return config


def test_resolve_service_monitor_namespace_falls_back_to_app_namespace() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_service_monitor_namespace(config) == "weather"


def test_resolve_dashboard_title_falls_back_to_app_name() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_dashboard_title(config) == "weatherapi"


def test_no_files_generated_when_observability_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    generated = render_observability_files(config, tmp_path)

    assert generated == []
    assert not (tmp_path / "README.md").exists()


def test_observability_renderer_generates_expected_files(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    generated = render_observability_files(config, tmp_path)

    assert {str(path.relative_to(tmp_path)) for path in generated} == {
        "README.md",
        "prometheus/servicemonitor.yaml",
        "grafana/dashboard.json",
    }
    assert "Observability Readiness" in (tmp_path / "README.md").read_text(
        encoding="utf-8"
    )


def test_service_monitor_yaml_is_parseable_and_targets_service(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_observability_files(config, tmp_path)

    monitor = yaml.safe_load(
        (tmp_path / "prometheus" / "servicemonitor.yaml").read_text(encoding="utf-8")
    )
    assert monitor["apiVersion"] == "monitoring.coreos.com/v1"
    assert monitor["kind"] == "ServiceMonitor"
    assert monitor["metadata"]["name"] == "weatherapi"
    assert monitor["metadata"]["namespace"] == "weather"
    assert monitor["metadata"]["labels"]["app.kubernetes.io/name"] == "weatherapi"
    assert monitor["metadata"]["labels"]["release"] == "kube-prometheus-stack"
    assert monitor["spec"]["selector"]["matchLabels"] == {"app": "weatherapi"}
    assert monitor["spec"]["endpoints"] == [
        {"port": "http", "path": "/metrics", "interval": "30s"}
    ]


def test_service_monitor_uses_configured_namespace_path_port_and_interval(
    tmp_path: Path,
) -> None:
    config_data = _enabled_config()
    observability = config_data["observability"]
    assert isinstance(observability, dict)
    metrics = observability["metrics"]
    service_monitor = observability["serviceMonitor"]
    assert isinstance(metrics, dict)
    assert isinstance(service_monitor, dict)
    metrics["path"] = "/custom-metrics"
    metrics["portName"] = "metrics"
    metrics["interval"] = "1m"
    service_monitor["namespace"] = "monitoring"
    config = AppConfig.model_validate(config_data)

    render_observability_files(config, tmp_path)

    monitor = yaml.safe_load(
        (tmp_path / "prometheus" / "servicemonitor.yaml").read_text(encoding="utf-8")
    )
    endpoint = monitor["spec"]["endpoints"][0]
    assert monitor["metadata"]["namespace"] == "monitoring"
    assert endpoint["path"] == "/custom-metrics"
    assert endpoint["port"] == "metrics"
    assert endpoint["interval"] == "1m"


def test_dashboard_json_is_parseable_and_uses_title_fallback(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_observability_files(config, tmp_path)

    dashboard = json.loads(
        (tmp_path / "grafana" / "dashboard.json").read_text(encoding="utf-8")
    )
    assert dashboard["title"] == "weatherapi"
    assert dashboard["panels"]
    assert dashboard["tags"] == ["k8s-forge", "observability-readiness"]


def test_dashboard_uses_configured_title(tmp_path: Path) -> None:
    config_data = _enabled_config()
    observability = config_data["observability"]
    assert isinstance(observability, dict)
    grafana = observability["grafana"]
    assert isinstance(grafana, dict)
    dashboard = grafana["dashboard"]
    assert isinstance(dashboard, dict)
    dashboard["title"] = "Weather API Observability"
    config = AppConfig.model_validate(config_data)

    render_observability_files(config, tmp_path)

    dashboard_data = json.loads(
        (tmp_path / "grafana" / "dashboard.json").read_text(encoding="utf-8")
    )
    assert dashboard_data["title"] == "Weather API Observability"


def test_dashboard_absent_when_disabled(tmp_path: Path) -> None:
    config_data = _enabled_config()
    observability = config_data["observability"]
    assert isinstance(observability, dict)
    grafana = observability["grafana"]
    assert isinstance(grafana, dict)
    dashboard = grafana["dashboard"]
    assert isinstance(dashboard, dict)
    dashboard["enabled"] = False
    config = AppConfig.model_validate(config_data)

    generated = render_observability_files(config, tmp_path)

    assert "grafana/dashboard.json" not in {
        str(path.relative_to(tmp_path)) for path in generated
    }
    assert not (tmp_path / "grafana" / "dashboard.json").exists()


def test_observability_output_contains_no_secret_token_or_apply_commands(
    tmp_path: Path,
) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_observability_files(config, tmp_path)

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            tmp_path / "prometheus" / "servicemonitor.yaml",
            tmp_path / "grafana" / "dashboard.json",
        ]
    ).lower()
    assert (
        "secret"
        not in (tmp_path / "prometheus" / "servicemonitor.yaml")
        .read_text(encoding="utf-8")
        .lower()
    )
    assert "token" not in combined
    assert "kubectl apply" not in combined
    assert "helm install" not in combined
    assert "grafana api" not in combined


def test_observability_renderer_refuses_to_overwrite_without_force(
    tmp_path: Path,
) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_observability_files(config, tmp_path)

    with pytest.raises(RenderError, match="use --force"):
        render_observability_files(config, tmp_path)


def test_observability_renderer_overwrites_with_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_observability_files(config, tmp_path)
    dashboard = tmp_path / "grafana" / "dashboard.json"
    dashboard.write_text("old", encoding="utf-8")

    render_observability_files(config, tmp_path, force=True)

    assert json.loads(dashboard.read_text(encoding="utf-8"))["title"] == "weatherapi"
