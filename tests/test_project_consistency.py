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
