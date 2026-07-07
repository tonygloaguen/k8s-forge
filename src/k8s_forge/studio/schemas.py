"""Typed Studio schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
PipelineState = Literal[
    "empty",
    "repo_selected",
    "repo_ready",
    "discovered",
    "scaffold_required",
    "yaml_reviewed",
    "checked",
    "explained",
    "manifests_rendered",
    "dry_run_ok",
    "deploy_confirmed",
    "deployed",
    "verified",
]


@dataclass
class StudioJob:
    """A tracked Studio job."""

    id: str
    type: str
    status: JobStatus
    command: list[str]
    cwd: Path
    env: dict[str, str]
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None
    log_path: Path
    cancellable: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable job representation."""
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "command": self.command,
            "cwd": str(self.cwd),
            "env": self.env,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "exit_code": self.exit_code,
            "log_path": str(self.log_path),
            "cancellable": self.cancellable,
        }


@dataclass
class StudioState:
    """Persistent Studio pipeline state."""

    state: PipelineState = "empty"
    repo_path: str = ""
    discovery_dir: str = ""
    app_yaml_path: str = ""
    generated_k8s_dir: str = ""
    dry_run_ok: bool = False
    critical_blockers: list[str] = field(default_factory=list)
    last_explain: str = ""
    needs_scaffold: bool = False
    dockerfile_proposal: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return JSON-serializable state."""
        return {
            "state": self.state,
            "repo_path": self.repo_path,
            "discovery_dir": self.discovery_dir,
            "app_yaml_path": self.app_yaml_path,
            "generated_k8s_dir": self.generated_k8s_dir,
            "dry_run_ok": self.dry_run_ok,
            "critical_blockers": self.critical_blockers,
            "last_explain": self.last_explain,
            "needs_scaffold": self.needs_scaffold,
            "dockerfile_proposal": self.dockerfile_proposal,
        }
