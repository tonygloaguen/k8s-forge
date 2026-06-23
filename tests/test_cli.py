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
        "helm",
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
