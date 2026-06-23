from pathlib import Path
from typing import Any

import yaml

from k8s_forge.config_loader import load_app_config
from k8s_forge.helm_renderer import render_helm_chart, split_image
from k8s_forge.models import AppConfig

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
        Path("templates/ingress.yaml"),
        Path("templates/networkpolicy.yaml"),
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


def test_values_yaml_contains_complete_ingress_section(tmp_path: Path) -> None:
    _render_example("demo-app.yaml", tmp_path)

    values = _load_yaml(tmp_path / "demo-app" / "values.yaml")

    assert values["ingress"] == {
        "enabled": False,
        "host": "demo.local",
        "className": "nginx",
        "path": "/",
        "pathType": "Prefix",
        "tls": {"enabled": False, "secretName": None},
        "certManager": {"enabled": False, "clusterIssuer": None},
        "annotations": {},
    }


def test_ingress_template_is_generated_and_conditional(tmp_path: Path) -> None:
    _render_example("demo-app.yaml", tmp_path)

    ingress_template = (tmp_path / "demo-app" / "templates" / "ingress.yaml").read_text(
        encoding="utf-8"
    )

    assert "{{- if .Values.ingress.enabled }}" in ingress_template
    assert "kind: Ingress" in ingress_template
    assert (
        "ingressClassName: {{ .Values.ingress.className | quote }}" in ingress_template
    )
    assert "path: {{ .Values.ingress.path | quote }}" in ingress_template
    assert "pathType: {{ .Values.ingress.pathType }}" in ingress_template
    assert "number: {{ .Values.service.port }}" in ingress_template
    assert "cert-manager.io/cluster-issuer" in ingress_template
    assert "{{- if .Values.ingress.tls.enabled }}" in ingress_template


def test_two_configs_generate_different_ingress_values(tmp_path: Path) -> None:
    _render_example("demo-app.yaml", tmp_path)
    _render_example("admin-api.yaml", tmp_path)

    demo = _load_yaml(tmp_path / "demo-app" / "values.yaml")
    admin = _load_yaml(tmp_path / "admin-api" / "values.yaml")

    assert demo["ingress"]["host"] == "demo.local"
    assert admin["ingress"]["host"] == "admin.local"
    assert demo["ingress"] != admin["ingress"]


def test_values_yaml_contains_mesh_section(tmp_path: Path) -> None:
    _render_example("demo-app.yaml", tmp_path)

    values = _load_yaml(tmp_path / "demo-app" / "values.yaml")

    assert values["mesh"] == {
        "enabled": False,
        "provider": "linkerd",
        "inject": False,
        "annotations": {"linkerd.io/inject": "enabled"},
    }


def test_deployment_template_contains_conditional_mesh_annotations(
    tmp_path: Path,
) -> None:
    _render_example("demo-app.yaml", tmp_path)

    deployment_template = (
        tmp_path / "demo-app" / "templates" / "deployment.yaml"
    ).read_text(encoding="utf-8")

    assert "{{- if and .Values.mesh.enabled .Values.mesh.inject" in deployment_template
    assert "toYaml .Values.mesh.annotations" in deployment_template
    assert "annotations:" in deployment_template


def test_two_configs_generate_different_mesh_values(tmp_path: Path) -> None:
    base = {
        "app": {
            "name": "mesh-app",
            "namespace": "mesh",
            "image": "mesh-app:1.0.0",
            "containerPort": 8000,
            "replicas": 2,
        },
        "service": {"enabled": True, "port": 80},
        "mesh": {
            "enabled": True,
            "provider": "linkerd",
            "inject": True,
            "annotations": {"linkerd.io/inject": "enabled"},
        },
    }
    render_helm_chart(AppConfig.model_validate(base), tmp_path)
    _render_example("demo-app.yaml", tmp_path)

    mesh_values = _load_yaml(tmp_path / "mesh-app" / "values.yaml")
    demo_values = _load_yaml(tmp_path / "demo-app" / "values.yaml")

    assert mesh_values["mesh"]["enabled"] is True
    assert mesh_values["mesh"]["inject"] is True
    assert demo_values["mesh"]["enabled"] is False
    assert mesh_values["mesh"] != demo_values["mesh"]


def test_values_yaml_contains_network_policy_section(tmp_path: Path) -> None:
    _render_example("demo-app.yaml", tmp_path)

    values = _load_yaml(tmp_path / "demo-app" / "values.yaml")

    assert values["networkPolicy"] == {
        "enabled": False,
        "profile": "ingress-only",
        "ingress": {
            "enabled": True,
            "fromNamespaces": ["ingress-nginx"],
            "ports": [8000],
        },
        "egress": {"enabled": False},
    }


def test_network_policy_template_is_generated_and_conditional(tmp_path: Path) -> None:
    _render_example("demo-app.yaml", tmp_path)

    template = (tmp_path / "demo-app" / "templates" / "networkpolicy.yaml").read_text(
        encoding="utf-8"
    )

    assert "{{- if .Values.networkPolicy.enabled }}" in template
    assert "kind: NetworkPolicy" in template
    assert "kubernetes.io/metadata.name" in template
    assert ".Values.networkPolicy.ingress.fromNamespaces" in template
    assert ".Values.networkPolicy.ingress.ports" in template


def test_two_configs_generate_different_network_policy_values(tmp_path: Path) -> None:
    base = {
        "app": {
            "name": "netpol-app",
            "namespace": "netpol",
            "image": "netpol-app:1.0.0",
            "containerPort": 9000,
            "replicas": 2,
        },
        "service": {"enabled": True, "port": 80},
        "networkPolicy": {
            "enabled": True,
            "profile": "ingress-only",
            "ingress": {
                "enabled": True,
                "fromNamespaces": ["ingress-nginx", "edge"],
                "ports": [9000],
            },
        },
    }
    render_helm_chart(AppConfig.model_validate(base), tmp_path)
    _render_example("demo-app.yaml", tmp_path)

    netpol_values = _load_yaml(tmp_path / "netpol-app" / "values.yaml")
    demo_values = _load_yaml(tmp_path / "demo-app" / "values.yaml")

    assert netpol_values["networkPolicy"]["enabled"] is True
    assert netpol_values["networkPolicy"]["ingress"]["ports"] == [9000]
    assert netpol_values["networkPolicy"]["ingress"]["fromNamespaces"] == [
        "ingress-nginx",
        "edge",
    ]
    assert demo_values["networkPolicy"]["enabled"] is False
    assert netpol_values["networkPolicy"] != demo_values["networkPolicy"]
