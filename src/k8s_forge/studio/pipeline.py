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


def detect_critical_blockers(text: str) -> list[str]:
    """Detect critical blockers from discovery warnings text."""
    blockers: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(keyword in lowered for keyword in CRITICAL_BLOCKER_KEYWORDS):
            cleaned = line.strip(" -|#")
            if cleaned:
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
    if state.critical_blockers:
        return False, "critical discovery blockers require review-only mode"
    if not manifests_dir.exists():
        return False, "rendered manifests are missing"
    return True, "deploy allowed after explicit confirmation"
