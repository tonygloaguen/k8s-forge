"""Studio workspace management."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from k8s_forge.studio.schemas import StudioState

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_.-]+")


class WorkspaceError(ValueError):
    """Raised when a Studio workspace path is unsafe."""


def sanitize_name(value: str) -> str:
    """Return a safe filesystem name."""
    name = value.strip().replace("\\", "/").rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    name = _SAFE_NAME.sub("-", name).strip(".-_")
    if not name or name in {".", ".."}:
        msg = f"Unsafe workspace name: {value}"
        raise WorkspaceError(msg)
    return name.lower()


def repo_name_from_url(url: str) -> str:
    """Derive a safe repo name from a Git URL."""
    parsed = urlparse(url)
    candidate = parsed.path or url
    return sanitize_name(candidate)


class WorkspaceManager:
    """Manage Studio workspace directories and state."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.repos_dir = self.root / "repos"
        self.jobs_dir = self.root / "jobs"
        self.logs_dir = self.root / "logs"
        self.outputs_dir = self.root / "outputs"
        self.state_path = self.root / "state.json"

    def prepare(self) -> None:
        """Create the Studio directory layout."""
        for path in (
            self.root,
            self.repos_dir,
            self.jobs_dir,
            self.logs_dir,
            self.outputs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self.save_state(StudioState())

    def ensure_inside(self, path: Path) -> Path:
        """Resolve a path and require it to stay inside the workspace."""
        resolved = path.expanduser().resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            msg = f"Path escapes Studio workspace: {path}"
            raise WorkspaceError(msg) from exc
        return resolved

    def repo_dir(self, name: str) -> Path:
        """Return a safe repository directory under the workspace."""
        return self.ensure_inside(self.repos_dir / sanitize_name(name))

    def repo_dir_from_url(self, url: str) -> Path:
        """Return the clone destination for a Git URL."""
        return self.repo_dir(repo_name_from_url(url))

    def output_dir(self, name: str) -> Path:
        """Return a safe output directory under the workspace."""
        return self.ensure_inside(self.outputs_dir / sanitize_name(name))

    def job_log_path(self, job_id: str) -> Path:
        """Return the combined log path for a job."""
        return self.ensure_inside(self.jobs_dir / f"{sanitize_name(job_id)}.log")

    def load_state(self) -> StudioState:
        """Load Studio state from disk."""
        if not self.state_path.exists():
            return StudioState()
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        return StudioState(**data)

    def save_state(self, state: StudioState) -> None:
        """Persist Studio state."""
        self.state_path.write_text(
            json.dumps(asdict(state), indent=2, sort_keys=True),
            encoding="utf-8",
        )
