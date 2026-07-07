from pathlib import Path
from typing import Any

import yaml

from k8s_forge.config_loader import load_app_config
from k8s_forge.models import AppConfig
from k8s_forge.renderer import render_manifests

ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _render_example(example_name: str, tmp_path: Path) -> list[Path]:
    config = load_app_config(ROOT / "examples" / example_name)
    return render_manifests(config, tmp_path)


def _base_config() -> dict[str, object]:
    return {
        "app": {
            "name": "generic-web",
            "namespace": "generic",
            "image": "ghcr.io/example/generic-web:1.0.0",
            "containerPort": 9000,
            "replicas": 1,
        },
        "config": {"APP_ENV": "test"},
        "secrets": {"API_TOKEN": "change-me"},
        "service": {"enabled": True, "port": 9001},
        "resources": {},
        "probes": {},
        "ingress": {"enabled": False},
    }


def test_render_generates_expected_files_for_demo_app(tmp_path: Path) -> None:
    generated = _render_example("demo-app.yaml", tmp_path)

    assert [path.name for path in generated] == [
        "00-namespace.yaml",
        "10-configmap.yaml",
        "20-secret.yaml",
        "30-deployment.yaml",
        "40-service.yaml",
    ]
    for path in generated:
        assert path.exists()


def test_render_generates_expected_files_for_admin_api(tmp_path: Path) -> None:
    generated = _render_example("admin-api.yaml", tmp_path)

    assert [path.name for path in generated] == [
        "00-namespace.yaml",
        "10-configmap.yaml",
        "20-secret.yaml",
        "30-deployment.yaml",
        "40-service.yaml",
        "50-hpa.yaml",
    ]


def test_demo_deployment_contains_demo_image(tmp_path: Path) -> None:
    _render_example("demo-app.yaml", tmp_path)
    deployment = _load_yaml(tmp_path / "30-deployment.yaml")

    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "ghcr.io/example/demo-app:1.0.0"


def test_admin_deployment_contains_admin_image(tmp_path: Path) -> None:
    _render_example("admin-api.yaml", tmp_path)
    deployment = _load_yaml(tmp_path / "30-deployment.yaml")

    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "ghcr.io/example/admin-api:2.1.0"


def test_service_target_port_matches_container_port(tmp_path: Path) -> None:
    _render_example("admin-api.yaml", tmp_path)
    service = _load_yaml(tmp_path / "40-service.yaml")

    assert service["spec"]["ports"][0]["targetPort"] == 8080


def test_service_port_is_named_http_for_service_monitor(tmp_path: Path) -> None:
    _render_example("demo-app.yaml", tmp_path)
    service = _load_yaml(tmp_path / "40-service.yaml")

    assert service["spec"]["ports"][0]["name"] == "http"


def test_service_selector_matches_pod_template_labels(tmp_path: Path) -> None:
    _render_example("demo-app.yaml", tmp_path)
    service = _load_yaml(tmp_path / "40-service.yaml")
    deployment = _load_yaml(tmp_path / "30-deployment.yaml")

    selector = service["spec"]["selector"]
    pod_labels = deployment["spec"]["template"]["metadata"]["labels"]
    for key, value in selector.items():
        assert pod_labels[key] == value


def test_configmap_absent_if_config_empty(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["config"] = {}
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)

    assert not (tmp_path / "10-configmap.yaml").exists()


def test_secret_absent_if_secrets_empty(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["secrets"] = {}
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)

    assert not (tmp_path / "20-secret.yaml").exists()


def test_service_absent_if_service_disabled(tmp_path: Path) -> None:
    config_data = _base_config()
    service = config_data["service"]
    assert isinstance(service, dict)
    service["enabled"] = False
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)

    assert not (tmp_path / "40-service.yaml").exists()


def test_env_from_excludes_configmap_when_config_empty(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["config"] = {}
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)
    deployment = _load_yaml(tmp_path / "30-deployment.yaml")

    container = deployment["spec"]["template"]["spec"]["containers"][0]
    env_from = container["envFrom"]
    assert {next(iter(source)) for source in env_from} == {"secretRef"}


def test_env_from_excludes_secret_when_secrets_empty(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["secrets"] = {}
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)
    deployment = _load_yaml(tmp_path / "30-deployment.yaml")

    container = deployment["spec"]["template"]["spec"]["containers"][0]
    env_from = container["envFrom"]
    assert {next(iter(source)) for source in env_from} == {"configMapRef"}


def test_env_from_absent_when_config_and_secrets_empty(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["config"] = {}
    config_data["secrets"] = {}
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)
    deployment = _load_yaml(tmp_path / "30-deployment.yaml")

    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert "envFrom" not in container


def test_generated_yaml_files_are_parseable(tmp_path: Path) -> None:
    generated = _render_example("demo-app.yaml", tmp_path)

    for path in generated:
        assert _load_yaml(path)["kind"]


def test_renderer_does_not_delete_user_files(tmp_path: Path) -> None:
    user_file = tmp_path / "notes.txt"
    user_file.write_text("keep me", encoding="utf-8")

    _render_example("demo-app.yaml", tmp_path)

    assert user_file.read_text(encoding="utf-8") == "keep me"


def test_hpa_absent_when_autoscaling_disabled(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["autoscaling"] = {
        "enabled": False,
        "minReplicas": 2,
        "maxReplicas": 6,
        "targetCPUUtilizationPercentage": 70,
    }
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)

    assert not (tmp_path / "50-hpa.yaml").exists()


def test_hpa_generated_when_autoscaling_enabled(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["autoscaling"] = {
        "enabled": True,
        "minReplicas": 2,
        "maxReplicas": 6,
        "targetCPUUtilizationPercentage": 70,
    }
    config = AppConfig.model_validate(config_data)

    generated = render_manifests(config, tmp_path)

    assert "50-hpa.yaml" in [path.name for path in generated]
    assert (tmp_path / "50-hpa.yaml").exists()


def test_hpa_yaml_targets_deployment_and_namespace(tmp_path: Path) -> None:
    _render_example("admin-api.yaml", tmp_path)

    hpa = _load_yaml(tmp_path / "50-hpa.yaml")

    assert hpa["apiVersion"] == "autoscaling/v2"
    assert hpa["kind"] == "HorizontalPodAutoscaler"
    assert hpa["metadata"]["name"] == "admin-api"
    assert hpa["metadata"]["namespace"] == "admin"
    assert hpa["spec"]["scaleTargetRef"] == {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "name": "admin-api",
    }


def test_hpa_labels_match_status_selector(tmp_path: Path) -> None:
    _render_example("admin-api.yaml", tmp_path)

    hpa = _load_yaml(tmp_path / "50-hpa.yaml")
    labels = hpa["metadata"]["labels"]

    assert labels["app"] == "admin-api"
    assert labels["app.kubernetes.io/managed-by"] == "k8s-forge"


def test_hpa_values_come_from_config(tmp_path: Path) -> None:
    _render_example("admin-api.yaml", tmp_path)

    hpa = _load_yaml(tmp_path / "50-hpa.yaml")

    assert hpa["spec"]["minReplicas"] == 2
    assert hpa["spec"]["maxReplicas"] == 6
    metric = hpa["spec"]["metrics"][0]
    assert metric["resource"]["target"]["averageUtilization"] == 70


def test_renderer_cleans_previous_hpa_file_when_disabled(tmp_path: Path) -> None:
    hpa_file = tmp_path / "50-hpa.yaml"
    hpa_file.write_text("old hpa", encoding="utf-8")

    _render_example("demo-app.yaml", tmp_path)

    assert not hpa_file.exists()


def test_ingress_absent_when_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    render_manifests(config, tmp_path)

    assert not (tmp_path / "60-ingress.yaml").exists()


def test_ingress_generated_when_enabled(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["ingress"] = {
        "enabled": True,
        "host": "generic.local",
        "className": "nginx",
        "path": "/",
        "pathType": "Prefix",
        "tls": {"enabled": False, "secretName": None},
        "certManager": {"enabled": False, "clusterIssuer": None},
        "annotations": {"nginx.ingress.kubernetes.io/proxy-body-size": "1m"},
    }
    config = AppConfig.model_validate(config_data)

    generated = render_manifests(config, tmp_path)
    ingress = _load_yaml(tmp_path / "60-ingress.yaml")

    assert "60-ingress.yaml" in [path.name for path in generated]
    assert ingress["apiVersion"] == "networking.k8s.io/v1"
    assert ingress["kind"] == "Ingress"
    assert ingress["metadata"]["name"] == "generic-web"
    assert ingress["metadata"]["namespace"] == "generic"
    assert ingress["spec"]["ingressClassName"] == "nginx"
    assert ingress["spec"]["rules"][0]["host"] == "generic.local"
    path_rule = ingress["spec"]["rules"][0]["http"]["paths"][0]
    assert path_rule["path"] == "/"
    assert path_rule["pathType"] == "Prefix"
    assert path_rule["backend"]["service"]["name"] == "generic-web"
    assert path_rule["backend"]["service"]["port"]["number"] == 9001
    assert "tls" not in ingress["spec"]


def test_ingress_tls_and_cert_manager_annotations(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["ingress"] = {
        "enabled": True,
        "host": "generic.local",
        "className": "nginx",
        "path": "/weather",
        "pathType": "Prefix",
        "tls": {"enabled": True, "secretName": "generic-tls"},
        "certManager": {"enabled": True, "clusterIssuer": "selfsigned-dev"},
        "annotations": {"nginx.ingress.kubernetes.io/rewrite-target": "/"},
    }
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)
    ingress = _load_yaml(tmp_path / "60-ingress.yaml")

    assert ingress["metadata"]["annotations"] == {
        "nginx.ingress.kubernetes.io/rewrite-target": "/",
        "cert-manager.io/cluster-issuer": "selfsigned-dev",
    }
    assert ingress["spec"]["tls"] == [
        {"hosts": ["generic.local"], "secretName": "generic-tls"}
    ]


def test_renderer_cleans_previous_ingress_file_when_disabled(tmp_path: Path) -> None:
    ingress_file = tmp_path / "60-ingress.yaml"
    ingress_file.write_text("old ingress", encoding="utf-8")

    render_manifests(AppConfig.model_validate(_base_config()), tmp_path)

    assert not ingress_file.exists()


def test_mesh_disabled_does_not_add_pod_template_annotations(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    render_manifests(config, tmp_path)
    deployment = _load_yaml(tmp_path / "30-deployment.yaml")

    metadata = deployment["spec"]["template"]["metadata"]
    assert "annotations" not in metadata


def test_mesh_inject_adds_linkerd_annotation_to_pod_template(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["mesh"] = {
        "enabled": True,
        "provider": "linkerd",
        "inject": True,
        "annotations": {"linkerd.io/inject": "enabled"},
    }
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)
    deployment = _load_yaml(tmp_path / "30-deployment.yaml")

    annotations = deployment["spec"]["template"]["metadata"]["annotations"]
    assert annotations == {"linkerd.io/inject": "enabled"}


def test_mesh_inject_preserves_pod_template_labels(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["mesh"] = {
        "enabled": True,
        "provider": "linkerd",
        "inject": True,
        "annotations": {"linkerd.io/inject": "enabled"},
    }
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)
    deployment = _load_yaml(tmp_path / "30-deployment.yaml")

    labels = deployment["spec"]["template"]["metadata"]["labels"]
    assert labels["app"] == "generic-web"
    assert labels["app.kubernetes.io/managed-by"] == "k8s-forge"


def test_mesh_does_not_annotate_namespace(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["mesh"] = {
        "enabled": True,
        "provider": "linkerd",
        "inject": True,
        "annotations": {"linkerd.io/inject": "enabled"},
    }
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)
    namespace = _load_yaml(tmp_path / "00-namespace.yaml")

    assert "annotations" not in namespace["metadata"]


def test_network_policy_absent_when_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    render_manifests(config, tmp_path)

    assert not (tmp_path / "70-networkpolicy.yaml").exists()


def test_network_policy_generated_when_enabled(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["networkPolicy"] = {
        "enabled": True,
        "profile": "ingress-only",
    }
    config = AppConfig.model_validate(config_data)

    generated = render_manifests(config, tmp_path)
    network_policy = _load_yaml(tmp_path / "70-networkpolicy.yaml")

    assert "70-networkpolicy.yaml" in [path.name for path in generated]
    assert network_policy["apiVersion"] == "networking.k8s.io/v1"
    assert network_policy["kind"] == "NetworkPolicy"
    assert network_policy["metadata"]["name"] == "generic-web-ingress-only"
    assert network_policy["metadata"]["namespace"] == "generic"


def test_network_policy_yaml_uses_app_selector_namespace_and_container_port(
    tmp_path: Path,
) -> None:
    config_data = _base_config()
    config_data["networkPolicy"] = {
        "enabled": True,
        "profile": "ingress-only",
    }
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)
    network_policy = _load_yaml(tmp_path / "70-networkpolicy.yaml")

    assert network_policy["spec"]["podSelector"]["matchLabels"] == {
        "app": "generic-web",
        "app.kubernetes.io/name": "generic-web",
    }
    assert network_policy["spec"]["policyTypes"] == ["Ingress"]
    rule = network_policy["spec"]["ingress"][0]
    assert rule["from"] == [
        {
            "namespaceSelector": {
                "matchLabels": {"kubernetes.io/metadata.name": "ingress-nginx"}
            }
        }
    ]
    assert rule["ports"] == [{"protocol": "TCP", "port": 9000}]


def test_network_policy_uses_configured_namespaces_and_ports(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["networkPolicy"] = {
        "enabled": True,
        "profile": "ingress-only",
        "ingress": {
            "enabled": True,
            "fromNamespaces": ["ingress-nginx", "edge"],
            "ports": [9000, 9443],
        },
    }
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)
    network_policy = _load_yaml(tmp_path / "70-networkpolicy.yaml")
    rule = network_policy["spec"]["ingress"][0]

    assert rule["from"] == [
        {
            "namespaceSelector": {
                "matchLabels": {"kubernetes.io/metadata.name": "ingress-nginx"}
            }
        },
        {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "edge"}}},
    ]
    assert rule["ports"] == [
        {"protocol": "TCP", "port": 9000},
        {"protocol": "TCP", "port": 9443},
    ]


def test_renderer_cleans_previous_network_policy_file_when_disabled(
    tmp_path: Path,
) -> None:
    network_policy_file = tmp_path / "70-networkpolicy.yaml"
    network_policy_file.write_text("old network policy", encoding="utf-8")

    render_manifests(AppConfig.model_validate(_base_config()), tmp_path)

    assert not network_policy_file.exists()


def test_kyverno_policy_absent_when_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    render_manifests(config, tmp_path)

    assert not (tmp_path / "80-kyverno-policy.yaml").exists()


def test_kyverno_policy_generated_when_enabled(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["policy"] = {"enabled": True, "provider": "kyverno"}
    config = AppConfig.model_validate(config_data)

    generated = render_manifests(config, tmp_path)
    policy = _load_yaml(tmp_path / "80-kyverno-policy.yaml")

    assert "80-kyverno-policy.yaml" in [path.name for path in generated]
    assert policy["apiVersion"] == "kyverno.io/v1"
    assert policy["kind"] == "Policy"
    assert policy["metadata"]["name"] == "generic-web-baseline"
    assert policy["metadata"]["namespace"] == "generic"


def test_kyverno_policy_uses_audit_background_and_rules(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["policy"] = {"enabled": True, "provider": "kyverno"}
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)
    policy = _load_yaml(tmp_path / "80-kyverno-policy.yaml")

    assert policy["spec"]["validationFailureAction"] == "Audit"
    assert policy["spec"]["background"] is True
    rule_names = {rule["name"] for rule in policy["spec"]["rules"]}
    assert rule_names == {
        "require-recommended-labels",
        "disallow-privileged-containers",
        "require-run-as-non-root",
        "require-resources",
        "disallow-latest-tag",
    }
    assert "ClusterPolicy" not in (tmp_path / "80-kyverno-policy.yaml").read_text(
        encoding="utf-8"
    )


def test_kyverno_policy_respects_disabled_rules(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["policy"] = {
        "enabled": True,
        "provider": "kyverno",
        "rules": {
            "requireRecommendedLabels": True,
            "disallowPrivilegedContainers": False,
            "requireRunAsNonRoot": False,
            "requireResources": True,
            "disallowLatestTag": False,
        },
    }
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)
    policy = _load_yaml(tmp_path / "80-kyverno-policy.yaml")

    rule_names = {rule["name"] for rule in policy["spec"]["rules"]}
    assert rule_names == {"require-recommended-labels", "require-resources"}


def test_renderer_cleans_previous_kyverno_policy_file_when_disabled(
    tmp_path: Path,
) -> None:
    policy_file = tmp_path / "80-kyverno-policy.yaml"
    policy_file.write_text("old policy", encoding="utf-8")

    render_manifests(AppConfig.model_validate(_base_config()), tmp_path)

    assert not policy_file.exists()


def test_worker_workload_generates_deployment_without_service(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["workload"] = {
        "type": "worker",
        "command": ["python"],
        "args": ["-m", "worker"],
    }
    config_data["service"] = {"enabled": False, "port": 80}
    config = AppConfig.model_validate(config_data)

    generated = render_manifests(config, tmp_path)

    assert "30-deployment.yaml" in [path.name for path in generated]
    assert not (tmp_path / "40-service.yaml").exists()
    deployment = _load_yaml(tmp_path / "30-deployment.yaml")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["command"] == ["python"]
    assert container["args"] == ["-m", "worker"]


def test_job_workload_generates_job_without_service(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["workload"] = {
        "type": "job",
        "command": ["python"],
        "args": ["-m", "network_mapper"],
        "restartPolicy": "OnFailure",
    }
    config_data["service"] = {"enabled": False, "port": 80}
    config = AppConfig.model_validate(config_data)

    generated = render_manifests(config, tmp_path)

    assert "30-job.yaml" in [path.name for path in generated]
    assert not (tmp_path / "30-deployment.yaml").exists()
    assert not (tmp_path / "40-service.yaml").exists()
    job = _load_yaml(tmp_path / "30-job.yaml")
    assert job["apiVersion"] == "batch/v1"
    assert job["kind"] == "Job"
    spec = job["spec"]["template"]["spec"]
    assert spec["restartPolicy"] == "OnFailure"
    assert spec["containers"][0]["command"] == ["python"]
    assert spec["containers"][0]["args"] == ["-m", "network_mapper"]


def test_cronjob_workload_generates_cronjob_without_service(tmp_path: Path) -> None:
    config_data = _base_config()
    config_data["workload"] = {
        "type": "cronjob",
        "command": ["python"],
        "args": ["-m", "network_mapper"],
        "restartPolicy": "OnFailure",
        "schedule": "0 * * * *",
    }
    config_data["service"] = {"enabled": False, "port": 80}
    config = AppConfig.model_validate(config_data)

    generated = render_manifests(config, tmp_path)

    assert "30-cronjob.yaml" in [path.name for path in generated]
    assert not (tmp_path / "30-deployment.yaml").exists()
    assert not (tmp_path / "40-service.yaml").exists()
    cronjob = _load_yaml(tmp_path / "30-cronjob.yaml")
    assert cronjob["apiVersion"] == "batch/v1"
    assert cronjob["kind"] == "CronJob"
    assert cronjob["spec"]["schedule"] == "0 * * * *"
    spec = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    assert spec["restartPolicy"] == "OnFailure"


def test_ingress_is_not_generated_without_service_for_non_web_workload(
    tmp_path: Path,
) -> None:
    config_data = _base_config()
    config_data["workload"] = {
        "type": "job",
        "command": ["python"],
        "args": ["-m", "network_mapper"],
        "restartPolicy": "OnFailure",
    }
    config_data["service"] = {"enabled": False, "port": 80}
    config = AppConfig.model_validate(config_data)

    render_manifests(config, tmp_path)

    assert not (tmp_path / "60-ingress.yaml").exists()
