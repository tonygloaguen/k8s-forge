import os
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from k8s_forge.cli import app
from k8s_forge.config_loader import load_app_config

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()

TOP_LEVEL_HELP_COMMANDS = [
    [],
    ["init"],
    ["check"],
    ["render"],
    ["dry-run"],
    ["diff"],
    ["apply"],
    ["status"],
    ["discover"],
    ["explain"],
    ["studio"],
    ["doctor"],
    ["cluster"],
    ["image"],
    ["helm"],
    ["supply-chain"],
    ["ci"],
    ["gitops"],
    ["observability"],
    ["logging"],
    ["tracing"],
    ["terraform"],
    ["ansible"],
    ["security"],
    ["capstone"],
]

SPECIALIZED_RENDER_HELP_COMMANDS = [
    ["helm", "render"],
    ["supply-chain", "render"],
    ["ci", "render"],
    ["gitops", "render"],
    ["observability", "render"],
    ["logging", "render"],
    ["tracing", "render"],
    ["terraform", "render"],
    ["ansible", "render"],
    ["security", "render"],
    ["capstone", "render"],
]


@pytest.mark.parametrize("command", TOP_LEVEL_HELP_COMMANDS)
def test_cli_help_smoke(command: list[str]) -> None:
    result = runner.invoke(app, [*command, "--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output


@pytest.mark.parametrize("command", SPECIALIZED_RENDER_HELP_COMMANDS)
def test_specialized_render_help_smoke(command: list[str]) -> None:
    result = runner.invoke(app, [*command, "--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "app.yaml" in result.output


@pytest.mark.parametrize(
    "example_path",
    [ROOT / "examples" / "demo-app.yaml", ROOT / "examples" / "admin-api.yaml"],
)
def test_checked_in_examples_load(example_path: Path) -> None:
    config = load_app_config(example_path)

    assert config.app.name
    assert config.app.namespace
    assert config.workload is not None
    assert config.ingress is not None
    assert config.networkPolicy is not None
    assert config.policy is not None
    assert config.supplyChain is not None
    assert config.ci is not None
    assert config.gitops is not None
    assert config.observability is not None
    assert config.logging is not None
    assert config.tracing is not None
    assert config.terraform is not None
    assert config.ansible is not None
    assert config.security is not None
    assert config.capstone is not None


def test_pyproject_packages_all_template_directories() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["k8s_forge"]

    expected_patterns = {
        "templates/*.j2",
        "helm_templates/*.j2",
        "helm_templates/templates/*.j2",
        "supply_chain_templates/*.j2",
        "ci_templates/*.j2",
        "ci_templates/workflows/*.j2",
        "gitops_templates/*.j2",
        "gitops_templates/argocd/*.j2",
        "observability_templates/*.j2",
        "observability_templates/prometheus/*.j2",
        "observability_templates/grafana/*.j2",
        "logging_templates/*.j2",
        "logging_templates/loki/*.j2",
        "logging_templates/grafana/*.j2",
        "logging_templates/collector/*.j2",
        "tracing_templates/*.j2",
        "tracing_templates/opentelemetry/*.j2",
        "tracing_templates/tempo/*.j2",
        "tracing_templates/grafana/*.j2",
        "tracing_templates/collector/*.j2",
        "terraform_templates/*.j2",
        "ansible_templates/*.j2",
        "ansible_templates/group_vars/*.j2",
        "ansible_templates/roles/*.j2",
        "security_templates/*.j2",
        "capstone_templates/*.j2",
        "discovery_templates/*.j2",
        "studio/templates/*.html",
        "studio/static/*.js",
        "studio/static/*.css",
    }

    assert expected_patterns <= set(package_data)


@pytest.mark.parametrize(
    "path",
    [
        ROOT / "CHANGELOG.md",
        ROOT / "docs" / "release-v1.md",
        ROOT / "docs" / "release-checklist.md",
        ROOT / "docs" / "module-13-security-audit.md",
        ROOT / "docs" / "module-14-capstone.md",
        ROOT / "docs" / "module-15-repository-discovery.md",
        ROOT / "docs" / "module-16-explain.md",
        ROOT / "docs" / "module-17-studio.md",
        ROOT / "docs" / "module-18-workload-types.md",
    ],
)
def test_release_documentation_exists(path: Path) -> None:
    assert path.exists()
    assert path.read_text(encoding="utf-8").strip()


def test_release_script_is_local_and_safe() -> None:
    script = ROOT / "scripts" / "check_release.sh"
    text = script.read_text(encoding="utf-8")

    assert script.exists()
    assert os.access(script, os.X_OK)
    for forbidden in (
        "kubectl apply",
        "helm install",
        "terraform apply",
        "ansible-playbook",
    ):
        assert forbidden not in text
    for expected in (
        "ruff format --check",
        "ruff check",
        "mypy src",
        "pytest -q",
        "bandit -r src",
        "pip_audit --skip-editable",
        "build",
        "--version",
        "--help",
    ):
        assert expected in text


def test_studio_extra_includes_websocket_support() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    studio_deps = pyproject["project"]["optional-dependencies"]["studio"]
    normalized = {dependency.lower() for dependency in studio_deps}

    assert (
        any(dependency.startswith("uvicorn[standard]") for dependency in normalized)
        or any(dependency.startswith("websockets") for dependency in normalized)
        or any(dependency.startswith("wsproto") for dependency in normalized)
    )


def test_studio_frontend_has_websocket_polling_fallback() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )

    assert "Live job streaming unavailable. Falling back to polling." in app_js
    assert "new WebSocket" in app_js
    assert "setInterval" in app_js
    assert "/api/jobs" in app_js


def test_studio_frontend_shows_action_results() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    index = (
        ROOT / "src" / "k8s_forge" / "studio" / "templates" / "index.html"
    ).read_text(encoding="utf-8")

    assert "action-results" in index
    assert "[OK] Docker image built" in app_js
    assert "[OK] Image loaded into kind" in app_js
    assert "[OK] Kubernetes dry-run succeeded" in app_js
    assert "Deploy locked" in app_js


def test_studio_frontend_preserves_multiline_text() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    style = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "style.css").read_text(
        encoding="utf-8"
    )

    assert "normalizeMultiline" in app_js
    assert "textContent = normalizeMultiline" in app_js
    assert "white-space: pre-wrap" in style


def test_studio_frontend_shows_output_paths_and_kind_cluster_controls() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    index = (
        ROOT / "src" / "k8s_forge" / "studio" / "templates" / "index.html"
    ).read_text(encoding="utf-8")

    assert "Studio output paths" in index
    assert "studio-output-path" in index
    assert "generated-discovery-path" in index
    assert "generated-k8s-path" in index
    assert "copy-output-path" in index
    assert "kind-cluster" in index
    assert "refresh-kind-clusters" in index
    assert "/api/kind/clusters" in app_js
    assert "kind load" not in app_js.lower() or "--name" in app_js


def test_studio_frontend_render_result_includes_generated_k8s_dir() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )

    assert "generated_k8s_dir" in app_js
    assert "result.output_dir" in app_js


def test_studio_frontend_does_not_json_stringify_last_explain() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )

    assert "renderStateSnapshot" in app_js
    assert "[see Explain panel]" in app_js
    assert "JSON.stringify(snapshot, null, 2)" not in app_js


def test_studio_frontend_has_deployment_readiness_memo() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    index = (
        ROOT / "src" / "k8s_forge" / "studio" / "templates" / "index.html"
    ).read_text(encoding="utf-8")

    assert "Deployment readiness memo" in index
    for expected in (
        "Select repository",
        "Discover repository",
        "Choose workload type",
        "Create or review app.yaml",
        "Run Check",
        "Run Explain",
        "Render manifests",
        "Build Docker image",
        "Load image into Kind",
        "Dry-run",
        "Deploy to local lab",
        "Verify status",
        "Read logs",
    ):
        assert expected in app_js
    assert "deploy_blocked_reason" in app_js
    assert "generatedK8sDir(snapshot)" in app_js


def test_studio_frontend_has_production_handoff_checklist_copy_only() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    index = (
        ROOT / "src" / "k8s_forge" / "studio" / "templates" / "index.html"
    ).read_text(encoding="utf-8")

    assert "Production handoff checklist" in index
    assert "Studio prepares and documents production readiness." in index
    assert "It does not execute production commands automatically." in index
    assert "prod-registry" in index
    assert "prod-release-tag" in index
    assert "prod-context" in index
    assert "Copy command" in app_js
    assert "copy-command" in app_js
    assert "navigator.clipboard.writeText" in app_js
    assert "post('/api/production" not in app_js
    for expected in (
        "Push image to registry",
        "Use immutable image tag",
        "Scan image vulnerabilities",
        "Generate SBOM",
        "Check secrets handling",
        "Review RBAC",
        "Review NetworkPolicy",
        "Validate resources",
        "Validate probes",
        "Validate storage / PVC / backups",
        "Validate ingress / DNS / TLS",
        "Validate monitoring / logging",
        "Define rollback plan",
        "Confirm target Kubernetes context",
        "Human approval before production",
    ):
        assert expected in app_js


def test_studio_frontend_has_job_redeploy_action() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    index = (
        ROOT / "src" / "k8s_forge" / "studio" / "templates" / "index.html"
    ).read_text(encoding="utf-8")

    assert "Delete existing Job and redeploy" in index
    assert "DELETE JOB AND REDEPLOY" in app_js
    assert "/api/deploy/job/redeploy" in app_js
    routes = (ROOT / "src" / "k8s_forge" / "studio" / "routes.py").read_text(
        encoding="utf-8"
    )

    assert "[BLOCKED] Existing Job must be deleted before redeploy" in app_js
    assert "Existing Kubernetes Job cannot be updated in place." in routes


def test_studio_frontend_tracks_action_statuses_and_prevents_duplicates() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )

    assert "activeActions = new Set()" in app_js
    assert "duplicate click ignored" in app_js
    assert "data-result-key" in app_js
    assert "actionResultKey(path)" in app_js
    assert "setActionRunning(path, true)" in app_js
    assert "setActionRunning(path, false)" in app_js


def test_studio_frontend_uses_deploy_status_for_job_blocks() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    routes = (ROOT / "src" / "k8s_forge" / "studio" / "routes.py").read_text(
        encoding="utf-8"
    )

    assert '"deploy_status": "blocked_existing_job"' in routes
    assert '"job_exists": True' in routes
    assert "result.deploy_status === 'blocked_existing_job'" in app_js
    assert "[BLOCKED] Existing Job must be deleted before redeploy" in app_js
    assert "[CANCELLED] Delete existing Job and redeploy cancelled" in app_js
    assert "[RUNNING] Deleting existing Job" in app_js
    assert "[RUNNING] Applying manifests" in app_js


def test_studio_frontend_memo_uses_real_action_statuses() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )

    assert "state.docker_build_ok ? 'done'" in app_js
    assert "state.kind_load_ok ? 'done'" in app_js
    assert "state.deploy_status === 'blocked_existing_job'" in app_js
    assert "state.deploy_status === 'succeeded' ? 'done'" in app_js
    assert "state.status_ok ? 'done'" in app_js
    assert "showJobRedeploy" in app_js
    assert "workloadType(snapshot) === 'job'" in app_js


def test_studio_frontend_job_redeploy_confirmation_and_cleanup() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )

    assert "Type exactly:" in app_js
    assert "DELETE JOB AND REDEPLOY" in app_js
    assert "Confirmation text did not match. No Job was deleted." in app_js
    assert "expected confirmation: DELETE JOB AND REDEPLOY" in app_js
    assert "[DONE] Existing Job deleted" in app_js
    assert "[DONE] Manifests applied" in app_js
    assert "result.deploy_status === 'succeeded' ? 'deploy' : key" in app_js


def test_studio_frontend_logs_panel_and_actions() -> None:
    app_js = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    index = (
        ROOT / "src" / "k8s_forge" / "studio" / "templates" / "index.html"
    ).read_text(encoding="utf-8")
    style = (ROOT / "src" / "k8s_forge" / "studio" / "static" / "style.css").read_text(
        encoding="utf-8"
    )

    assert 'id="read-logs"' in index
    assert 'id="refresh-logs"' in index
    assert '<pre id="logs-output">' in index
    assert "/api/logs" in app_js
    assert "[OK] Logs loaded" in app_js
    assert "[FAILED] Logs failed" in app_js
    assert "state.logs_ok ? 'done'" in app_js
    assert "normalizeMultiline(result.logs" in app_js
    assert "#logs-output" in style
    assert "white-space: pre-wrap" in style
