from pathlib import Path

import pytest

from k8s_forge.studio.schemas import StudioState
from k8s_forge.studio.workspace import WorkspaceError, WorkspaceManager, sanitize_name


def test_workspace_prepare_creates_layout(tmp_path: Path) -> None:
    workspace = WorkspaceManager(tmp_path / "studio")
    workspace.prepare()

    assert workspace.repos_dir.exists()
    assert workspace.jobs_dir.exists()
    assert workspace.logs_dir.exists()
    assert workspace.outputs_dir.exists()
    assert workspace.state_path.exists()


def test_workspace_rejects_path_traversal(tmp_path: Path) -> None:
    workspace = WorkspaceManager(tmp_path / "studio")
    workspace.prepare()

    with pytest.raises(WorkspaceError):
        workspace.ensure_inside(tmp_path / "outside")


def test_workspace_sanitizes_repo_names(tmp_path: Path) -> None:
    workspace = WorkspaceManager(tmp_path / "studio")
    workspace.prepare()

    assert sanitize_name("../Demo Repo.git") == "demo-repo"
    assert workspace.repo_dir("../Demo Repo.git").parent == workspace.repos_dir


def test_workspace_persists_state(tmp_path: Path) -> None:
    workspace = WorkspaceManager(tmp_path / "studio")
    workspace.prepare()
    state = StudioState(state="repo_ready", repo_path="/tmp/repo")

    workspace.save_state(state)

    loaded = workspace.load_state()
    assert loaded.state == "repo_ready"
    assert loaded.repo_path == "/tmp/repo"
