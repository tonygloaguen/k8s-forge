import json
from pathlib import Path

import pytest

from k8s_forge.exceptions import RenderError
from k8s_forge.logging_renderer import (
    render_logging_files,
    resolve_logging_dashboard_title,
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
    config["logging"] = {
        "enabled": True,
        "provider": "loki",
        "applicationLogs": {"enabled": True, "source": "stdout"},
        "loki": {"namespace": "monitoring", "datasourceName": "Loki"},
        "collector": {"enabled": True, "type": "promtail"},
        "grafana": {"enabled": True, "dashboard": {"enabled": True, "title": ""}},
        "queries": {"enabled": True},
    }
    return config


def test_resolve_logging_dashboard_title_falls_back_to_app_name() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_logging_dashboard_title(config) == "weatherapi"


def test_no_files_generated_when_logging_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    generated = render_logging_files(config, tmp_path)

    assert generated == []
    assert not (tmp_path / "README.md").exists()


def test_logging_renderer_generates_expected_files(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    generated = render_logging_files(config, tmp_path)

    assert {str(path.relative_to(tmp_path)) for path in generated} == {
        "README.md",
        "loki/logql-queries.md",
        "grafana/logs-dashboard.json",
        "collector/collector-notes.md",
    }
    assert "Logging Readiness" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_logql_queries_contain_namespace_and_app(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_logging_files(config, tmp_path)

    queries = (tmp_path / "loki" / "logql-queries.md").read_text(encoding="utf-8")
    assert '{namespace="weather"}' in queries
    assert '{namespace="weather", app="weatherapi"}' in queries
    assert "count_over_time" in queries
    assert "rate" in queries


def test_logs_dashboard_json_is_parseable_and_uses_title_fallback(
    tmp_path: Path,
) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_logging_files(config, tmp_path)

    dashboard = json.loads(
        (tmp_path / "grafana" / "logs-dashboard.json").read_text(encoding="utf-8")
    )
    assert dashboard["uid"] == "weatherapi-logs-readiness"
    assert dashboard["title"] == "weatherapi"
    assert dashboard["tags"] == ["k8s-forge", "logging-readiness", "loki"]
    expressions = [
        target["expr"] for panel in dashboard["panels"] for target in panel["targets"]
    ]
    assert '{namespace="weather", app="weatherapi"}' in expressions


def test_logs_dashboard_uses_configured_title(tmp_path: Path) -> None:
    config_data = _enabled_config()
    logging = config_data["logging"]
    assert isinstance(logging, dict)
    grafana = logging["grafana"]
    assert isinstance(grafana, dict)
    dashboard = grafana["dashboard"]
    assert isinstance(dashboard, dict)
    dashboard["title"] = "Weather API Logs"
    config = AppConfig.model_validate(config_data)

    render_logging_files(config, tmp_path)

    dashboard_data = json.loads(
        (tmp_path / "grafana" / "logs-dashboard.json").read_text(encoding="utf-8")
    )
    assert dashboard_data["title"] == "Weather API Logs"


def test_dashboard_absent_when_disabled(tmp_path: Path) -> None:
    config_data = _enabled_config()
    logging = config_data["logging"]
    assert isinstance(logging, dict)
    grafana = logging["grafana"]
    assert isinstance(grafana, dict)
    dashboard = grafana["dashboard"]
    assert isinstance(dashboard, dict)
    dashboard["enabled"] = False
    config = AppConfig.model_validate(config_data)

    generated = render_logging_files(config, tmp_path)

    assert "grafana/logs-dashboard.json" not in {
        str(path.relative_to(tmp_path)) for path in generated
    }
    assert not (tmp_path / "grafana" / "logs-dashboard.json").exists()


def test_collector_notes_absent_when_disabled(tmp_path: Path) -> None:
    config_data = _enabled_config()
    logging = config_data["logging"]
    assert isinstance(logging, dict)
    collector = logging["collector"]
    assert isinstance(collector, dict)
    collector["enabled"] = False
    config = AppConfig.model_validate(config_data)

    generated = render_logging_files(config, tmp_path)

    assert "collector/collector-notes.md" not in {
        str(path.relative_to(tmp_path)) for path in generated
    }
    assert not (tmp_path / "collector" / "collector-notes.md").exists()


def test_logging_output_contains_no_tokens_or_cluster_install_commands(
    tmp_path: Path,
) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_logging_files(config, tmp_path)

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            tmp_path / "loki" / "logql-queries.md",
            tmp_path / "grafana" / "logs-dashboard.json",
            tmp_path / "collector" / "collector-notes.md",
        ]
    ).lower()
    assert "token" not in combined
    assert "kubectl apply" not in combined
    assert "helm install" not in combined
    assert "helm upgrade" not in combined
    assert "grafana api" not in combined


def test_logging_renderer_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_logging_files(config, tmp_path)

    with pytest.raises(RenderError, match="use --force"):
        render_logging_files(config, tmp_path)


def test_logging_renderer_overwrites_with_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_logging_files(config, tmp_path)
    dashboard = tmp_path / "grafana" / "logs-dashboard.json"
    dashboard.write_text("old", encoding="utf-8")

    render_logging_files(config, tmp_path, force=True)

    assert json.loads(dashboard.read_text(encoding="utf-8"))["title"] == "weatherapi"
