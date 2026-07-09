"""Studio pipeline guardrails."""

from __future__ import annotations

from pathlib import Path

from k8s_forge.studio.schemas import StudioState

CRITICAL_BLOCKER_KEYWORDS = (
    "windows",
    "win32",
    "pywin32",
    "pythoncom",
    "com",
    "outlook",
    "desktop",
    "gui",
)

NON_BLOCKER_PREFIXES = (
    "recommended action",
    "kubernetes impact",
)

NON_BLOCKER_FRAGMENTS = ("a generated yaml file is only",)


def detect_critical_blockers(text: str) -> list[str]:
    """Detect critical blockers from discovery warnings text."""
    blockers: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip(" -|#")
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered.startswith(NON_BLOCKER_PREFIXES):
            continue
        if any(fragment in lowered for fragment in NON_BLOCKER_FRAGMENTS):
            continue
        if any(keyword in lowered for keyword in CRITICAL_BLOCKER_KEYWORDS):
            blockers.append(cleaned)
    return blockers


def update_blockers_from_file(state: StudioState, warnings_path: Path) -> StudioState:
    """Update state blockers from a warnings file."""
    if warnings_path.exists():
        state.critical_blockers = detect_critical_blockers(
            warnings_path.read_text(encoding="utf-8")
        )
    return state


def can_deploy(state: StudioState, manifests_dir: Path) -> tuple[bool, str]:
    """Return whether real deploy is allowed by Studio guardrails."""
    if not state.dry_run_ok:
        return False, "dry-run must succeed before deploy"
    if not state.app_yaml_path:
        return False, "app.yaml is required before deploy"
    if not state.docker_build_ok:
        return False, "Docker image must be built before deploy"
    if not state.kind_load_ok:
        return False, "Docker image must be loaded into Kind before deploy"
    if state.deploy_status == "running":
        return False, "deploy is already running"
    if state.critical_blockers:
        return False, "critical discovery blockers require review-only mode"
    if not manifests_dir.exists():
        return False, "rendered manifests are missing"
    return True, "deploy allowed after explicit confirmation"
