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


def test_network_policy_defaults_when_section_absent() -> None:
    config_data = _valid_config()
    config_data.pop("networkPolicy", None)

    config = AppConfig.model_validate(config_data)

    assert config.networkPolicy.enabled is False
    assert config.networkPolicy.profile == "ingress-only"
    assert config.networkPolicy.ingress.enabled is True
    assert config.networkPolicy.ingress.fromNamespaces == ["ingress-nginx"]
    assert config.networkPolicy.ingress.ports == []
    assert config.networkPolicy.egress.enabled is False


def test_network_policy_accepts_ingress_only_profile() -> None:
    config_data = _valid_config()
    config_data["networkPolicy"] = {
        "enabled": True,
        "profile": "ingress-only",
    }

    config = AppConfig.model_validate(config_data)

    assert config.networkPolicy.enabled is True
    assert config.networkPolicy.profile == "ingress-only"


def test_network_policy_rejects_invalid_profile() -> None:
    config_data = _valid_config()
    config_data["networkPolicy"] = {"enabled": True, "profile": "default-deny"}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_network_policy_preserves_custom_namespaces_and_ports() -> None:
    config_data = _valid_config()
    config_data["networkPolicy"] = {
        "enabled": True,
        "profile": "ingress-only",
        "ingress": {
            "enabled": True,
            "fromNamespaces": ["ingress-nginx", "edge"],
            "ports": [8000, 9000],
        },
        "egress": {"enabled": False},
    }

    config = AppConfig.model_validate(config_data)

    assert config.networkPolicy.ingress.fromNamespaces == ["ingress-nginx", "edge"]
    assert config.networkPolicy.ingress.ports == [8000, 9000]
    assert config.networkPolicy.egress.enabled is False


def test_network_policy_rejects_invalid_port() -> None:
    config_data = _valid_config()
    config_data["networkPolicy"] = {
        "enabled": True,
        "profile": "ingress-only",
        "ingress": {"ports": [0]},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_policy_defaults_when_section_absent() -> None:
    config_data = _valid_config()

    config = AppConfig.model_validate(config_data)

    assert config.policy.enabled is False
    assert config.policy.provider == "kyverno"
    assert config.policy.profile == "baseline"
    assert config.policy.validationFailureAction == "Audit"
    assert config.policy.background is True
    assert config.policy.rules.requireRecommendedLabels is True
    assert config.policy.rules.disallowLatestTag is True


def test_policy_accepts_kyverno_baseline_audit() -> None:
    config_data = _valid_config()
    config_data["policy"] = {
        "enabled": True,
        "provider": "kyverno",
        "profile": "baseline",
        "validationFailureAction": "Audit",
        "background": True,
    }

    config = AppConfig.model_validate(config_data)

    assert config.policy.enabled is True
    assert config.policy.provider == "kyverno"
    assert config.policy.profile == "baseline"
    assert config.policy.validationFailureAction == "Audit"


def test_policy_rejects_invalid_provider() -> None:
    config_data = _valid_config()
    config_data["policy"] = {"enabled": True, "provider": "gatekeeper"}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_policy_rejects_invalid_profile() -> None:
    config_data = _valid_config()
    config_data["policy"] = {"enabled": True, "profile": "restricted"}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_policy_accepts_enforce_but_not_as_default() -> None:
    config_data = _valid_config()
    config_data["policy"] = {
        "enabled": True,
        "provider": "kyverno",
        "profile": "baseline",
        "validationFailureAction": "Enforce",
    }

    config = AppConfig.model_validate(config_data)

    assert config.policy.validationFailureAction == "Enforce"


def test_policy_rejects_invalid_validation_failure_action() -> None:
    config_data = _valid_config()
    config_data["policy"] = {"enabled": True, "validationFailureAction": "Warn"}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_policy_rules_can_be_disabled() -> None:
    config_data = _valid_config()
    config_data["policy"] = {
        "enabled": True,
        "rules": {
            "requireRecommendedLabels": False,
            "disallowPrivilegedContainers": True,
            "requireRunAsNonRoot": False,
            "requireResources": True,
            "disallowLatestTag": False,
        },
    }

    config = AppConfig.model_validate(config_data)

    assert config.policy.rules.requireRecommendedLabels is False
    assert config.policy.rules.requireRunAsNonRoot is False
    assert config.policy.rules.disallowLatestTag is False


def test_supply_chain_defaults_when_section_absent() -> None:
    config = AppConfig.model_validate(_valid_config())

    assert config.supplyChain.enabled is False
    assert config.supplyChain.image == ""
    assert config.supplyChain.scan.enabled is True
    assert config.supplyChain.scan.tool == "trivy"
    assert config.supplyChain.scan.severity == ["HIGH", "CRITICAL"]
    assert config.supplyChain.sbom.tool == "syft"
    assert config.supplyChain.sbom.format == "cyclonedx-json"
    assert config.supplyChain.signing.enabled is False
    assert config.supplyChain.signing.tool == "cosign"
    assert config.supplyChain.signing.keyless is True


def test_supply_chain_accepts_empty_image_for_app_image_fallback() -> None:
    config_data = _valid_config()
    config_data["supplyChain"] = {"enabled": True, "image": ""}

    config = AppConfig.model_validate(config_data)

    assert config.supplyChain.enabled is True
    assert config.supplyChain.image == ""


def test_supply_chain_rejects_invalid_scan_tool() -> None:
    config_data = _valid_config()
    config_data["supplyChain"] = {"enabled": True, "scan": {"tool": "grype"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_supply_chain_accepts_valid_severities() -> None:
    config_data = _valid_config()
    config_data["supplyChain"] = {
        "enabled": True,
        "scan": {"severity": ["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]},
    }

    config = AppConfig.model_validate(config_data)

    assert config.supplyChain.scan.severity == [
        "UNKNOWN",
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    ]


def test_supply_chain_rejects_invalid_severity() -> None:
    config_data = _valid_config()
    config_data["supplyChain"] = {"enabled": True, "scan": {"severity": ["SEVERE"]}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_supply_chain_accepts_valid_sbom_formats() -> None:
    for format_name in ("cyclonedx-json", "spdx-json", "syft-json"):
        config_data = _valid_config()
        config_data["supplyChain"] = {"enabled": True, "sbom": {"format": format_name}}

        config = AppConfig.model_validate(config_data)

        assert config.supplyChain.sbom.format == format_name


def test_supply_chain_rejects_invalid_sbom_format() -> None:
    config_data = _valid_config()
    config_data["supplyChain"] = {"enabled": True, "sbom": {"format": "xml"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_supply_chain_rejects_invalid_signing_tool() -> None:
    config_data = _valid_config()
    config_data["supplyChain"] = {"enabled": True, "signing": {"tool": "notation"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_supply_chain_signing_keyless_is_strict_bool() -> None:
    config_data = _valid_config()
    config_data["supplyChain"] = {"enabled": True, "signing": {"keyless": "true"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ci_defaults_when_section_absent() -> None:
    config = AppConfig.model_validate(_valid_config())

    assert config.ci.enabled is False
    assert config.ci.provider == "github-actions"
    assert config.ci.python.enabled is True
    assert config.ci.python.version == "3.12"
    assert config.ci.python.quality.ruff is True
    assert config.ci.python.quality.pipAudit is True
    assert config.ci.container.enabled is True
    assert config.ci.container.image == ""
    assert config.ci.container.dockerfile == "Dockerfile"
    assert config.ci.container.context == "."
    assert config.ci.container.scan.tool == "trivy"
    assert config.ci.container.scan.severity == ["HIGH", "CRITICAL"]
    assert config.ci.container.sbom.tool == "syft"
    assert config.ci.container.sbom.format == "cyclonedx-json"
    assert config.ci.artifacts.enabled is True


def test_ci_accepts_github_actions_provider_and_python_version() -> None:
    config_data = _valid_config()
    config_data["ci"] = {
        "enabled": True,
        "provider": "github-actions",
        "python": {"version": "3.11"},
    }

    config = AppConfig.model_validate(config_data)

    assert config.ci.enabled is True
    assert config.ci.provider == "github-actions"
    assert config.ci.python.version == "3.11"


def test_ci_rejects_invalid_provider() -> None:
    config_data = _valid_config()
    config_data["ci"] = {"enabled": True, "provider": "gitlab-ci"}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ci_accepts_empty_container_image() -> None:
    config_data = _valid_config()
    config_data["ci"] = {"enabled": True, "container": {"image": ""}}

    config = AppConfig.model_validate(config_data)

    assert config.ci.container.image == ""


def test_ci_accepts_valid_scan_severities() -> None:
    config_data = _valid_config()
    config_data["ci"] = {
        "enabled": True,
        "container": {"scan": {"severity": ["UNKNOWN", "LOW", "MEDIUM"]}},
    }

    config = AppConfig.model_validate(config_data)

    assert config.ci.container.scan.severity == ["UNKNOWN", "LOW", "MEDIUM"]


def test_ci_rejects_invalid_scan_severity() -> None:
    config_data = _valid_config()
    config_data["ci"] = {
        "enabled": True,
        "container": {"scan": {"severity": ["SEVERE"]}},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ci_accepts_valid_sbom_formats() -> None:
    for format_name in ("cyclonedx-json", "spdx-json", "syft-json"):
        config_data = _valid_config()
        config_data["ci"] = {
            "enabled": True,
            "container": {"sbom": {"format": format_name}},
        }

        config = AppConfig.model_validate(config_data)

        assert config.ci.container.sbom.format == format_name


def test_ci_rejects_invalid_sbom_format() -> None:
    config_data = _valid_config()
    config_data["ci"] = {"enabled": True, "container": {"sbom": {"format": "xml"}}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ci_quality_flags_are_strict_booleans() -> None:
    config_data = _valid_config()
    config_data["ci"] = {
        "enabled": True,
        "python": {"quality": {"ruff": "true"}},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ci_artifacts_enabled_is_strict_boolean() -> None:
    config_data = _valid_config()
    config_data["ci"] = {"enabled": True, "artifacts": {"enabled": "true"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_gitops_defaults_when_section_absent() -> None:
    config = AppConfig.model_validate(_valid_config())

    assert config.gitops.enabled is False
    assert config.gitops.provider == "argocd"
    assert config.gitops.application.name == ""
    assert config.gitops.application.namespace == "argocd"
    assert config.gitops.application.project == "default"
    assert config.gitops.destination.server == "https://kubernetes.default.svc"
    assert config.gitops.destination.namespace == ""
    assert config.gitops.source.repo_url == ""
    assert config.gitops.source.target_revision == "main"
    assert config.gitops.source.path == ""
    assert config.gitops.source.type == "helm"
    assert config.gitops.sync_policy.automated is False
    assert config.gitops.sync_policy.prune is False
    assert config.gitops.sync_policy.self_heal is False


def test_gitops_accepts_argocd_helm_source() -> None:
    config_data = _valid_config()
    config_data["gitops"] = {
        "enabled": True,
        "provider": "argocd",
        "source": {
            "repoURL": "https://github.com/example/app.git",
            "targetRevision": "main",
            "path": "charts/app",
            "type": "helm",
        },
    }

    config = AppConfig.model_validate(config_data)

    assert config.gitops.enabled is True
    assert config.gitops.source.repo_url == "https://github.com/example/app.git"
    assert config.gitops.source.path == "charts/app"


def test_gitops_rejects_invalid_provider() -> None:
    config_data = _valid_config()
    config_data["gitops"] = {"enabled": False, "provider": "flux"}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_gitops_rejects_invalid_source_type() -> None:
    config_data = _valid_config()
    config_data["gitops"] = {
        "enabled": True,
        "source": {
            "repoURL": "https://github.com/example/app.git",
            "path": "manifests",
            "type": "raw",
        },
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_gitops_requires_repo_url_when_enabled() -> None:
    config_data = _valid_config()
    config_data["gitops"] = {
        "enabled": True,
        "source": {"repoURL": "", "path": "charts/app"},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_gitops_requires_source_path_when_enabled() -> None:
    config_data = _valid_config()
    config_data["gitops"] = {
        "enabled": True,
        "source": {"repoURL": "https://github.com/example/app.git", "path": ""},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_gitops_accepts_empty_fallback_fields() -> None:
    config_data = _valid_config()
    config_data["gitops"] = {
        "enabled": True,
        "application": {"name": ""},
        "destination": {"namespace": ""},
        "source": {
            "repoURL": "https://github.com/example/app.git",
            "path": "charts/app",
        },
    }

    config = AppConfig.model_validate(config_data)

    assert config.gitops.application.name == ""
    assert config.gitops.destination.namespace == ""


def test_gitops_sync_policy_flags_are_strict_booleans() -> None:
    config_data = _valid_config()
    config_data["gitops"] = {
        "enabled": True,
        "source": {
            "repoURL": "https://github.com/example/app.git",
            "path": "charts/app",
        },
        "syncPolicy": {"automated": "true", "prune": False, "selfHeal": False},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_observability_defaults_when_section_absent() -> None:
    config_data = _valid_config()

    config = AppConfig.model_validate(config_data)

    assert config.observability.enabled is False
    assert config.observability.provider == "prometheus"
    assert config.observability.metrics.enabled is True
    assert config.observability.metrics.path == "/metrics"
    assert config.observability.metrics.portName == "http"
    assert config.observability.metrics.interval == "30s"
    assert config.observability.serviceMonitor.enabled is True
    assert config.observability.serviceMonitor.namespace == ""
    assert config.observability.serviceMonitor.labels == {}
    assert config.observability.grafana.enabled is True
    assert config.observability.grafana.dashboard.enabled is True
    assert config.observability.grafana.dashboard.title == ""
    assert config.observability.alerts.enabled is False


def test_observability_accepts_prometheus_provider() -> None:
    config_data = _valid_config()
    config_data["observability"] = {
        "enabled": True,
        "provider": "prometheus",
        "metrics": {
            "enabled": True,
            "path": "/metrics",
            "portName": "http",
            "interval": "30s",
        },
    }

    config = AppConfig.model_validate(config_data)

    assert config.observability.enabled is True
    assert config.observability.provider == "prometheus"


def test_observability_rejects_invalid_provider() -> None:
    config_data = _valid_config()
    config_data["observability"] = {"enabled": True, "provider": "loki"}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_observability_metrics_path_is_configurable() -> None:
    config_data = _valid_config()
    config_data["observability"] = {
        "enabled": True,
        "metrics": {"path": "/custom", "portName": "metrics", "interval": "1m"},
    }

    config = AppConfig.model_validate(config_data)

    assert config.observability.metrics.path == "/custom"
    assert config.observability.metrics.portName == "metrics"
    assert config.observability.metrics.interval == "1m"


def test_observability_rejects_metrics_path_without_slash() -> None:
    config_data = _valid_config()
    config_data["observability"] = {"enabled": True, "metrics": {"path": "metrics"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_observability_rejects_invalid_interval() -> None:
    config_data = _valid_config()
    config_data["observability"] = {"enabled": True, "metrics": {"interval": "soon"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_observability_preserves_service_monitor_namespace_and_labels() -> None:
    config_data = _valid_config()
    config_data["observability"] = {
        "enabled": True,
        "serviceMonitor": {
            "enabled": True,
            "namespace": "monitoring",
            "labels": {"release": "kube-prometheus-stack"},
        },
    }

    config = AppConfig.model_validate(config_data)

    assert config.observability.serviceMonitor.namespace == "monitoring"
    assert config.observability.serviceMonitor.labels == {
        "release": "kube-prometheus-stack"
    }


def test_observability_preserves_grafana_dashboard_title() -> None:
    config_data = _valid_config()
    config_data["observability"] = {
        "enabled": True,
        "grafana": {
            "enabled": True,
            "dashboard": {"enabled": True, "title": "Demo Observability"},
        },
    }

    config = AppConfig.model_validate(config_data)

    assert config.observability.grafana.dashboard.title == "Demo Observability"


def test_observability_alerts_enabled_is_accepted() -> None:
    config_data = _valid_config()
    config_data["observability"] = {"enabled": True, "alerts": {"enabled": True}}

    config = AppConfig.model_validate(config_data)

    assert config.observability.alerts.enabled is True


def test_observability_booleans_are_strict() -> None:
    config_data = _valid_config()
    config_data["observability"] = {
        "enabled": True,
        "metrics": {"enabled": "yes"},
        "serviceMonitor": {"enabled": True},
        "grafana": {"enabled": True, "dashboard": {"enabled": True}},
        "alerts": {"enabled": False},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_logging_defaults_when_section_absent() -> None:
    config = AppConfig.model_validate(_valid_config())

    assert config.logging.enabled is False
    assert config.logging.provider == "loki"
    assert config.logging.application_logs.enabled is True
    assert config.logging.application_logs.source == "stdout"
    assert config.logging.loki.namespace == "monitoring"
    assert config.logging.loki.datasource_name == "Loki"
    assert config.logging.collector.enabled is True
    assert config.logging.collector.type == "promtail"
    assert config.logging.grafana.enabled is True
    assert config.logging.grafana.dashboard.enabled is True
    assert config.logging.grafana.dashboard.title == ""
    assert config.logging.queries.enabled is True


def test_logging_accepts_loki_provider() -> None:
    config_data = _valid_config()
    config_data["logging"] = {"enabled": True, "provider": "loki"}

    config = AppConfig.model_validate(config_data)

    assert config.logging.enabled is True
    assert config.logging.provider == "loki"


def test_logging_rejects_invalid_provider() -> None:
    config_data = _valid_config()
    config_data["logging"] = {"enabled": True, "provider": "elasticsearch"}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_logging_accepts_stdout_source() -> None:
    config_data = _valid_config()
    config_data["logging"] = {
        "enabled": True,
        "applicationLogs": {"enabled": True, "source": "stdout"},
    }

    config = AppConfig.model_validate(config_data)

    assert config.logging.application_logs.source == "stdout"


def test_logging_rejects_invalid_source() -> None:
    config_data = _valid_config()
    config_data["logging"] = {"enabled": True, "applicationLogs": {"source": "file"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_logging_accepts_promtail_collector() -> None:
    config_data = _valid_config()
    config_data["logging"] = {"enabled": True, "collector": {"type": "promtail"}}

    config = AppConfig.model_validate(config_data)

    assert config.logging.collector.type == "promtail"


def test_logging_rejects_invalid_collector_type() -> None:
    config_data = _valid_config()
    config_data["logging"] = {"enabled": True, "collector": {"type": "alloy"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_logging_preserves_dashboard_title() -> None:
    config_data = _valid_config()
    config_data["logging"] = {
        "enabled": True,
        "grafana": {"dashboard": {"title": "Demo Logs"}},
    }

    config = AppConfig.model_validate(config_data)

    assert config.logging.grafana.dashboard.title == "Demo Logs"


def test_logging_booleans_are_strict() -> None:
    config_data = _valid_config()
    config_data["logging"] = {
        "enabled": "yes",
        "applicationLogs": {"enabled": "yes"},
        "collector": {"enabled": "yes"},
        "grafana": {"enabled": "yes", "dashboard": {"enabled": "yes"}},
        "queries": {"enabled": "yes"},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_tracing_defaults_when_section_absent() -> None:
    config = AppConfig.model_validate(_valid_config())

    assert config.tracing.enabled is False
    assert config.tracing.provider == "opentelemetry"
    assert config.tracing.backend.type == "tempo"
    assert config.tracing.backend.namespace == "monitoring"
    assert config.tracing.backend.datasource_name == "Tempo"
    assert config.tracing.collector.enabled is True
    assert config.tracing.collector.type == "opentelemetry-collector"
    assert config.tracing.collector.endpoint.endswith(":4318")
    assert config.tracing.collector.protocol == "otlp-http"
    assert config.tracing.instrumentation.enabled is True
    assert config.tracing.instrumentation.mode == "env"
    assert config.tracing.instrumentation.service_name == ""
    assert config.tracing.grafana.enabled is True
    assert config.tracing.grafana.dashboard.enabled is True
    assert config.tracing.grafana.dashboard.title == ""
    assert config.tracing.examples.enabled is True


def test_tracing_accepts_opentelemetry_provider() -> None:
    config_data = _valid_config()
    config_data["tracing"] = {"enabled": True, "provider": "opentelemetry"}

    config = AppConfig.model_validate(config_data)

    assert config.tracing.enabled is True
    assert config.tracing.provider == "opentelemetry"


def test_tracing_rejects_invalid_provider() -> None:
    config_data = _valid_config()
    config_data["tracing"] = {"enabled": True, "provider": "jaeger"}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_tracing_accepts_tempo_backend() -> None:
    config_data = _valid_config()
    config_data["tracing"] = {
        "enabled": True,
        "backend": {
            "type": "tempo",
            "namespace": "monitoring",
            "datasourceName": "Tempo",
        },
    }

    config = AppConfig.model_validate(config_data)

    assert config.tracing.backend.type == "tempo"
    assert config.tracing.backend.namespace == "monitoring"


def test_tracing_rejects_invalid_backend() -> None:
    config_data = _valid_config()
    config_data["tracing"] = {"enabled": True, "backend": {"type": "jaeger"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_tracing_accepts_opentelemetry_collector_and_protocols() -> None:
    for protocol in ("otlp-http", "otlp-grpc"):
        config_data = _valid_config()
        config_data["tracing"] = {
            "enabled": True,
            "collector": {
                "enabled": True,
                "type": "opentelemetry-collector",
                "endpoint": "http://otel-collector.monitoring.svc.cluster.local:4318",
                "protocol": protocol,
            },
        }

        config = AppConfig.model_validate(config_data)

        assert config.tracing.collector.type == "opentelemetry-collector"
        assert config.tracing.collector.protocol == protocol


def test_tracing_rejects_invalid_collector_type() -> None:
    config_data = _valid_config()
    config_data["tracing"] = {"enabled": True, "collector": {"type": "jaeger-agent"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_tracing_rejects_invalid_protocol() -> None:
    config_data = _valid_config()
    config_data["tracing"] = {"enabled": True, "collector": {"protocol": "zipkin"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_tracing_accepts_env_instrumentation_and_service_name() -> None:
    config_data = _valid_config()
    config_data["tracing"] = {
        "enabled": True,
        "instrumentation": {
            "enabled": True,
            "mode": "env",
            "serviceName": "demo-service",
        },
    }

    config = AppConfig.model_validate(config_data)

    assert config.tracing.instrumentation.mode == "env"
    assert config.tracing.instrumentation.service_name == "demo-service"


def test_tracing_rejects_invalid_instrumentation_mode() -> None:
    config_data = _valid_config()
    config_data["tracing"] = {
        "enabled": True,
        "instrumentation": {"mode": "auto"},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_tracing_preserves_dashboard_title() -> None:
    config_data = _valid_config()
    config_data["tracing"] = {
        "enabled": True,
        "grafana": {"dashboard": {"title": "Demo Traces"}},
    }

    config = AppConfig.model_validate(config_data)

    assert config.tracing.grafana.dashboard.title == "Demo Traces"


def test_tracing_booleans_are_strict() -> None:
    config_data = _valid_config()
    config_data["tracing"] = {
        "enabled": "yes",
        "collector": {"enabled": "yes"},
        "instrumentation": {"enabled": "yes"},
        "grafana": {"enabled": "yes", "dashboard": {"enabled": "yes"}},
        "examples": {"enabled": "yes"},
    }

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_terraform_defaults_when_section_absent() -> None:
    config_data = _valid_config()

    config = AppConfig.model_validate(config_data)

    assert config.terraform.enabled is False
    assert config.terraform.project_name == ""
    assert config.terraform.backend.type == "local"
    assert config.terraform.providers.kubernetes.enabled is True
    assert config.terraform.providers.helm.enabled is True
    assert config.terraform.providers.cloud.enabled is False
    assert config.terraform.modules.enabled is True
    assert config.terraform.examples.enabled is True


def test_terraform_enabled_config_is_valid() -> None:
    config_data = _valid_config()
    config_data["terraform"] = {
        "enabled": True,
        "projectName": "weather-platform",
        "backend": {"type": "local"},
        "providers": {
            "kubernetes": {"enabled": True},
            "helm": {"enabled": True},
            "cloud": {"enabled": False},
        },
        "modules": {"enabled": True},
        "examples": {"enabled": True},
    }

    config = AppConfig.model_validate(config_data)

    assert config.terraform.enabled is True
    assert config.terraform.project_name == "weather-platform"
    assert config.terraform.backend.type == "local"


def test_terraform_rejects_invalid_backend() -> None:
    config_data = _valid_config()
    config_data["terraform"] = {"backend": {"type": "remote"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_terraform_project_name_can_be_empty_for_fallback() -> None:
    config_data = _valid_config()
    config_data["terraform"] = {"enabled": True, "projectName": ""}

    config = AppConfig.model_validate(config_data)

    assert config.terraform.project_name == ""


def test_terraform_rejects_non_strict_provider_booleans() -> None:
    config_data = _valid_config()
    config_data["terraform"] = {"providers": {"kubernetes": {"enabled": "yes"}}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_terraform_rejects_non_strict_modules_boolean() -> None:
    config_data = _valid_config()
    config_data["terraform"] = {"modules": {"enabled": "yes"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_terraform_rejects_non_strict_examples_boolean() -> None:
    config_data = _valid_config()
    config_data["terraform"] = {"examples": {"enabled": "yes"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ansible_defaults_when_section_absent() -> None:
    config_data = _valid_config()

    config = AppConfig.model_validate(config_data)

    assert config.ansible.enabled is False
    assert config.ansible.project_name == ""
    assert config.ansible.inventory.type == "local"
    assert config.ansible.inventory.hosts == ["localhost"]
    assert config.ansible.playbook.name == "site.yml"
    assert config.ansible.roles.enabled is True
    assert config.ansible.collections.kubernetes.enabled is True
    assert config.ansible.collections.community.enabled is False
    assert config.ansible.examples.enabled is True


def test_ansible_enabled_config_is_valid() -> None:
    config_data = _valid_config()
    config_data["ansible"] = {
        "enabled": True,
        "projectName": "weather-automation",
        "inventory": {"type": "local", "hosts": ["localhost"]},
        "playbook": {"name": "site.yaml"},
        "roles": {"enabled": True},
        "collections": {
            "kubernetes": {"enabled": True},
            "community": {"enabled": False},
        },
        "examples": {"enabled": True},
    }

    config = AppConfig.model_validate(config_data)

    assert config.ansible.enabled is True
    assert config.ansible.project_name == "weather-automation"
    assert config.ansible.playbook.name == "site.yaml"


def test_ansible_rejects_invalid_inventory_type() -> None:
    config_data = _valid_config()
    config_data["ansible"] = {"inventory": {"type": "production"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ansible_rejects_empty_hosts() -> None:
    config_data = _valid_config()
    config_data["ansible"] = {"inventory": {"hosts": []}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ansible_rejects_empty_host_entry() -> None:
    config_data = _valid_config()
    config_data["ansible"] = {"inventory": {"hosts": [""]}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ansible_rejects_empty_playbook_name() -> None:
    config_data = _valid_config()
    config_data["ansible"] = {"playbook": {"name": ""}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ansible_rejects_playbook_name_without_yaml_suffix() -> None:
    config_data = _valid_config()
    config_data["ansible"] = {"playbook": {"name": "site.txt"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ansible_rejects_non_strict_booleans() -> None:
    config_data = _valid_config()
    config_data["ansible"] = {"roles": {"enabled": "yes"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_ansible_project_name_can_be_empty_for_fallback() -> None:
    config_data = _valid_config()
    config_data["ansible"] = {"enabled": True, "projectName": ""}

    config = AppConfig.model_validate(config_data)

    assert config.ansible.project_name == ""


def test_security_defaults_when_section_absent() -> None:
    config = AppConfig.model_validate(_valid_config())

    assert config.security.enabled is False
    assert config.security.project_name == ""
    assert config.security.container.enabled is True
    assert config.security.manifests.enabled is True
    assert config.security.rbac.enabled is True
    assert config.security.pod_security.enabled is True
    assert config.security.network.enabled is True
    assert config.security.secrets.enabled is True
    assert config.security.supply_chain.enabled is True
    assert config.security.checklist.enabled is True
    assert config.security.examples.enabled is True


def test_security_enabled_config_is_valid() -> None:
    config_data = _valid_config()
    config_data["security"] = {
        "enabled": True,
        "projectName": "weather-security",
        "container": {"enabled": True},
        "manifests": {"enabled": True},
        "rbac": {"enabled": True},
        "podSecurity": {"enabled": True},
        "network": {"enabled": True},
        "secrets": {"enabled": True},
        "supplyChain": {"enabled": True},
        "checklist": {"enabled": True},
        "examples": {"enabled": True},
    }

    config = AppConfig.model_validate(config_data)

    assert config.security.enabled is True
    assert config.security.project_name == "weather-security"
    assert config.security.pod_security.enabled is True
    assert config.security.supply_chain.enabled is True


def test_security_project_name_can_be_empty_for_fallback() -> None:
    config_data = _valid_config()
    config_data["security"] = {"enabled": True, "projectName": ""}

    config = AppConfig.model_validate(config_data)

    assert config.security.project_name == ""


@pytest.mark.parametrize(
    ("section", "payload"),
    [
        ("container", {"enabled": "yes"}),
        ("manifests", {"enabled": "yes"}),
        ("rbac", {"enabled": "yes"}),
        ("podSecurity", {"enabled": "yes"}),
        ("network", {"enabled": "yes"}),
        ("secrets", {"enabled": "yes"}),
        ("supplyChain", {"enabled": "yes"}),
        ("checklist", {"enabled": "yes"}),
        ("examples", {"enabled": "yes"}),
    ],
)
def test_security_rejects_non_strict_booleans(
    section: str, payload: dict[str, object]
) -> None:
    config_data = _valid_config()
    config_data["security"] = {section: payload}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_capstone_defaults_when_section_absent() -> None:
    config = AppConfig.model_validate(_valid_config())

    assert config.capstone.enabled is False
    assert config.capstone.project_name == ""
    assert config.capstone.report.title == ""
    assert config.capstone.report.audience == "technical"
    assert config.capstone.checklist.enabled is True
    assert config.capstone.architecture.enabled is True
    assert config.capstone.devsecops_matrix.enabled is True
    assert config.capstone.modules_summary.enabled is True
    assert config.capstone.manual_steps.enabled is True
    assert config.capstone.runtime_dependencies.enabled is True
    assert config.capstone.security_summary.enabled is True
    assert config.capstone.v1_readiness.enabled is True
    assert config.capstone.examples.enabled is True


def test_capstone_enabled_config_is_valid() -> None:
    config_data = _valid_config()
    config_data["capstone"] = {
        "enabled": True,
        "projectName": "weather-capstone",
        "report": {"title": "Weather Lab", "audience": "technical"},
        "checklist": {"enabled": True},
        "architecture": {"enabled": True},
        "devsecopsMatrix": {"enabled": True},
        "modulesSummary": {"enabled": True},
        "manualSteps": {"enabled": True},
        "runtimeDependencies": {"enabled": True},
        "securitySummary": {"enabled": True},
        "v1Readiness": {"enabled": True},
        "examples": {"enabled": True},
    }

    config = AppConfig.model_validate(config_data)

    assert config.capstone.enabled is True
    assert config.capstone.project_name == "weather-capstone"
    assert config.capstone.report.title == "Weather Lab"
    assert config.capstone.report.audience == "technical"


@pytest.mark.parametrize("audience", ["technical", "training", "internship"])
def test_capstone_accepts_supported_audiences(audience: str) -> None:
    config_data = _valid_config()
    config_data["capstone"] = {"report": {"audience": audience}}

    config = AppConfig.model_validate(config_data)

    assert config.capstone.report.audience == audience


def test_capstone_rejects_invalid_audience() -> None:
    config_data = _valid_config()
    config_data["capstone"] = {"report": {"audience": "executive"}}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_capstone_project_name_and_title_can_be_empty_for_fallback() -> None:
    config_data = _valid_config()
    config_data["capstone"] = {
        "enabled": True,
        "projectName": "",
        "report": {"title": ""},
    }

    config = AppConfig.model_validate(config_data)

    assert config.capstone.project_name == ""
    assert config.capstone.report.title == ""


@pytest.mark.parametrize(
    ("section", "payload"),
    [
        ("checklist", {"enabled": "yes"}),
        ("architecture", {"enabled": "yes"}),
        ("devsecopsMatrix", {"enabled": "yes"}),
        ("modulesSummary", {"enabled": "yes"}),
        ("manualSteps", {"enabled": "yes"}),
        ("runtimeDependencies", {"enabled": "yes"}),
        ("securitySummary", {"enabled": "yes"}),
        ("v1Readiness", {"enabled": "yes"}),
        ("examples", {"enabled": "yes"}),
    ],
)
def test_capstone_rejects_non_strict_booleans(
    section: str, payload: dict[str, object]
) -> None:
    config_data = _valid_config()
    config_data["capstone"] = {section: payload}

    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)
