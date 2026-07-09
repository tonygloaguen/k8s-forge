from pathlib import Path

from k8s_forge.studio.pipeline import can_deploy, detect_critical_blockers
from k8s_forge.studio.schemas import StudioState


def test_detect_critical_blockers_windows_desktop() -> None:
    blockers = detect_critical_blockers("- Windows COM dependency\n- normal warning")

    assert blockers == ["Windows COM dependency"]


def test_detect_critical_blockers_ignores_explanatory_lines() -> None:
    blockers = detect_critical_blockers(
        "- Windows COM dependency\n"
        "- Recommended action: split Windows worker from Kubernetes app\n"
        "- Kubernetes impact: deploy in review-only mode\n"
        "- A generated YAML file is only a starter configuration\n"
    )

    assert blockers == ["Windows COM dependency"]


def test_deploy_requires_dry_run(tmp_path: Path) -> None:
    allowed, reason = can_deploy(StudioState(dry_run_ok=False), tmp_path)

    assert allowed is False
    assert "dry-run" in reason


def test_deploy_rejects_critical_blocker(tmp_path: Path) -> None:
    manifests = tmp_path / "generated-k8s"
    manifests.mkdir()
    state = StudioState(
        app_yaml_path="app.yaml",
        dry_run_ok=True,
        docker_build_ok=True,
        kind_load_ok=True,
        critical_blockers=["Windows COM"],
    )

    allowed, reason = can_deploy(state, manifests)

    assert allowed is False
    assert "blockers" in reason


def test_deploy_requires_docker_build(tmp_path: Path) -> None:
    manifests = tmp_path / "generated-k8s"
    manifests.mkdir()
    state = StudioState(app_yaml_path="app.yaml", dry_run_ok=True)

    allowed, reason = can_deploy(state, manifests)

    assert allowed is False
    assert "Docker image" in reason


def test_deploy_requires_kind_load(tmp_path: Path) -> None:
    manifests = tmp_path / "generated-k8s"
    manifests.mkdir()
    state = StudioState(
        app_yaml_path="app.yaml",
        dry_run_ok=True,
        docker_build_ok=True,
    )

    allowed, reason = can_deploy(state, manifests)

    assert allowed is False
    assert "Kind" in reason


def test_deploy_allowed_after_dry_run_without_blockers(tmp_path: Path) -> None:
    manifests = tmp_path / "generated-k8s"
    manifests.mkdir()
    state = StudioState(
        app_yaml_path="app.yaml",
        dry_run_ok=True,
        docker_build_ok=True,
        kind_load_ok=True,
    )

    allowed, reason = can_deploy(state, manifests)

    assert allowed is True
    assert "allowed" in reason
