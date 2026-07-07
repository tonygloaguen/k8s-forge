from pathlib import Path

from k8s_forge.studio.pipeline import can_deploy, detect_critical_blockers
from k8s_forge.studio.schemas import StudioState


def test_detect_critical_blockers_windows_desktop() -> None:
    blockers = detect_critical_blockers("- Windows COM dependency\n- normal warning")

    assert blockers == ["Windows COM dependency"]


def test_deploy_requires_dry_run(tmp_path: Path) -> None:
    allowed, reason = can_deploy(StudioState(dry_run_ok=False), tmp_path)

    assert allowed is False
    assert "dry-run" in reason


def test_deploy_rejects_critical_blocker(tmp_path: Path) -> None:
    manifests = tmp_path / "generated-k8s"
    manifests.mkdir()
    state = StudioState(dry_run_ok=True, critical_blockers=["Windows COM"])

    allowed, reason = can_deploy(state, manifests)

    assert allowed is False
    assert "blockers" in reason


def test_deploy_allowed_after_dry_run_without_blockers(tmp_path: Path) -> None:
    manifests = tmp_path / "generated-k8s"
    manifests.mkdir()
    state = StudioState(dry_run_ok=True)

    allowed, reason = can_deploy(state, manifests)

    assert allowed is True
    assert "allowed" in reason
