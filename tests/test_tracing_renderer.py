import json
from pathlib import Path

import pytest

from k8s_forge.exceptions import RenderError
from k8s_forge.models import AppConfig
from k8s_forge.tracing_renderer import (
    otel_protocol_value,
    render_tracing_files,
    resolve_tracing_dashboard_title,
    resolve_tracing_service_name,
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
    config["tracing"] = {
        "enabled": True,
        "provider": "opentelemetry",
        "backend": {
            "type": "tempo",
            "namespace": "monitoring",
            "datasourceName": "Tempo",
        },
        "collector": {
            "enabled": True,
            "type": "opentelemetry-collector",
            "endpoint": "http://otel-collector.monitoring.svc.cluster.local:4318",
            "protocol": "otlp-http",
        },
        "instrumentation": {"enabled": True, "mode": "env", "serviceName": ""},
        "grafana": {"enabled": True, "dashboard": {"enabled": True, "title": ""}},
        "examples": {"enabled": True},
    }
    return config


def test_resolve_tracing_service_name_falls_back_to_app_name() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_tracing_service_name(config) == "weatherapi"


def test_resolve_tracing_dashboard_title_falls_back_to_app_name() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_tracing_dashboard_title(config) == "weatherapi"


def test_otel_protocol_value_for_http_and_grpc() -> None:
    http_config = AppConfig.model_validate(_enabled_config())
    grpc_data = _enabled_config()
    tracing = grpc_data["tracing"]
    assert isinstance(tracing, dict)
    collector = tracing["collector"]
    assert isinstance(collector, dict)
    collector["protocol"] = "otlp-grpc"
    collector["endpoint"] = "http://otel-collector.monitoring.svc.cluster.local:4317"
    grpc_config = AppConfig.model_validate(grpc_data)

    assert otel_protocol_value(http_config) == "http/protobuf"
    assert otel_protocol_value(grpc_config) == "grpc"


def test_no_files_generated_when_tracing_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    generated = render_tracing_files(config, tmp_path)

    assert generated == []
    assert not (tmp_path / "README.md").exists()


def test_tracing_renderer_generates_expected_files(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    generated = render_tracing_files(config, tmp_path)

    assert {str(path.relative_to(tmp_path)) for path in generated} == {
        "README.md",
        "opentelemetry/instrumentation-notes.md",
        "opentelemetry/otel-env.md",
        "tempo/traceql-examples.md",
        "grafana/traces-dashboard.json",
        "collector/collector-notes.md",
    }
    assert "Tracing Readiness" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_otel_env_contains_service_endpoint_and_resource_attributes(
    tmp_path: Path,
) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_tracing_files(config, tmp_path)

    env = (tmp_path / "opentelemetry" / "otel-env.md").read_text(encoding="utf-8")
    assert "OTEL_SERVICE_NAME=weatherapi" in env
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector" in env
    assert "OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf" in env
    assert "k8s.namespace.name=weather" in env


def test_otel_env_uses_grpc_protocol(tmp_path: Path) -> None:
    config_data = _enabled_config()
    tracing = config_data["tracing"]
    assert isinstance(tracing, dict)
    collector = tracing["collector"]
    assert isinstance(collector, dict)
    collector["protocol"] = "otlp-grpc"
    collector["endpoint"] = "http://otel-collector.monitoring.svc.cluster.local:4317"
    config = AppConfig.model_validate(config_data)

    render_tracing_files(config, tmp_path)

    env = (tmp_path / "opentelemetry" / "otel-env.md").read_text(encoding="utf-8")
    assert "OTEL_EXPORTER_OTLP_PROTOCOL=grpc" in env
    assert ":4317" in env


def test_traceql_examples_contain_namespace_app_and_service_name(
    tmp_path: Path,
) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_tracing_files(config, tmp_path)

    traceql = (tmp_path / "tempo" / "traceql-examples.md").read_text(encoding="utf-8")
    assert 'resource.service.name = "weatherapi"' in traceql
    assert 'resource.k8s.namespace.name = "weather"' in traceql
    assert 'span.http.route = "/weather"' in traceql
    assert "span.http.status_code >= 500" in traceql


def test_traces_dashboard_json_is_parseable_and_uses_title_fallback(
    tmp_path: Path,
) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_tracing_files(config, tmp_path)

    dashboard = json.loads(
        (tmp_path / "grafana" / "traces-dashboard.json").read_text(encoding="utf-8")
    )
    assert dashboard["uid"] == "weatherapi-traces-readiness"
    assert dashboard["title"] == "weatherapi"
    assert dashboard["tags"] == [
        "k8s-forge",
        "tracing-readiness",
        "tempo",
        "opentelemetry",
    ]
    expressions = [
        target["query"] for panel in dashboard["panels"] for target in panel["targets"]
    ]
    assert any('resource.service.name = "weatherapi"' in expr for expr in expressions)
    assert any(
        'resource.k8s.namespace.name = "weather"' in expr for expr in expressions
    )


def test_traces_dashboard_uses_configured_title(tmp_path: Path) -> None:
    config_data = _enabled_config()
    tracing = config_data["tracing"]
    assert isinstance(tracing, dict)
    grafana = tracing["grafana"]
    assert isinstance(grafana, dict)
    dashboard = grafana["dashboard"]
    assert isinstance(dashboard, dict)
    dashboard["title"] = "Weather API Traces"
    config = AppConfig.model_validate(config_data)

    render_tracing_files(config, tmp_path)

    dashboard_data = json.loads(
        (tmp_path / "grafana" / "traces-dashboard.json").read_text(encoding="utf-8")
    )
    assert dashboard_data["title"] == "Weather API Traces"


def test_optional_tracing_files_absent_when_disabled(tmp_path: Path) -> None:
    config_data = _enabled_config()
    tracing = config_data["tracing"]
    assert isinstance(tracing, dict)
    instrumentation = tracing["instrumentation"]
    grafana = tracing["grafana"]
    collector = tracing["collector"]
    examples = tracing["examples"]
    assert isinstance(instrumentation, dict)
    assert isinstance(grafana, dict)
    assert isinstance(collector, dict)
    assert isinstance(examples, dict)
    dashboard = grafana["dashboard"]
    assert isinstance(dashboard, dict)
    instrumentation["enabled"] = False
    dashboard["enabled"] = False
    collector["enabled"] = False
    examples["enabled"] = False
    config = AppConfig.model_validate(config_data)

    generated = render_tracing_files(config, tmp_path)

    assert {str(path.relative_to(tmp_path)) for path in generated} == {"README.md"}
    assert not (tmp_path / "opentelemetry" / "otel-env.md").exists()
    assert not (tmp_path / "grafana" / "traces-dashboard.json").exists()
    assert not (tmp_path / "collector" / "collector-notes.md").exists()


def test_tracing_output_contains_no_tokens_or_cluster_install_commands(
    tmp_path: Path,
) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_tracing_files(config, tmp_path)

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            tmp_path / "opentelemetry" / "instrumentation-notes.md",
            tmp_path / "opentelemetry" / "otel-env.md",
            tmp_path / "tempo" / "traceql-examples.md",
            tmp_path / "grafana" / "traces-dashboard.json",
            tmp_path / "collector" / "collector-notes.md",
        ]
    ).lower()
    assert "password" not in combined
    assert "api_key" not in combined
    assert "bearer " not in combined
    assert "kubectl apply" not in combined
    assert "helm install" not in combined
    assert "helm upgrade" not in combined
    assert "grafana api" not in combined


def test_tracing_renderer_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_tracing_files(config, tmp_path)

    with pytest.raises(RenderError, match="use --force"):
        render_tracing_files(config, tmp_path)


def test_tracing_renderer_overwrites_with_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_tracing_files(config, tmp_path)
    dashboard = tmp_path / "grafana" / "traces-dashboard.json"
    dashboard.write_text("old", encoding="utf-8")

    render_tracing_files(config, tmp_path, force=True)

    assert json.loads(dashboard.read_text(encoding="utf-8"))["title"] == "weatherapi"
