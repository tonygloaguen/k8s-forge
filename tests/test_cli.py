import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from k8s_forge.cli import app
from k8s_forge.config_loader import load_app_config
from k8s_forge.kubectl import KubectlResult

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
METRICS_SERVER_COMMAND = [
    "kubectl",
    "-n",
    "kube-system",
    "get",
    "deploy",
    "metrics-server",
]
INGRESS_NGINX_COMMAND = [
    "kubectl",
    "-n",
    "ingress-nginx",
    "get",
    "deploy",
    "ingress-nginx-controller",
]
CERT_MANAGER_COMMAND = [
    "kubectl",
    "-n",
    "cert-manager",
    "get",
    "deploy",
    "cert-manager",
]

LINKERD_CLI_COMMAND = ["linkerd", "version", "--client"]
LINKERD_NAMESPACE_COMMAND = ["kubectl", "get", "ns", "linkerd"]
LINKERD_CONTROL_PLANE_COMMAND = ["kubectl", "-n", "linkerd", "get", "deploy"]
LINKERD_VIZ_COMMAND = ["kubectl", "get", "ns", "linkerd-viz"]
CNI_PODS_COMMAND = ["kubectl", "-n", "kube-system", "get", "pods"]
NETWORK_POLICY_COMMAND = ["kubectl", "get", "networkpolicy", "--all-namespaces"]
KYVERNO_NAMESPACE_COMMAND = ["kubectl", "get", "ns", "kyverno"]
KYVERNO_DEPLOY_COMMAND = ["kubectl", "-n", "kyverno", "get", "deploy"]
KYVERNO_CRD_COMMAND = ["kubectl", "get", "crd"]
POLICY_REPORT_COMMAND = ["kubectl", "get", "policyreport", "--all-namespaces"]
TRIVY_COMMAND = ["trivy", "--version"]
SYFT_COMMAND = ["syft", "version"]
COSIGN_COMMAND = ["cosign", "version"]
GIT_COMMAND = ["git", "--version"]
TERRAFORM_COMMAND = ["terraform", "version"]
ANSIBLE_COMMAND = ["ansible", "--version"]
ANSIBLE_LINT_COMMAND = ["ansible-lint", "--version"]
ARGOCD_CLI_COMMAND = ["argocd", "version", "--client"]
ARGOCD_NAMESPACE_COMMAND = ["kubectl", "get", "ns", "argocd"]
ARGOCD_DEPLOY_COMMAND = ["kubectl", "-n", "argocd", "get", "deploy"]
ARGOCD_APPLICATION_CRD_COMMAND = ["kubectl", "get", "crd", "applications.argoproj.io"]
SERVICEMONITOR_CRD_COMMAND = [
    "kubectl",
    "get",
    "crd",
    "servicemonitors.monitoring.coreos.com",
]
PROMETHEUSRULE_CRD_COMMAND = [
    "kubectl",
    "get",
    "crd",
    "prometheusrules.monitoring.coreos.com",
]
MONITORING_NAMESPACE_COMMAND = ["kubectl", "get", "ns", "monitoring"]
MONITORING_DEPLOY_COMMAND = ["kubectl", "-n", "monitoring", "get", "deploy"]
MONITORING_SERVICE_COMMAND = ["kubectl", "-n", "monitoring", "get", "svc"]
CLUSTER_PODS_COMMAND = ["kubectl", "get", "pods", "--all-namespaces"]


def test_cli_help_responds() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "k8s-forge" in result.output


def test_cli_commands_exist() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in (
        "init",
        "check",
        "render",
        "dry-run",
        "diff",
        "apply",
        "status",
        "discover",
        "explain",
        "studio",
        "helm",
        "ci",
        "gitops",
        "observability",
        "logging",
        "tracing",
        "terraform",
        "ansible",
        "security",
        "capstone",
    ):
        assert command in result.output


def test_cli_init_creates_default_app_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "demo-app"])

    assert result.exit_code == 0
    config_path = Path("app.yaml")
    assert config_path.exists()
    config = load_app_config(config_path)
    assert config.app.name == "demo-app"
    assert config.app.namespace == "demo-app"
    assert config.app.image == "demo-app:latest"
    assert config.app.containerPort == 8000
    assert config.app.replicas == 1
    assert config.service.port == 80
    assert config.ingress.host is None
    text = config_path.read_text(encoding="utf-8")
    assert 'API_TOKEN: "change-me"' in text
    assert "host: null" in text


def test_cli_init_options_override_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "init",
            "admin-api",
            "--namespace",
            "admin",
            "--image",
            "ghcr.io/example/admin-api:1.0.0",
            "--port",
            "8080",
            "--replicas",
            "1",
            "--service-port",
            "8081",
            "--output",
            "custom.yaml",
        ],
    )

    assert result.exit_code == 0
    config = load_app_config(Path("custom.yaml"))
    assert config.app.name == "admin-api"
    assert config.app.namespace == "admin"
    assert config.app.image == "ghcr.io/example/admin-api:1.0.0"
    assert config.app.containerPort == 8080
    assert config.app.replicas == 1
    assert config.service.port == 8081


def test_cli_init_hpa_options_generate_autoscaling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "init",
            "weatherapi",
            "--image",
            "weatherapi:0.1.0",
            "--namespace",
            "weather",
            "--port",
            "8000",
            "--replicas",
            "2",
            "--hpa",
            "--hpa-min",
            "2",
            "--hpa-max",
            "6",
            "--hpa-cpu",
            "70",
            "--output",
            "k8s-forge-app.yaml",
        ],
    )

    assert result.exit_code == 0
    config = load_app_config(Path("k8s-forge-app.yaml"))
    assert config.autoscaling.enabled is True
    assert config.autoscaling.minReplicas == 2
    assert config.autoscaling.maxReplicas == 6
    assert config.autoscaling.targetCPUUtilizationPercentage == 70
    text = Path("k8s-forge-app.yaml").read_text(encoding="utf-8")
    assert "autoscaling:" in text
    assert "enabled: true" in text


def test_cli_init_hpa_warns_when_replicas_below_min(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["init", "demo-app", "--hpa", "--replicas", "1", "--hpa-min", "2"],
    )

    assert result.exit_code == 0
    assert "Deployment replicas is lower than HPA minReplicas" in result.output


def test_cli_init_custom_output_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "sample-web", "--output", "custom.yaml"])

    assert result.exit_code == 0
    assert Path("custom.yaml").exists()
    assert not Path("app.yaml").exists()


def test_cli_init_existing_file_fails_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("app.yaml")
    config_path.write_text("existing content", encoding="utf-8")

    result = runner.invoke(app, ["init", "demo-app"])

    assert result.exit_code == 1
    assert "file already exists, use --force to overwrite" in result.output
    assert config_path.read_text(encoding="utf-8") == "existing content"


def test_cli_init_force_overwrites_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("app.yaml")
    config_path.write_text("existing content", encoding="utf-8")

    result = runner.invoke(app, ["init", "demo-app", "--force"])

    assert result.exit_code == 0
    assert "existing content" not in config_path.read_text(encoding="utf-8")
    assert load_app_config(config_path).app.name == "demo-app"


def test_cli_init_does_not_call_kubectl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        raise AssertionError("init must not call kubectl")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fail_run_kubectl)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "generic-api"])

    assert result.exit_code == 0
    assert load_app_config(Path("app.yaml")).app.name == "generic-api"


def test_cli_check_success() -> None:
    result = runner.invoke(app, ["check", str(ROOT / "examples" / "demo-app.yaml")])

    assert result.exit_code == 0
    assert "Validating application configuration" in result.output
    assert "structurally valid" in result.output
    assert "Kubernetes manifests" in result.output
    assert "configuration is valid" in result.output
    assert "demo-app" in result.output
    assert "demo" in result.output
    assert "ghcr.io/example/demo-app:1.0.0" in result.output
    assert "8000" in result.output
    assert "enabled on port 80" in result.output


def test_cli_check_error(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
app:
  name: broken-app
  namespace: broken
  containerPort: 8000
  replicas: 1
service:
  enabled: true
  port: 80
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 1
    assert "Configuration validation failed" in result.output
    assert "app.image" in result.output


def test_cli_render_success(tmp_path: Path) -> None:
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "render",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Rendering Kubernetes manifests from app.yaml" in result.output
    assert "does not contact the cluster" in result.output
    assert "manifests generated" in result.output
    assert "00-namespace.yaml" in result.output
    assert "40-service.yaml" in result.output
    assert "Generated manifests are ready for review" in result.output
    assert (output_dir / "30-deployment.yaml").exists()


def test_cli_render_lists_hpa_when_autoscaling_enabled(tmp_path: Path) -> None:
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "render",
            str(ROOT / "examples" / "admin-api.yaml"),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert "50-hpa.yaml" in result.output
    assert (
        "Autoscaling is enabled, so an HPA manifest will be generated" in result.output
    )
    assert "metrics-server" in result.output
    assert (output_dir / "50-hpa.yaml").exists()


def test_cli_helm_render_generates_chart(tmp_path: Path) -> None:
    output_dir = tmp_path / "charts"

    result = runner.invoke(
        app,
        [
            "helm",
            "render",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
    )

    chart_dir = output_dir / "demo-app"
    assert result.exit_code == 0
    assert "Rendering a Helm chart from app.yaml" in result.output
    assert "does not contact the cluster and does not install anything" in result.output
    assert "Helm chart generated" in result.output
    assert "helm lint" in result.output
    assert "helm template" in result.output
    assert "ownership metadata" in result.output
    assert (chart_dir / "Chart.yaml").exists()
    assert (chart_dir / "values.yaml").exists()
    assert (chart_dir / "templates" / "deployment.yaml").exists()


def test_cli_helm_render_uses_custom_chart_name(tmp_path: Path) -> None:
    output_dir = tmp_path / "charts"

    result = runner.invoke(
        app,
        [
            "helm",
            "render",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
            "--chart-name",
            "sample-chart",
        ],
    )

    assert result.exit_code == 0
    assert (output_dir / "sample-chart" / "Chart.yaml").exists()
    assert "helm lint" in result.output
    assert "sample-chart" in result.output


def _write_ingress_config(path: Path) -> None:
    path.write_text(
        """
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
config:
  APP_ENV: "dev"
secrets:
  API_TOKEN: "change-me"
service:
  enabled: true
  port: 80
resources:
  requests:
    cpu: "50m"
    memory: "64Mi"
  limits:
    cpu: "250m"
    memory: "128Mi"
probes:
  liveness: "/healthz"
  readiness: "/readyz"
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 6
  targetCPUUtilizationPercentage: 70
ingress:
  enabled: true
  host: weather.local
  className: nginx
  path: /
  pathType: Prefix
  tls:
    enabled: true
    secretName: weather-tls
  certManager:
    enabled: true
    clusterIssuer: selfsigned-dev
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "1m"
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_ingress_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_ingress_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "Ingress is enabled" in result.output
    assert "weather.local" in result.output
    assert "ingress-nginx" in result.output
    assert "TLS is enabled for this Ingress" in result.output
    assert "ClusterIssuer exists" in result.output


def test_cli_render_lists_ingress_and_prints_local_hints(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_ingress_config(config_path)

    result = runner.invoke(
        app, ["render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "60-ingress.yaml" in result.output
    assert (
        "Ingress is enabled, so an Ingress manifest will be generated" in result.output
    )
    assert "127.0.0.1 weather.local" in result.output
    assert "ports 80 and 443" in result.output
    assert (output_dir / "60-ingress.yaml").exists()


def test_cli_helm_render_lists_ingress_template(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "charts"
    _write_ingress_config(config_path)

    result = runner.invoke(
        app, ["helm", "render", str(config_path), "--output", str(output_dir)]
    )

    chart_dir = output_dir / "weatherapi"
    assert result.exit_code == 0
    assert "templates/ingress.yaml" in result.output
    assert "optional Ingress template" in result.output
    assert "Helm will not install ingress-nginx or cert-manager" in result.output
    assert "127.0.0.1 weather.local" in result.output
    assert (chart_dir / "templates" / "ingress.yaml").exists()


def test_cli_render_validation_error_does_not_generate(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    config_path.write_text(
        """
app:
  name: broken-app
  namespace: broken
  image: ghcr.io/example/broken-app:1.0.0
  containerPort: 70000
  replicas: 1
service:
  enabled: true
  port: 80
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 1
    assert "Configuration validation failed" in result.output
    assert not output_dir.exists()


def test_cli_dry_run_calls_kubectl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], int]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append((args, timeout))
        return KubectlResult(["kubectl", *args], 0, "dry run ok", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "dry-run",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
            "--timeout",
            "7",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        (["get", "namespace", "demo"], 7),
        (["apply", "--dry-run=server", "-f", str(output_dir)], 7),
    ]
    assert "Running Kubernetes server-side dry-run" in result.output
    assert "Kubernetes API for validation" in result.output
    assert "No changes are persisted" in result.output
    assert "Checking target namespace before dry-run" in result.output
    assert "dry run ok" in result.output
    assert "does not exist" not in result.output


def test_cli_dry_run_warns_when_namespace_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append(args)
        if args == ["get", "namespace", "demo"]:
            return KubectlResult(
                ["kubectl", *args],
                1,
                "",
                'Error from server (NotFound): namespaces "demo" not found',
            )
        return KubectlResult(["kubectl", *args], 0, "dry run ok", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "dry-run",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        ["get", "namespace", "demo"],
        ["apply", "--dry-run=server", "-f", str(output_dir)],
    ]
    assert "Namespace 'demo' does not exist" in result.output
    assert "Server-side dry-run simulates the Namespace manifest" in result.output
    assert "kubectl create namespace demo" in result.output
    assert "dry run ok" in result.output


def test_cli_dry_run_explains_namespace_not_found_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        if args == ["get", "namespace", "demo"]:
            return KubectlResult(
                ["kubectl", *args],
                1,
                "",
                'Error from server (NotFound): namespaces "demo" not found',
            )
        return KubectlResult(
            ["kubectl", *args],
            1,
            "namespace/demo created (server dry run)",
            'Error from server (NotFound): namespaces "demo" not found',
        )

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "dry-run",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 1
    assert "namespace/demo created (server dry run)" in result.output
    assert 'namespaces "demo" not found' in result.output
    assert "only simulated during server-side dry-run" in result.output
    assert (
        "ConfigMap, Secret, Deployment, and Service cannot be validated"
        in result.output
    )
    assert "kubectl create namespace demo" in result.output
    assert "Then rerun: k8s-forge dry-run" in result.output
    assert str(ROOT / "examples" / "demo-app.yaml") in result.output
    assert str(output_dir) in result.output


def test_cli_dry_run_explains_hpa_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        return KubectlResult(["kubectl", *args], 0, "dry run ok", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "dry-run",
            str(ROOT / "examples" / "admin-api.yaml"),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Validating HPA manifest against the Kubernetes API" in result.output
    assert "CPU targets may appear as <unknown>" in result.output


def test_cli_diff_calls_kubectl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append(args)
        return KubectlResult(["kubectl", *args], 1, "diff output", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        ["diff", str(ROOT / "examples" / "demo-app.yaml"), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert calls == [["diff", "-f", str(output_dir)]]
    assert "diff output" in result.output
    assert "found changes" in result.output


def test_cli_apply_refusal_does_not_call_kubectl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append(args)
        return KubectlResult(["kubectl", *args], 0, "applied", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "apply",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
        input="n\n",
    )

    assert result.exit_code == 0
    assert calls == []
    assert "apply cancelled" in result.output


def test_cli_apply_confirmation_calls_kubectl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append(args)
        return KubectlResult(["kubectl", *args], 0, "applied", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "apply",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
        input="y\n",
    )

    assert result.exit_code == 0
    assert calls == [["apply", "-f", str(output_dir)]]
    assert "Applying manifests to the current Kubernetes context" in result.output
    assert "Current context will be modified" in result.output
    assert "Apply completed" in result.output
    assert "Next steps: check rollout status" in result.output
    assert "applied" in result.output


def test_cli_apply_yes_calls_kubectl_without_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append(args)
        return KubectlResult(["kubectl", *args], 0, "applied", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "apply",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert calls == [["apply", "-f", str(output_dir)]]
    assert "Continue with kubectl apply?" not in result.output


def test_cli_status_calls_kubectl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], int]] = []

    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        calls.append((args, timeout))
        return KubectlResult(["kubectl", *args], 0, "status output", "")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)

    result = runner.invoke(app, ["status", "demo-app", "-n", "demo", "--timeout", "9"])

    assert result.exit_code == 0
    assert calls == [
        (["-n", "demo", "get", "deploy,po,svc", "-l", "app=demo-app"], 9),
        (["-n", "demo", "get", "hpa", "-l", "app=demo-app"], 9),
    ]
    assert "Reading Kubernetes status for application demo-app" in result.output
    assert "Deployment status shows" in result.output
    assert "Pods are the actual running instances" in result.output
    assert "stable network entry point" in result.output
    assert "The HPA controls scaling" in result.output
    assert "status output" in result.output


def test_cli_status_reports_no_hpa_without_hiding_workloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        if args == ["-n", "demo", "get", "deploy,po,svc", "-l", "app=demo-app"]:
            return KubectlResult(["kubectl", *args], 0, "deploy/demo-app ready", "")
        return KubectlResult(
            ["kubectl", *args],
            0,
            "No resources found in demo namespace.",
            "",
        )

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)

    result = runner.invoke(app, ["status", "demo-app", "-n", "demo"])

    assert result.exit_code == 0
    assert "deploy/demo-app ready" in result.output
    assert "No HPA found for app demo-app" in result.output
    assert "autoscaling.enabled is false" in result.output


def test_cli_status_prints_hpa_unknown_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        if args == ["-n", "demo", "get", "deploy,po,svc", "-l", "app=demo-app"]:
            return KubectlResult(["kubectl", *args], 0, "pod/demo-app Running", "")
        return KubectlResult(
            ["kubectl", *args],
            0,
            "NAME REFERENCE TARGETS MINPODS MAXPODS REPLICAS AGE\n"
            "demo-app Deployment/demo-app <unknown>/70% 2 6 2 1m",
            "",
        )

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)

    result = runner.invoke(app, ["status", "demo-app", "-n", "demo"])

    assert result.exit_code == 0
    assert "<unknown>/70%" in result.output
    assert "No HPA found" not in result.output


def test_cli_status_hpa_error_is_not_silently_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_kubectl(args: list[str], timeout: int = 30) -> KubectlResult:
        if args == ["-n", "demo", "get", "deploy,po,svc", "-l", "app=demo-app"]:
            return KubectlResult(["kubectl", *args], 0, "pod/demo-app Running", "")
        return KubectlResult(["kubectl", *args], 2, "", "hpa forbidden")

    monkeypatch.setattr("k8s_forge.cli.run_kubectl", fake_run_kubectl)

    result = runner.invoke(app, ["status", "demo-app", "-n", "demo"])

    assert result.exit_code == 2
    assert "pod/demo-app Running" in result.output
    assert "hpa forbidden" in result.output


def test_cli_dry_run_missing_kubectl_reports_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "dry-run",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 1
    assert "kubectl executable was not found" in result.output
    assert "Install kubectl" in result.output
    assert "PATH" in result.output


def test_cli_status_timeout_reports_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, timeout=5, stderr="cluster too slow")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["status", "demo-app", "-n", "demo", "--timeout", "5"])

    assert result.exit_code == 1
    assert "kubectl timed out after 5 seconds" in result.output
    assert "cluster too slow" in result.output


def test_cli_dry_run_nonzero_return_shows_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 3, "", "server rejected manifest")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "dry-run",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 3
    assert "server rejected manifest" in result.output


def test_cli_apply_nonzero_return_shows_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 4, "", "forbidden by RBAC")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        [
            "apply",
            str(ROOT / "examples" / "demo-app.yaml"),
            "--output",
            str(output_dir),
            "--yes",
        ],
    )

    assert result.exit_code == 4
    assert "forbidden by RBAC" in result.output


def test_cli_status_nonzero_return_shows_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "namespace demo not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["status", "demo-app", "-n", "demo"])

    assert result.exit_code == 1
    assert "namespace demo not found" in result.output


def test_cli_diff_zero_return_is_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "no differences", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        ["diff", str(ROOT / "examples" / "demo-app.yaml"), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "no differences" in result.output
    assert "found changes" not in result.output


def test_cli_diff_return_one_is_not_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "diff content", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        ["diff", str(ROOT / "examples" / "demo-app.yaml"), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "diff content" in result.output
    assert "found changes" in result.output


def test_cli_diff_return_above_one_is_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, "", "diff failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output_dir = tmp_path / "generated"

    result = runner.invoke(
        app,
        ["diff", str(ROOT / "examples" / "demo-app.yaml"), "--output", str(output_dir)],
    )

    assert result.exit_code == 2
    assert "diff failed" in result.output


def test_cli_doctor_all_tools_present(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        outputs = {
            ("docker", "version"): "Docker version",
            ("kind", "version"): "kind v0.23.0",
            ("kubectl", "version", "--client"): "Client Version",
            ("kubectl", "config", "current-context"): "kind-devsecops",
            ("kubectl", "get", "nodes"): "node Ready",
            (
                "kubectl",
                "-n",
                "kube-system",
                "get",
                "deploy",
                "metrics-server",
            ): "metrics-server available",
            (
                "kubectl",
                "-n",
                "ingress-nginx",
                "get",
                "deploy",
                "ingress-nginx-controller",
            ): "ingress-nginx-controller available",
            (
                "kubectl",
                "-n",
                "cert-manager",
                "get",
                "deploy",
                "cert-manager",
            ): "cert-manager available",
            ("linkerd", "version", "--client"): "Client version: stable",
            ("kubectl", "get", "ns", "linkerd"): "linkerd",
            ("kubectl", "-n", "linkerd", "get", "deploy"): "linkerd-control-plane",
            ("kubectl", "get", "ns", "linkerd-viz"): "linkerd-viz",
            ("kubectl", "-n", "kube-system", "get", "pods"): "calico-node",
            ("kubectl", "get", "networkpolicy", "--all-namespaces"): "weather np",
            ("kubectl", "get", "ns", "kyverno"): "kyverno",
            (
                "kubectl",
                "-n",
                "kyverno",
                "get",
                "deploy",
            ): "kyverno-admission-controller",
            ("kubectl", "get", "crd"): "policies.kyverno.io",
            ("kubectl", "get", "policyreport", "--all-namespaces"): "weather report",
            ("trivy", "--version"): "trivy",
            ("syft", "version"): "syft",
            ("cosign", "version"): "cosign",
            ("git", "--version"): "git version 2.43.0",
            ("terraform", "version"): "Terraform v1.8.0",
            ("ansible", "--version"): "ansible [core 2.16.0",
            ("ansible-lint", "--version"): "ansible-lint 24.0.0",
            ("argocd", "version", "--client"): "argocd: v2.11.0",
            ("kubectl", "get", "ns", "argocd"): "argocd",
            ("kubectl", "-n", "argocd", "get", "deploy"): "argocd-server",
            (
                "kubectl",
                "get",
                "crd",
                "applications.argoproj.io",
            ): "applications.argoproj.io",
            (
                "kubectl",
                "get",
                "crd",
                "servicemonitors.monitoring.coreos.com",
            ): "servicemonitors.monitoring.coreos.com",
            (
                "kubectl",
                "get",
                "crd",
                "prometheusrules.monitoring.coreos.com",
            ): "prometheusrules.monitoring.coreos.com",
            ("kubectl", "get", "ns", "monitoring"): "monitoring",
            ("kubectl", "-n", "monitoring", "get", "deploy"): "prometheus grafana",
            ("kubectl", "-n", "monitoring", "get", "svc"): "prometheus grafana",
            (
                "kubectl",
                "get",
                "pods",
                "--all-namespaces",
            ): "monitoring loki-0 grafana promtail-agent",
        }
        return subprocess.CompletedProcess(command, 0, outputs[tuple(command)], "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Docker" in result.output
    assert "kind" in result.output
    assert "kubectl" in result.output
    assert "kind-devsecops" in result.output
    assert "Checking local DevSecOps toolchain" in result.output
    assert "Checking metrics-server availability" in result.output
    assert "Ready for local kind workflows" in result.output
    assert "metrics-server available" in result.output
    assert "HPA can read CPU and memory metrics" in result.output
    assert "Checking ingress-nginx readiness" in result.output
    assert "ingress-nginx available" in result.output
    assert "Checking cert-manager readiness" in result.output
    assert "cert-manager available" in result.output
    assert "Checking Linkerd service mesh readiness" in result.output
    assert "Linkerd control plane appears to be available" in result.output
    assert "Linkerd Viz appears to be available" in result.output
    assert "Checking NetworkPolicy and CNI readiness" in result.output
    assert "NetworkPolicy-capable CNI appears to be present" in result.output
    assert "Checking Kyverno policy readiness" in result.output
    assert "Kyverno appears to be installed" in result.output
    assert "Checking supply chain tooling" in result.output
    assert "Supply chain tools detected" in result.output


def test_cli_doctor_docker_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[0] == "docker":
            raise FileNotFoundError
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Docker" in result.output
    assert "missing" in result.output
    assert "Install docker" in result.output
    assert "Missing or failing prerequisites" in result.output


def test_cli_doctor_kind_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[0] == "kind":
            raise FileNotFoundError
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "kind" in result.output
    assert "Install kind" in result.output


def test_cli_doctor_kubectl_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[0] == "kubectl":
            raise FileNotFoundError
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "kubectl" in result.output
    assert "Install kubectl" in result.output
    assert "unavailable" in result.output


def test_cli_doctor_multiple_tools_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert result.output.count("missing") >= 3
    assert "Missing or failing prerequisites" in result.output


def test_cli_doctor_metrics_server_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == METRICS_SERVER_COMMAND:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "metrics-server" in result.output
    assert "metrics-server not found" in result.output
    assert "CPU-based scaling will not work" in result.output


def test_cli_doctor_metrics_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == METRICS_SERVER_COMMAND:
            return subprocess.CompletedProcess(command, 2, "", "api unavailable")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "api unavailable" in result.output
    assert "CPU-based scaling will not work" in result.output


def test_cli_doctor_ingress_nginx_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == INGRESS_NGINX_COMMAND:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "ingress-nginx not found" in result.output
    assert "will not install ingress-nginx automatically" in result.output
    assert "Ready for local kind workflows" in result.output


def test_cli_doctor_cert_manager_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == CERT_MANAGER_COMMAND:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "cert-manager not found" in result.output
    assert "will not install cert-manager automatically" in result.output
    assert "Ready for local kind workflows" in result.output


def test_cli_cluster_create_calls_kind_create(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command == ["kind", "get", "clusters"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] == ["kind", "create", "cluster"]:
            return subprocess.CompletedProcess(command, 0, "created", "")
        if command == [
            "kubectl",
            "wait",
            "--for=condition=Ready",
            "nodes",
            "--all",
            "--timeout=120s",
        ]:
            return subprocess.CompletedProcess(command, 0, "node/devsecops ready", "")
        if command == ["kubectl", "config", "current-context"]:
            return subprocess.CompletedProcess(command, 0, "kind-devsecops", "")
        if command == ["kubectl", "get", "nodes"]:
            return subprocess.CompletedProcess(command, 0, "node Ready", "")
        raise AssertionError(command)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["cluster", "create", "--name", "devsecops"])

    assert result.exit_code == 0
    assert ["kind", "create", "cluster", "--name", "devsecops"] in calls
    assert [
        "kubectl",
        "wait",
        "--for=condition=Ready",
        "nodes",
        "--all",
        "--timeout=120s",
    ] in calls
    assert "created" in result.output
    assert "node/devsecops ready" in result.output
    assert "node Ready" in result.output


def test_cli_cluster_create_wait_failure_is_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == ["kind", "get", "clusters"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command == ["kind", "create", "cluster", "--name", "devsecops"]:
            return subprocess.CompletedProcess(command, 0, "created", "")
        if command == [
            "kubectl",
            "wait",
            "--for=condition=Ready",
            "nodes",
            "--all",
            "--timeout=120s",
        ]:
            return subprocess.CompletedProcess(command, 1, "", "timed out waiting")
        raise AssertionError(command)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["cluster", "create", "--name", "devsecops"])

    assert result.exit_code == 1
    assert "timed out waiting" in result.output
    assert "Timed out or failed while waiting for nodes to be Ready" in result.output
    assert "kubectl get nodes" in result.output
    assert "kubectl get pods -A" in result.output


def test_cli_cluster_create_existing_does_not_recreate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command == ["kind", "get", "clusters"]:
            return subprocess.CompletedProcess(command, 0, "devsecops\n", "")
        if command == ["kubectl", "config", "current-context"]:
            return subprocess.CompletedProcess(command, 0, "kind-devsecops", "")
        if command == ["kubectl", "get", "nodes"]:
            return subprocess.CompletedProcess(command, 0, "node Ready", "")
        raise AssertionError(command)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["cluster", "create", "--name", "devsecops"])

    assert result.exit_code == 0
    assert "already exists" in result.output
    assert ["kind", "create", "cluster", "--name", "devsecops"] not in calls
    assert not any(command[:2] == ["kubectl", "wait"] for command in calls)


def test_cli_cluster_status_calls_expected_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command == ["kind", "get", "clusters"]:
            return subprocess.CompletedProcess(command, 0, "devsecops\n", "")
        if command == ["kubectl", "config", "current-context"]:
            return subprocess.CompletedProcess(command, 0, "kind-devsecops", "")
        if command == ["kubectl", "get", "nodes"]:
            return subprocess.CompletedProcess(command, 0, "node Ready", "")
        raise AssertionError(command)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["cluster", "status", "--name", "devsecops"])

    assert result.exit_code == 0
    assert calls == [
        ["kind", "get", "clusters"],
        ["kubectl", "config", "current-context"],
        ["kubectl", "get", "nodes"],
    ]
    assert "Checking kind cluster status" in result.output
    assert "A Ready node means Kubernetes can schedule and run pods" in result.output
    assert "kind cluster devsecops exists" in result.output


def test_cli_cluster_status_missing_cluster_is_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "other\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["cluster", "status", "--name", "devsecops"])

    assert result.exit_code == 1
    assert "kind cluster devsecops does not exist" in result.output


def test_cli_cluster_delete_refusal_does_not_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "deleted", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(
        app, ["cluster", "delete", "--name", "devsecops"], input="n\n"
    )

    assert result.exit_code == 0
    assert calls == []
    assert "cluster delete cancelled" in result.output


def test_cli_cluster_delete_confirmation_calls_kind_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "deleted", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(
        app, ["cluster", "delete", "--name", "devsecops"], input="y\n"
    )

    assert result.exit_code == 0
    assert calls == [["kind", "delete", "cluster", "--name", "devsecops"]]
    assert "deleted" in result.output


def test_cli_cluster_delete_yes_calls_kind_delete_without_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "deleted", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["cluster", "delete", "--name", "devsecops", "--yes"])

    assert result.exit_code == 0
    assert calls == [["kind", "delete", "cluster", "--name", "devsecops"]]
    assert "Delete kind cluster" not in result.output


def test_cli_image_load_checks_image_and_loads_into_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, "[]", "")
        if command[:3] == ["kind", "load", "docker-image"]:
            return subprocess.CompletedProcess(command, 0, "loaded", "")
        raise AssertionError(command)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(
        app, ["image", "load", "demo-app:latest", "--cluster", "devsecops"]
    )

    assert result.exit_code == 0
    assert calls == [
        ["docker", "image", "inspect", "demo-app:latest"],
        ["kind", "load", "docker-image", "demo-app:latest", "--name", "devsecops"],
    ]
    assert "Loading Docker image into kind cluster" in result.output
    assert "kind nodes use their own containerd image store" in result.output
    assert "Loaded demo-app:latest" in result.output


def test_cli_image_load_fails_if_image_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, "", "No such image")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(
        app, ["image", "load", "demo-app:latest", "--cluster", "devsecops"]
    )

    assert result.exit_code == 1
    assert calls == [["docker", "image", "inspect", "demo-app:latest"]]
    assert "No such image" in result.output
    assert "was not found locally" in result.output


def _write_mesh_config(path: Path) -> None:
    path.write_text(
        """
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
config:
  APP_ENV: "dev"
secrets:
  API_TOKEN: "change-me"
service:
  enabled: true
  port: 80
resources:
  requests:
    cpu: "50m"
    memory: "64Mi"
  limits:
    cpu: "250m"
    memory: "128Mi"
probes:
  liveness: "/healthz"
  readiness: "/readyz"
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 6
  targetCPUUtilizationPercentage: 70
ingress:
  enabled: false
  host: null
mesh:
  enabled: true
  provider: linkerd
  inject: true
  annotations:
    linkerd.io/inject: enabled
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_mesh_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_mesh_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "Service mesh support is enabled" in result.output
    assert "sidecar proxy" in result.output
    assert "2/2 containers" in result.output
    assert "Linkerd injection is enabled" in result.output
    assert "linkerd.io/inject: enabled" in result.output
    assert "linkerd check" in result.output


def test_cli_render_mentions_linkerd_annotation(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_mesh_config(config_path)

    result = runner.invoke(
        app, ["render", str(config_path), "--output", str(output_dir)]
    )

    deployment = (output_dir / "30-deployment.yaml").read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert "Linkerd injection is enabled" in result.output
    assert "does not install Linkerd" in result.output
    assert "kubectl -n weather get pods" in result.output
    assert "linkerd.io/inject" in deployment


def test_cli_helm_render_mentions_linkerd_annotation(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "charts"
    _write_mesh_config(config_path)

    result = runner.invoke(
        app, ["helm", "render", str(config_path), "--output", str(output_dir)]
    )

    deployment = (
        output_dir / "weatherapi" / "templates" / "deployment.yaml"
    ).read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert "Linkerd injection is enabled" in result.output
    assert "helm upgrade" in result.output
    assert "linkerd stat deploy -n weather" in result.output
    assert ".Values.mesh.enabled" in deployment


def test_cli_doctor_linkerd_absent_is_non_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[0] == "linkerd" or command in (
            LINKERD_NAMESPACE_COMMAND,
            LINKERD_CONTROL_PLANE_COMMAND,
            LINKERD_VIZ_COMMAND,
        ):
            if command[0] == "linkerd":
                raise FileNotFoundError
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking Linkerd service mesh readiness" in result.output
    assert "Linkerd does not appear to be installed" in result.output
    assert "will not install it automatically" in result.output
    assert "Ready for local kind workflows" in result.output


def test_cli_doctor_linkerd_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Linkerd control plane appears to be available" in result.output
    assert "Linkerd Viz appears to be available" in result.output


def test_cli_doctor_linkerd_cli_present_namespace_absent_is_clear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == LINKERD_NAMESPACE_COMMAND:
            return subprocess.CompletedProcess(
                command, 1, "", 'namespaces "linkerd" not found'
            )
        if command == LINKERD_VIZ_COMMAND:
            return subprocess.CompletedProcess(
                command, 1, "", 'namespaces "linkerd-viz" not found'
            )
        if command == LINKERD_CONTROL_PLANE_COMMAND:
            raise AssertionError("control plane must not be checked without namespace")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Linkerd CLI" in result.output
    assert "OK" in result.output
    assert "Linkerd namespace" in result.output
    assert "missing" in result.output
    assert "Linkerd namespace is missing" in result.output
    assert "Linkerd control plane" in result.output
    assert "plane was not" in result.output
    assert "Linkerd does not appear to be installed in this cluster" in result.output
    assert "k8s-forge will not install it automatically" in result.output
    assert "Install and validate Linkerd manually" in result.output
    assert "Linkerd Viz is optional and was not detected" in result.output
    assert "Ready for local kind workflows" in result.output


def _write_network_policy_config(path: Path) -> None:
    path.write_text(
        """
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
service:
  enabled: true
  port: 80
ingress:
  enabled: true
  host: weather.local
networkPolicy:
  enabled: true
  profile: ingress-only
  ingress:
    enabled: true
    fromNamespaces:
      - ingress-nginx
    ports:
      - 8000
  egress:
    enabled: false
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_network_policy_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_network_policy_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "NetworkPolicy support is enabled" in result.output
    assert "restricts which traffic" in result.output
    assert "ingress-only profile" in result.output
    assert "kubectl -n weather get networkpolicy" in result.output


def test_cli_render_mentions_network_policy(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_network_policy_config(config_path)

    result = runner.invoke(
        app, ["render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "70-networkpolicy.yaml" in result.output
    assert "NetworkPolicy enforcement depends on the CNI plugin" in result.output
    assert "does not install or replace the CNI" in result.output
    assert (output_dir / "70-networkpolicy.yaml").exists()


def test_cli_helm_render_mentions_network_policy(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "charts"
    _write_network_policy_config(config_path)

    result = runner.invoke(
        app, ["helm", "render", str(config_path), "--output", str(output_dir)]
    )

    chart_dir = output_dir / "weatherapi"
    assert result.exit_code == 0
    assert "templates/networkpolicy.yaml" in result.output
    assert "NetworkPolicy support is enabled" in result.output
    assert "helm template" in result.output
    assert (chart_dir / "templates" / "networkpolicy.yaml").exists()


def test_cli_doctor_reports_kindnet_cni_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == CNI_PODS_COMMAND:
            return subprocess.CompletedProcess(command, 0, "kindnet", "")
        if command == NETWORK_POLICY_COMMAND:
            return subprocess.CompletedProcess(command, 0, "No resources found", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking NetworkPolicy and CNI readiness" in result.output
    assert "Detected kindnet" in result.output
    assert "does not install or replace the CNI" in result.output
    assert "Ready for local kind workflows" in result.output


def test_cli_doctor_reports_unknown_cni(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == CNI_PODS_COMMAND:
            return subprocess.CompletedProcess(command, 0, "custom-network", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Could not identify a NetworkPolicy-enforcing CNI" in result.output


def test_cli_doctor_reports_cilium_or_calico_as_capable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == CNI_PODS_COMMAND:
            return subprocess.CompletedProcess(command, 0, "cilium-agent", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "NetworkPolicy-capable CNI appears to be present" in result.output
    assert "cilium" in result.output


def _write_policy_config(path: Path, action: str = "Audit") -> None:
    path.write_text(
        f"""
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
service:
  enabled: true
  port: 80
policy:
  enabled: true
  provider: kyverno
  profile: baseline
  validationFailureAction: {action}
  background: true
  rules:
    requireRecommendedLabels: true
    disallowPrivilegedContainers: true
    requireRunAsNonRoot: true
    requireResources: true
    disallowLatestTag: true
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_kyverno_policy_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_policy_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "Kyverno policy support is enabled" in result.output
    assert "admission controller" in result.output
    assert "Audit mode" in result.output
    assert "kubectl -n weather get policy" in result.output
    assert "kubectl get policyreport -A" in result.output


def test_cli_check_mentions_kyverno_enforce_mode(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_policy_config(config_path, action="Enforce")

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "Enforce mode" in result.output
    assert "may be rejected" in result.output


def test_cli_render_mentions_kyverno_policy(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_policy_config(config_path)

    result = runner.invoke(
        app, ["render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "80-kyverno-policy.yaml" in result.output
    assert "does not install Kyverno" in result.output
    assert (output_dir / "80-kyverno-policy.yaml").exists()


def test_cli_helm_render_mentions_kyverno_policy(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "charts"
    _write_policy_config(config_path)

    result = runner.invoke(
        app, ["helm", "render", str(config_path), "--output", str(output_dir)]
    )

    chart_dir = output_dir / "weatherapi"
    assert result.exit_code == 0
    assert "templates/kyverno-policy.yaml" in result.output
    assert "Kyverno policy support is enabled" in result.output
    assert "helm template" in result.output
    assert (chart_dir / "templates" / "kyverno-policy.yaml").exists()


def test_cli_doctor_reports_kyverno_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command in (KYVERNO_NAMESPACE_COMMAND, KYVERNO_DEPLOY_COMMAND):
            return subprocess.CompletedProcess(command, 1, "", "not found")
        if command == KYVERNO_CRD_COMMAND:
            return subprocess.CompletedProcess(command, 0, "deployments.apps", "")
        if command == POLICY_REPORT_COMMAND:
            return subprocess.CompletedProcess(
                command, 1, "", "the server doesn't have a resource type"
            )
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking Kyverno policy readiness" in result.output
    assert "Kyverno does not appear to be installed" in result.output
    assert "will not install it automatically" in result.output
    assert "reviewed locally" in result.output
    assert "PolicyReport resource type is not available" in result.output
    assert (
        "PolicyReports are not available yet or no reports were found" in result.output
    )
    assert "Ready for local kind workflows" in result.output


def test_cli_doctor_reports_kyverno_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == KYVERNO_CRD_COMMAND:
            return subprocess.CompletedProcess(command, 0, "policies.kyverno.io", "")
        if command == POLICY_REPORT_COMMAND:
            return subprocess.CompletedProcess(command, 0, "weather report", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Kyverno appears to be installed" in result.output
    assert "PolicyReports are available" in result.output


def _write_supply_chain_config(
    path: Path,
    image: str = "weatherapi:0.1.0",
    signing: bool = False,
) -> None:
    path.write_text(
        f"""
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
service:
  enabled: true
  port: 80
supplyChain:
  enabled: true
  image: {image}
  scan:
    enabled: true
    tool: trivy
    severity:
      - HIGH
      - CRITICAL
  sbom:
    enabled: true
    tool: syft
    format: cyclonedx-json
  signing:
    enabled: {str(signing).lower()}
    tool: cosign
    keyless: true
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_supply_chain_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_supply_chain_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "Supply chain readiness is enabled" in result.output
    assert "Trivy can scan" in result.output
    assert "Syft can generate" in result.output
    assert "does not install Trivy, Syft, or Cosign" in result.output


def test_cli_render_suggests_supply_chain_command(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_supply_chain_config(config_path)

    result = runner.invoke(
        app, ["render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "Supply chain readiness is enabled" in result.output
    assert "Kubernetes manifests were generated separately" in result.output
    assert "k8s-forge supply-chain render" in result.output
    assert not (output_dir / "scan-image.sh").exists()


def test_cli_supply_chain_render_generates_files(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-supply-chain"
    _write_supply_chain_config(config_path)

    result = runner.invoke(
        app, ["supply-chain", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "Supply chain files generated" in result.output
    assert "scan-image.sh" in result.output
    assert "generate-sbom.sh" in result.output
    assert (output_dir / "README.md").exists()
    assert (output_dir / "scan-image.sh").exists()
    assert (output_dir / "generate-sbom.sh").exists()
    assert not (output_dir / "sign-image.sh").exists()


def test_cli_supply_chain_render_generates_signing_files_when_enabled(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-supply-chain"
    _write_supply_chain_config(config_path, signing=True)

    result = runner.invoke(
        app, ["supply-chain", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert (
        "Cosign signing usually requires a registry-backed image reference"
        in result.output
    )
    assert (output_dir / "sign-image.sh").exists()
    assert (output_dir / "verify-image.sh").exists()


def test_cli_supply_chain_render_warns_for_latest(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-supply-chain"
    _write_supply_chain_config(config_path, image="weatherapi:latest")

    result = runner.invoke(
        app, ["supply-chain", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "uses the latest tag" in result.output
    assert "weak for traceability" in result.output


def test_cli_supply_chain_render_disabled_is_clean(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
app:
  name: demo-app
  namespace: demo
  image: demo-app:1.0.0
  containerPort: 8000
  replicas: 1
supplyChain:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["supply-chain", "render", str(config_path)])

    assert result.exit_code == 0
    assert "Supply chain readiness is disabled" in result.output
    assert "No supply chain files were generated" in result.output


def test_cli_doctor_reports_supply_chain_tools_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command in (TRIVY_COMMAND, SYFT_COMMAND, COSIGN_COMMAND):
            raise FileNotFoundError
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking supply chain tooling" in result.output
    assert "Trivy is not installed" in result.output
    assert "Syft is not installed" in result.output
    assert "Cosign is not installed" in result.output
    assert "Ready for local kind workflows" in result.output


def test_cli_doctor_reports_supply_chain_tools_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Supply chain tools detected" in result.output


def _write_ci_config(path: Path, image: str = "weatherapi:0.1.0") -> None:
    path.write_text(
        f"""
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
service:
  enabled: true
  port: 80
ci:
  enabled: true
  provider: github-actions
  python:
    enabled: true
    version: "3.12"
    quality:
      ruff: true
      mypy: true
      bandit: true
      pipAudit: true
      pytest: true
      build: true
  container:
    enabled: true
    image: {image}
    dockerfile: Dockerfile
    context: .
    scan:
      enabled: true
      tool: trivy
      severity:
        - HIGH
        - CRITICAL
    sbom:
      enabled: true
      tool: syft
      format: cyclonedx-json
  artifacts:
    enabled: true
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_ci_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_ci_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "CI readiness is enabled" in result.output
    assert "GitHub Actions can automate" in result.output
    assert "does not push code" in result.output


def test_cli_render_suggests_ci_render_command(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_ci_config(config_path)

    result = runner.invoke(
        app, ["render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "Kubernetes manifests were generated separately" in result.output
    assert "k8s-forge ci render" in result.output
    assert not (output_dir / ".github" / "workflows" / "ci.yml").exists()


def test_cli_ci_render_generates_workflows(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-ci"
    _write_ci_config(config_path)

    result = runner.invoke(
        app, ["ci", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "CI files generated" in result.output
    assert "Generated CI files" in result.output
    assert (output_dir / "README.md").exists()
    assert (output_dir / ".github" / "workflows" / "ci.yml").exists()
    assert (output_dir / ".github" / "workflows" / "security.yml").exists()


def test_cli_ci_render_refuses_overwrite_without_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-ci"
    _write_ci_config(config_path)
    first = runner.invoke(
        app, ["ci", "render", str(config_path), "--output", str(output_dir)]
    )
    assert first.exit_code == 0

    result = runner.invoke(
        app, ["ci", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 1
    assert "use --force" in result.output


def test_cli_ci_render_overwrites_with_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-ci"
    _write_ci_config(config_path)
    first = runner.invoke(
        app, ["ci", "render", str(config_path), "--output", str(output_dir)]
    )
    assert first.exit_code == 0

    result = runner.invoke(
        app,
        ["ci", "render", str(config_path), "--output", str(output_dir), "--force"],
    )

    assert result.exit_code == 0
    assert "CI files generated" in result.output


def test_cli_ci_render_warns_for_direct_workflow_output(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / ".github" / "workflows"
    _write_ci_config(config_path)

    result = runner.invoke(
        app, ["ci", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "The output target is .github/workflows/" in result.output
    assert (output_dir / "ci.yml").exists()
    assert (output_dir / "security.yml").exists()
    assert (output_dir / "README.k8s-forge-ci.md").exists()


def test_cli_ci_render_warns_for_latest_image(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-ci"
    _write_ci_config(config_path, image="weatherapi:latest")

    result = runner.invoke(
        app, ["ci", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "uses the latest tag" in result.output
    assert "weak for traceability" in result.output


def test_cli_ci_render_disabled_is_clean(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
app:
  name: demo-app
  namespace: demo
  image: demo-app:1.0.0
  containerPort: 8000
  replicas: 1
ci:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["ci", "render", str(config_path)])

    assert result.exit_code == 0
    assert "CI readiness is disabled" in result.output
    assert "No CI workflow files were generated" in result.output


def test_cli_doctor_reports_git_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == GIT_COMMAND:
            raise FileNotFoundError
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking CI readiness" in result.output
    assert "Git is not available" in result.output


def test_cli_doctor_reports_git_present(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == GIT_COMMAND:
            return subprocess.CompletedProcess(command, 0, "git version 2.43.0", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking CI readiness" in result.output
    assert "Git is available" in result.output


def _write_gitops_config(
    path: Path,
    repo_url: str = "https://github.com/example/weatherapi-platform.git",
    automated: bool = False,
    prune: bool = False,
    self_heal: bool = False,
) -> None:
    path.write_text(
        f"""
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
service:
  enabled: true
  port: 80
gitops:
  enabled: true
  provider: argocd
  application:
    name: ""
    namespace: argocd
    project: default
  destination:
    server: https://kubernetes.default.svc
    namespace: ""
  source:
    repoURL: {repo_url}
    targetRevision: main
    path: charts-generated/weatherapi
    type: helm
  syncPolicy:
    automated: {str(automated).lower()}
    prune: {str(prune).lower()}
    selfHeal: {str(self_heal).lower()}
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_gitops_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_gitops_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "GitOps readiness is enabled" in result.output
    assert "ArgoCD can continuously compare" in result.output
    assert "does not install ArgoCD" in result.output


def test_cli_render_suggests_gitops_render_command(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_gitops_config(config_path)

    result = runner.invoke(
        app, ["render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "Kubernetes manifests were generated separately" in result.output
    assert "k8s-forge gitops render" in result.output
    assert not (output_dir / "argocd" / "application.yaml").exists()


def test_cli_gitops_render_generates_files(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-gitops"
    _write_gitops_config(config_path, repo_url="https://github.com/acme/weather.git")

    result = runner.invoke(
        app, ["gitops", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "GitOps files generated" in result.output
    assert "Generated GitOps files" in result.output
    assert (output_dir / "README.md").exists()
    assert (output_dir / "argocd" / "application.yaml").exists()


def test_cli_gitops_render_refuses_overwrite_without_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-gitops"
    _write_gitops_config(config_path, repo_url="https://github.com/acme/weather.git")
    first = runner.invoke(
        app, ["gitops", "render", str(config_path), "--output", str(output_dir)]
    )
    assert first.exit_code == 0

    result = runner.invoke(
        app, ["gitops", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 1
    assert "use --force" in result.output


def test_cli_gitops_render_overwrites_with_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-gitops"
    _write_gitops_config(config_path, repo_url="https://github.com/acme/weather.git")
    first = runner.invoke(
        app, ["gitops", "render", str(config_path), "--output", str(output_dir)]
    )
    assert first.exit_code == 0

    result = runner.invoke(
        app,
        [
            "gitops",
            "render",
            str(config_path),
            "--output",
            str(output_dir),
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "GitOps files generated" in result.output


def test_cli_gitops_render_warns_for_example_repo_url(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-gitops"
    _write_gitops_config(config_path)

    result = runner.invoke(
        app, ["gitops", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "repoURL still looks like an example value" in result.output


def test_cli_gitops_render_warns_for_automated_prune_self_heal(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-gitops"
    _write_gitops_config(
        config_path,
        repo_url="https://github.com/acme/weather.git",
        automated=True,
        prune=True,
        self_heal=True,
    )

    result = runner.invoke(
        app, ["gitops", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "automated sync is enabled" in result.output
    assert "prune is enabled" in result.output
    assert "selfHeal is enabled" in result.output


def test_cli_gitops_render_disabled_is_clean(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
app:
  name: demo-app
  namespace: demo
  image: demo-app:1.0.0
  containerPort: 8000
  replicas: 1
gitops:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["gitops", "render", str(config_path)])

    assert result.exit_code == 0
    assert "GitOps readiness is disabled" in result.output
    assert "No GitOps files were generated" in result.output


def test_cli_doctor_reports_argocd_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == ARGOCD_CLI_COMMAND:
            raise FileNotFoundError
        if tuple(command) in {
            tuple(ARGOCD_NAMESPACE_COMMAND),
            tuple(ARGOCD_APPLICATION_CRD_COMMAND),
        }:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking ArgoCD GitOps readiness" in result.output
    assert "ArgoCD does not appear to be installed" in result.output


def test_cli_doctor_reports_argocd_present(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking ArgoCD GitOps readiness" in result.output
    assert "ArgoCD appears to be installed" in result.output


def _write_observability_config(
    path: Path,
    alerts: bool = False,
    dashboard: bool = True,
) -> None:
    path.write_text(
        f"""
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
service:
  enabled: true
  port: 80
observability:
  enabled: true
  provider: prometheus
  metrics:
    enabled: true
    path: /metrics
    portName: http
    interval: 30s
  serviceMonitor:
    enabled: true
    namespace: ""
    labels: {{}}
  grafana:
    enabled: true
    dashboard:
      enabled: {str(dashboard).lower()}
      title: ""
  alerts:
    enabled: {str(alerts).lower()}
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_observability_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_observability_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "Observability readiness is enabled" in result.output
    assert "Prometheus can scrape application metrics" in result.output
    assert "Metrics endpoint: /metrics" in result.output
    assert "ServiceMonitor namespace: weather" in result.output
    assert "Grafana dashboard: enabled" in result.output


def test_cli_render_suggests_observability_render_command(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_observability_config(config_path)

    result = runner.invoke(
        app, ["render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "Kubernetes manifests were generated separately" in result.output
    assert "k8s-forge observability render" in result.output
    assert not (output_dir / "prometheus" / "servicemonitor.yaml").exists()


def test_cli_observability_render_generates_files(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-observability"
    _write_observability_config(config_path)

    result = runner.invoke(
        app,
        ["observability", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Observability files generated" in result.output
    assert "Generated observability files" in result.output
    assert (output_dir / "README.md").exists()
    assert (output_dir / "prometheus" / "servicemonitor.yaml").exists()
    assert (output_dir / "grafana" / "dashboard.json").exists()


def test_cli_observability_render_warns_for_uncertain_metrics(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-observability"
    _write_observability_config(config_path)

    result = runner.invoke(
        app,
        ["observability", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "ServiceMonitor readiness is enabled" in result.output
    assert "Grafana dashboard is a local model" in result.output


def test_cli_observability_render_warns_when_alerts_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-observability"
    _write_observability_config(config_path, alerts=True)

    result = runner.invoke(
        app,
        ["observability", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "PrometheusRule rendering" in result.output
    assert "v0.11.0" in result.output


def test_cli_observability_render_disabled_is_clean(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
app:
  name: demo-app
  namespace: demo
  image: demo-app:1.0.0
  containerPort: 8000
  replicas: 1
observability:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["observability", "render", str(config_path)])

    assert result.exit_code == 0
    assert "Observability readiness is disabled" in result.output
    assert "No observability files were generated" in result.output


def test_cli_observability_render_refuses_overwrite_without_force(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-observability"
    _write_observability_config(config_path)
    first = runner.invoke(
        app,
        ["observability", "render", str(config_path), "--output", str(output_dir)],
    )
    assert first.exit_code == 0

    result = runner.invoke(
        app,
        ["observability", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 1
    assert "use --force" in result.output


def test_cli_observability_render_overwrites_with_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-observability"
    _write_observability_config(config_path)
    first = runner.invoke(
        app,
        ["observability", "render", str(config_path), "--output", str(output_dir)],
    )
    assert first.exit_code == 0

    result = runner.invoke(
        app,
        [
            "observability",
            "render",
            str(config_path),
            "--output",
            str(output_dir),
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "Observability files generated" in result.output


def test_cli_doctor_reports_observability_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if tuple(command) in {
            tuple(SERVICEMONITOR_CRD_COMMAND),
            tuple(PROMETHEUSRULE_CRD_COMMAND),
            tuple(MONITORING_NAMESPACE_COMMAND),
        }:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking observability readiness" in result.output
    assert "Prometheus Operator CRDs do not appear to be installed" in result.output


def test_cli_doctor_reports_observability_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking observability readiness" in result.output
    assert "ServiceMonitor CRD appears to be available" in result.output


def _write_logging_config(
    path: Path,
    dashboard: bool = True,
) -> None:
    path.write_text(
        f"""
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
service:
  enabled: true
  port: 80
logging:
  enabled: true
  provider: loki
  applicationLogs:
    enabled: true
    source: stdout
  loki:
    namespace: monitoring
    datasourceName: Loki
  collector:
    enabled: true
    type: promtail
  grafana:
    enabled: true
    dashboard:
      enabled: {str(dashboard).lower()}
      title: ""
  queries:
    enabled: true
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_logging_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_logging_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "Logging readiness is enabled" in result.output
    assert "Loki can store and query Kubernetes logs" in result.output
    assert "Logging provider: loki" in result.output
    assert "Application log source: stdout" in result.output
    assert "Collector model: promtail" in result.output
    assert "Grafana logs dashboard: enabled" in result.output


def test_cli_render_suggests_logging_render_command(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_logging_config(config_path)

    result = runner.invoke(
        app, ["render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "Kubernetes manifests were generated separately" in result.output
    assert "k8s-forge logging render" in result.output
    assert not (output_dir / "loki" / "logql-queries.md").exists()


def test_cli_logging_render_generates_files(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-logging"
    _write_logging_config(config_path)

    result = runner.invoke(
        app, ["logging", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "Rendering logging readiness files from app.yaml" in result.output
    assert "does not contact the cluster" in result.output
    assert "Logging files generated" in result.output
    assert "Generated logging files" in result.output
    assert (output_dir / "README.md").exists()
    assert (output_dir / "loki" / "logql-queries.md").exists()
    assert (output_dir / "grafana" / "logs-dashboard.json").exists()
    assert (output_dir / "collector" / "collector-notes.md").exists()


def test_cli_logging_render_prints_warnings(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-logging"
    _write_logging_config(config_path)

    result = runner.invoke(
        app, ["logging", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 0
    assert "collector model" in result.output
    assert "Loki datasource" in result.output
    assert "LogQL labels are examples" in result.output
    assert "stdout or stderr" in result.output


def test_cli_logging_render_disabled_is_clean(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
app:
  name: demo-app
  namespace: demo
  image: demo-app:1.0.0
  containerPort: 8000
  replicas: 1
logging:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["logging", "render", str(config_path)])

    assert result.exit_code == 0
    assert "Logging readiness is disabled" in result.output
    assert "No logging files were generated" in result.output


def test_cli_logging_render_refuses_overwrite_without_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-logging"
    _write_logging_config(config_path)
    first = runner.invoke(
        app, ["logging", "render", str(config_path), "--output", str(output_dir)]
    )
    assert first.exit_code == 0

    result = runner.invoke(
        app, ["logging", "render", str(config_path), "--output", str(output_dir)]
    )

    assert result.exit_code == 1
    assert "use --force" in result.output


def test_cli_logging_render_overwrites_with_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-logging"
    _write_logging_config(config_path)
    first = runner.invoke(
        app, ["logging", "render", str(config_path), "--output", str(output_dir)]
    )
    assert first.exit_code == 0

    result = runner.invoke(
        app,
        [
            "logging",
            "render",
            str(config_path),
            "--output",
            str(output_dir),
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "Logging files generated" in result.output


def test_cli_doctor_reports_logging_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == CLUSTER_PODS_COMMAND:
            return subprocess.CompletedProcess(command, 0, "weather pod", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking logging readiness" in result.output
    assert "Loki or a compatible log collector does not appear" in result.output


def test_cli_doctor_reports_logging_present(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == CLUSTER_PODS_COMMAND:
            return subprocess.CompletedProcess(
                command, 0, "monitoring loki-0 grafana promtail-agent", ""
            )
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking logging readiness" in result.output
    assert "Loki and a compatible log collector appear" in result.output
    assert "Grafana appears to be available" in result.output


def _write_terraform_config(path: Path, enabled: bool = True) -> None:
    path.write_text(
        f"""
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
service:
  enabled: true
  port: 80
terraform:
  enabled: {str(enabled).lower()}
  projectName: ""
  backend:
    type: local
  providers:
    kubernetes:
      enabled: true
    helm:
      enabled: true
    cloud:
      enabled: false
  modules:
    enabled: true
  examples:
    enabled: true
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_terraform_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_terraform_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "Terraform readiness is enabled" in result.output
    assert "Terraform backend: local" in result.output
    assert "Kubernetes provider example: enabled" in result.output
    assert "Helm provider example: enabled" in result.output
    assert "Cloud provider example: disabled" in result.output
    assert "does not run Terraform commands" in result.output


def test_cli_render_suggests_terraform_render_command(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_terraform_config(config_path)

    result = runner.invoke(
        app,
        ["render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Terraform readiness is enabled" in result.output
    assert "Kubernetes manifests were generated separately" in result.output
    assert "k8s-forge terraform render" in result.output
    assert not (output_dir / "versions.tf").exists()


def test_cli_terraform_render_generates_files(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-terraform"
    _write_terraform_config(config_path)

    result = runner.invoke(
        app,
        ["terraform", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Rendering Terraform readiness files" in result.output
    assert "does not contact the cluster" in result.output
    assert "does not run Terraform" in result.output
    assert "Terraform files generated" in result.output
    assert "versions.tf" in result.output
    assert (output_dir / "README.md").exists()
    assert (output_dir / "versions.tf").exists()
    assert (output_dir / "providers.tf").exists()
    assert (output_dir / "variables.tf").exists()
    assert (output_dir / "main.tf").exists()
    assert (output_dir / "outputs.tf").exists()


def test_cli_terraform_render_disabled_is_clean(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-terraform"
    _write_terraform_config(config_path, enabled=False)

    result = runner.invoke(
        app,
        ["terraform", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Terraform readiness is disabled" in result.output
    assert not output_dir.exists()


def test_cli_terraform_render_refuses_overwrite_without_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-terraform"
    _write_terraform_config(config_path)
    output_dir.mkdir()
    (output_dir / "README.md").write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app,
        ["terraform", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 1
    assert "use --force" in result.output
    assert (output_dir / "README.md").read_text(encoding="utf-8") == "existing"


def test_cli_terraform_render_overwrites_with_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-terraform"
    _write_terraform_config(config_path)
    output_dir.mkdir()
    (output_dir / "README.md").write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "terraform",
            "render",
            str(config_path),
            "--output",
            str(output_dir),
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "Terraform Readiness" in (output_dir / "README.md").read_text(
        encoding="utf-8"
    )


def test_cli_doctor_reports_terraform_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == TERRAFORM_COMMAND:
            raise FileNotFoundError
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking Terraform readiness" in result.output
    assert "Terraform is not installed" in result.output
    assert "Ready for local kind workflows" in result.output


def test_cli_doctor_reports_terraform_present(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == TERRAFORM_COMMAND:
            return subprocess.CompletedProcess(command, 0, "Terraform v1.8.0", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Terraform is available" in result.output
    assert "Terraform v1.8.0" in result.output


def test_cli_doctor_never_runs_mutating_terraform_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden = {"init", "plan", "apply", "destroy"}
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command and command[0] == "terraform" and len(command) > 1:
            assert command[1] not in forbidden
            return subprocess.CompletedProcess(command, 0, "Terraform v1.8.0", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert TERRAFORM_COMMAND in calls


def _write_ansible_config(path: Path, enabled: bool = True) -> None:
    path.write_text(
        f"""
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
service:
  enabled: true
  port: 80
ansible:
  enabled: {str(enabled).lower()}
  projectName: ""
  inventory:
    type: local
    hosts:
      - localhost
  playbook:
    name: site.yml
  roles:
    enabled: true
  collections:
    kubernetes:
      enabled: true
    community:
      enabled: false
  examples:
    enabled: true
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_ansible_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_ansible_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "Ansible readiness is enabled" in result.output
    assert "Ansible inventory type: local" in result.output
    assert "Ansible example host: localhost" in result.output
    assert "Ansible roles structure: enabled" in result.output
    assert "Kubernetes collection example: enabled" in result.output
    assert "Community collection example: disabled" in result.output


def test_cli_render_suggests_ansible_render_command(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_ansible_config(config_path)

    result = runner.invoke(
        app,
        ["render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Ansible readiness is enabled" in result.output
    assert "Kubernetes manifests were generated separately" in result.output
    assert "k8s-forge ansible render" in result.output
    assert not (output_dir / "site.yml").exists()


def test_cli_ansible_render_generates_files(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-ansible"
    _write_ansible_config(config_path)

    result = runner.invoke(
        app,
        ["ansible", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Rendering Ansible readiness files" in result.output
    assert "does not contact hosts" in result.output
    assert "does not open SSH connections" in result.output
    assert "does not run Ansible" in result.output
    assert "Ansible files generated" in result.output
    assert "site.yml" in result.output
    assert (output_dir / "README.md").exists()
    assert (output_dir / "ansible.cfg").exists()
    assert (output_dir / "inventory.ini").exists()
    assert (output_dir / "site.yml").exists()
    assert (output_dir / "group_vars" / "all.yml").exists()
    assert (output_dir / "roles" / "README.md").exists()


def test_cli_ansible_render_disabled_is_clean(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-ansible"
    _write_ansible_config(config_path, enabled=False)

    result = runner.invoke(
        app,
        ["ansible", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Ansible readiness is disabled" in result.output
    assert not output_dir.exists()


def test_cli_ansible_render_refuses_overwrite_without_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-ansible"
    _write_ansible_config(config_path)
    output_dir.mkdir()
    (output_dir / "README.md").write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app,
        ["ansible", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 1
    assert "use --force" in result.output
    assert (output_dir / "README.md").read_text(encoding="utf-8") == "existing"


def test_cli_ansible_render_overwrites_with_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-ansible"
    _write_ansible_config(config_path)
    output_dir.mkdir()
    (output_dir / "README.md").write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "ansible",
            "render",
            str(config_path),
            "--output",
            str(output_dir),
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "Ansible Readiness" in (output_dir / "README.md").read_text(encoding="utf-8")


def test_cli_doctor_reports_ansible_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command in (ANSIBLE_COMMAND, ANSIBLE_LINT_COMMAND):
            raise FileNotFoundError
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Checking Ansible readiness" in result.output
    assert "Ansible is not installed" in result.output
    assert "ansible-lint is optional" in result.output
    assert "Ready for local kind workflows" in result.output


def test_cli_doctor_reports_ansible_present(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command == ANSIBLE_COMMAND:
            return subprocess.CompletedProcess(command, 0, "ansible [core 2.16.0]", "")
        if command == ANSIBLE_LINT_COMMAND:
            return subprocess.CompletedProcess(command, 0, "ansible-lint 24.0.0", "")
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Ansible is available" in result.output
    assert "ansible-lint is available" in result.output
    assert "ansible [core 2.16.0]" in result.output


def test_cli_doctor_never_runs_active_ansible_or_platform_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden = {
        "ansible-playbook",
        "ssh",
        "scp",
        "kubectl apply",
        "helm install",
        "terraform apply",
    }
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        rendered = " ".join(command)
        assert rendered not in forbidden
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert ANSIBLE_COMMAND in calls
    assert ANSIBLE_LINT_COMMAND in calls


def _write_security_config(path: Path, enabled: bool = True) -> None:
    path.write_text(
        f"""
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
service:
  enabled: true
  port: 80
resources:
  requests:
    cpu: "50m"
    memory: "64Mi"
  limits:
    cpu: "250m"
    memory: "128Mi"
probes:
  liveness: /healthz
  readiness: /readyz
networkPolicy:
  enabled: true
  profile: ingress-only
policy:
  enabled: true
  provider: kyverno
supplyChain:
  enabled: true
ci:
  enabled: true
  container:
    enabled: true
security:
  enabled: {str(enabled).lower()}
  projectName: ""
  container:
    enabled: true
  manifests:
    enabled: true
  rbac:
    enabled: true
  podSecurity:
    enabled: true
  network:
    enabled: true
  secrets:
    enabled: true
  supplyChain:
    enabled: true
  checklist:
    enabled: true
  examples:
    enabled: true
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_security_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_security_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "Security Audit readiness is enabled" in result.output
    assert "Security project: weatherapi" in result.output
    assert "Container security review: enabled" in result.output
    assert "Kubernetes manifest review: enabled" in result.output
    assert "RBAC review: enabled" in result.output
    assert "Pod security review: enabled" in result.output
    assert "Network security review: enabled" in result.output
    assert "Secrets review: enabled" in result.output
    assert "Supply chain review: enabled" in result.output
    assert "Final security checklist: enabled" in result.output


def test_cli_render_suggests_security_render_command(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_security_config(config_path)

    result = runner.invoke(
        app,
        ["render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Security Audit readiness is enabled" in result.output
    assert "Kubernetes manifests were generated separately" in result.output
    assert "k8s-forge security render" in result.output
    assert not (output_dir / "container-security.md").exists()


def test_cli_security_render_generates_files(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-security-audit"
    _write_security_config(config_path)

    result = runner.invoke(
        app,
        ["security", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Rendering Security Audit readiness files" in result.output
    assert "does not run scanners" in result.output
    assert "does not contact the cluster" in result.output
    assert "Security Audit files generated" in result.output
    assert "final-security-checklist.md" in result.output
    assert (output_dir / "README.md").exists()
    assert (output_dir / "container-security.md").exists()
    assert (output_dir / "kubernetes-manifest-audit.md").exists()
    assert (output_dir / "rbac-audit.md").exists()
    assert (output_dir / "pod-security-audit.md").exists()
    assert (output_dir / "network-security-audit.md").exists()
    assert (output_dir / "secrets-audit.md").exists()
    assert (output_dir / "supply-chain-security.md").exists()
    assert (output_dir / "final-security-checklist.md").exists()


def test_cli_security_render_disabled_is_clean(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-security-audit"
    _write_security_config(config_path, enabled=False)

    result = runner.invoke(
        app,
        ["security", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Security Audit readiness is disabled" in result.output
    assert not output_dir.exists()


def test_cli_security_render_refuses_overwrite_without_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-security-audit"
    _write_security_config(config_path)
    output_dir.mkdir()
    (output_dir / "README.md").write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app,
        ["security", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 1
    assert "use --force" in result.output
    assert (output_dir / "README.md").read_text(encoding="utf-8") == "existing"


def test_cli_security_render_overwrites_with_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-security-audit"
    _write_security_config(config_path)
    output_dir.mkdir()
    (output_dir / "README.md").write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "security",
            "render",
            str(config_path),
            "--output",
            str(output_dir),
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "Security Audit Readiness" in (output_dir / "README.md").read_text(
        encoding="utf-8"
    )


def _write_capstone_config(path: Path, enabled: bool = True) -> None:
    path.write_text(
        f"""
app:
  name: weatherapi
  namespace: weather
  image: weatherapi:0.1.0
  containerPort: 8000
  replicas: 2
service:
  enabled: true
  port: 80
security:
  enabled: true
capstone:
  enabled: {str(enabled).lower()}
  projectName: ""
  report:
    title: ""
    audience: technical
  checklist:
    enabled: true
  architecture:
    enabled: true
  devsecopsMatrix:
    enabled: true
  modulesSummary:
    enabled: true
  manualSteps:
    enabled: true
  runtimeDependencies:
    enabled: true
  securitySummary:
    enabled: true
  v1Readiness:
    enabled: true
  examples:
    enabled: true
""".strip(),
        encoding="utf-8",
    )


def test_cli_check_mentions_capstone_when_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    _write_capstone_config(config_path)

    result = runner.invoke(app, ["check", str(config_path)])

    assert result.exit_code == 0
    assert "Capstone readiness is enabled" in result.output
    assert "Capstone project: weatherapi" in result.output
    assert "Architecture overview: enabled" in result.output
    assert "DevSecOps matrix: enabled" in result.output
    assert "Modules summary: enabled" in result.output
    assert "Validation checklist: enabled" in result.output
    assert "Manual steps: enabled" in result.output
    assert "Runtime dependencies: enabled" in result.output
    assert "Security summary: enabled" in result.output
    assert "v1 readiness: enabled" in result.output


def test_cli_render_suggests_capstone_render_command(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated"
    _write_capstone_config(config_path)

    result = runner.invoke(
        app,
        ["render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Capstone readiness is enabled" in result.output
    assert "Kubernetes manifests were generated separately" in result.output
    assert "k8s-forge capstone render" in result.output
    assert not (output_dir / "lab-summary.md").exists()


def test_cli_capstone_render_generates_files(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-capstone"
    _write_capstone_config(config_path)

    result = runner.invoke(
        app,
        ["capstone", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Rendering Capstone readiness files" in result.output
    assert "final local DevSecOps lab summary" in result.output
    assert "does not contact the cluster" in result.output
    assert "Capstone files generated" in result.output
    assert "v1-readiness.md" in result.output
    assert (output_dir / "README.md").exists()
    assert (output_dir / "lab-summary.md").exists()
    assert (output_dir / "architecture-overview.md").exists()
    assert (output_dir / "devsecops-chain.md").exists()
    assert (output_dir / "modules-summary.md").exists()
    assert (output_dir / "validation-checklist.md").exists()
    assert (output_dir / "manual-steps.md").exists()
    assert (output_dir / "runtime-dependencies.md").exists()
    assert (output_dir / "security-summary.md").exists()
    assert (output_dir / "v1-readiness.md").exists()
    assert (output_dir / "final-report-outline.md").exists()


def test_cli_capstone_render_disabled_is_clean(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-capstone"
    _write_capstone_config(config_path, enabled=False)

    result = runner.invoke(
        app,
        ["capstone", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "Capstone readiness is disabled" in result.output
    assert not output_dir.exists()


def test_cli_capstone_render_refuses_overwrite_without_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-capstone"
    _write_capstone_config(config_path)
    output_dir.mkdir()
    (output_dir / "README.md").write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app,
        ["capstone", "render", str(config_path), "--output", str(output_dir)],
    )

    assert result.exit_code == 1
    assert "use --force" in result.output
    assert (output_dir / "README.md").read_text(encoding="utf-8") == "existing"


def test_cli_capstone_render_overwrites_with_force(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    output_dir = tmp_path / "generated-capstone"
    _write_capstone_config(config_path)
    output_dir.mkdir()
    (output_dir / "README.md").write_text("existing", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "capstone",
            "render",
            str(config_path),
            "--output",
            str(output_dir),
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "Capstone Readiness" in (output_dir / "README.md").read_text(
        encoding="utf-8"
    )
