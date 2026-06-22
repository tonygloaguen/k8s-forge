from pathlib import Path
from typing import Any

import yaml

from k8s_forge.config_loader import load_app_config
from k8s_forge.helm_renderer import render_helm_chart, split_image

ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _render_example(example_name: str, tmp_path: Path) -> list[Path]:
    config = load_app_config(ROOT / "examples" / example_name)
    return render_helm_chart(config, tmp_path)


def test_split_image_with_local_image_tag() -> None:
    assert split_image("weatherapi:0.1.0") == ("weatherapi", "0.1.0")


def test_split_image_with_registry_tag() -> None:
    assert split_image("ghcr.io/org/app:1.2.3") == ("ghcr.io/org/app", "1.2.3")


def test_split_image_with_registry_port_and_tag() -> None:
    assert split_image("localhost:5001/weatherapi:0.1.0") == (
        "localhost:5001/weatherapi",
        "0.1.0",
    )


def test_split_image_defaults_to_latest_without_tag() -> None:
    assert split_image("weatherapi") == ("weatherapi", "latest")


def test_render_helm_chart_generates_expected_files(tmp_path: Path) -> None:
    generated = _render_example("admin-api.yaml", tmp_path)

    assert [path.relative_to(tmp_path / "admin-api") for path in generated] == [
        Path("Chart.yaml"),
        Path("values.yaml"),
        Path("templates/_helpers.tpl"),
        Path("templates/configmap.yaml"),
        Path("templates/secret.yaml"),
        Path("templates/deployment.yaml"),
        Path("templates/service.yaml"),
        Path("templates/hpa.yaml"),
    ]


def test_chart_yaml_and_values_yaml_are_valid_yaml(tmp_path: Path) -> None:
    _render_example("admin-api.yaml", tmp_path)

    chart = _load_yaml(tmp_path / "admin-api" / "Chart.yaml")
    values = _load_yaml(tmp_path / "admin-api" / "values.yaml")

    assert chart["apiVersion"] == "v2"
    assert chart["name"] == "admin-api"
    assert values["replicaCount"] == 2


def test_values_yaml_reflects_app_config(tmp_path: Path) -> None:
    _render_example("admin-api.yaml", tmp_path)

    values = _load_yaml(tmp_path / "admin-api" / "values.yaml")

    assert values["image"] == {
        "repository": "ghcr.io/example/admin-api",
        "tag": "2.1.0",
        "pullPolicy": "IfNotPresent",
    }
    assert values["service"]["enabled"] is True
    assert values["service"]["port"] == 8081
    assert values["service"]["targetPort"] == 8080
    assert values["config"]["APP_ENV"] == "staging"
    assert values["secrets"]["enabled"] is True
    assert values["secrets"]["values"]["ADMIN_TOKEN"] == "change-me"
    assert values["resources"]["requests"]["cpu"] == "100m"
    assert values["resources"]["limits"]["memory"] == "256Mi"
    assert values["probes"]["liveness"] == "/live"
    assert values["probes"]["readiness"] == "/ready"
    assert values["autoscaling"]["enabled"] is True
    assert values["autoscaling"]["minReplicas"] == 2
    assert values["autoscaling"]["maxReplicas"] == 6
    assert values["autoscaling"]["targetCPUUtilizationPercentage"] == 70


def test_hpa_template_is_generated_and_conditional(tmp_path: Path) -> None:
    _render_example("admin-api.yaml", tmp_path)

    hpa_template = (tmp_path / "admin-api" / "templates" / "hpa.yaml").read_text(
        encoding="utf-8"
    )

    assert "{{- if .Values.autoscaling.enabled }}" in hpa_template
    assert "kind: HorizontalPodAutoscaler" in hpa_template
    assert (
        "averageUtilization: "
        "{{ .Values.autoscaling.targetCPUUtilizationPercentage }}" in hpa_template
    )


def test_helm_templates_use_expected_resources(tmp_path: Path) -> None:
    _render_example("admin-api.yaml", tmp_path)
    chart_dir = tmp_path / "admin-api" / "templates"

    assert "kind: ConfigMap" in (chart_dir / "configmap.yaml").read_text(
        encoding="utf-8"
    )
    assert "kind: Secret" in (chart_dir / "secret.yaml").read_text(encoding="utf-8")
    assert "kind: Deployment" in (chart_dir / "deployment.yaml").read_text(
        encoding="utf-8"
    )
    assert "kind: Service" in (chart_dir / "service.yaml").read_text(encoding="utf-8")


def test_two_configs_generate_different_values(tmp_path: Path) -> None:
    _render_example("demo-app.yaml", tmp_path)
    _render_example("admin-api.yaml", tmp_path)

    demo_values = (tmp_path / "demo-app" / "values.yaml").read_text(encoding="utf-8")
    admin_values = (tmp_path / "admin-api" / "values.yaml").read_text(encoding="utf-8")

    assert demo_values != admin_values
    assert "ghcr.io/example/demo-app" in demo_values
    assert "ghcr.io/example/admin-api" in admin_values


def test_render_helm_chart_does_not_delete_user_files(tmp_path: Path) -> None:
    chart_dir = tmp_path / "demo-app"
    chart_dir.mkdir()
    user_file = chart_dir / "notes.txt"
    user_file.write_text("keep me", encoding="utf-8")

    _render_example("demo-app.yaml", tmp_path)

    assert user_file.read_text(encoding="utf-8") == "keep me"
