from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="studio extra dependencies are not installed")
try:
    from fastapi.testclient import TestClient  # noqa: E402
except RuntimeError as exc:
    pytest.skip(str(exc), allow_module_level=True)

from k8s_forge.studio.jobs import StudioJobManager  # noqa: E402
from k8s_forge.studio.routes import create_app  # noqa: E402
from k8s_forge.studio.schemas import StudioJob  # noqa: E402


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class FakeRunner:
    def __init__(self, jobs: StudioJobManager) -> None:
        self.jobs = jobs
        self.commands: list[list[str]] = []

    async def run(
        self,
        job_type: str,
        command: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: int = 300,
    ) -> StudioJob:
        self.commands.append(command)
        job = self.jobs.create_job(job_type, command, cwd, env=env)
        await self.jobs.mark_started(job)
        await self.jobs.append_log(job, "stdout", "fake command completed")
        await self.jobs.mark_finished(job, "succeeded", 0)
        return job


def create_fastapi_repo(root: Path) -> Path:
    repo = root / "repo"
    write(repo / "requirements.txt", "fastapi\nuvicorn\n")
    write(repo / "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    return repo


def test_studio_index_and_state(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    app = create_app(tmp_path / "studio", runner=FakeRunner(jobs), jobs=jobs)
    client = TestClient(app)

    index = client.get("/")
    state = client.get("/api/state")

    assert index.status_code == 200
    assert "k8s-forge Studio" in index.text
    assert state.status_code == 200
    assert state.json()["state"]["state"] == "empty"


def test_studio_discover_check_explain_render_flow(tmp_path: Path) -> None:
    repo = create_fastapi_repo(tmp_path)
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = FakeRunner(jobs)
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)

    assert client.post("/api/repo/local", json={"path": str(repo)}).status_code == 200
    assert client.post("/api/discover").status_code == 200
    assert "FastAPI" in client.get("/api/discovery/report").text
    assert "app:" in client.get("/api/app-yaml").text
    assert client.post("/api/check").status_code == 200
    explain = client.post("/api/explain")
    assert explain.status_code == 200
    assert "Application" in explain.json()["explain"]
    assert client.post("/api/render").status_code == 200
    dry_run = client.post("/api/dry-run")
    assert dry_run.status_code == 200
    assert runner.commands[-1][0:2] == ["kubectl", "apply"]


def test_studio_deploy_requires_confirmation(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    app = create_app(tmp_path / "studio", runner=FakeRunner(jobs), jobs=jobs)
    client = TestClient(app)

    response = client.post("/api/deploy", json={"confirm": False})

    assert response.status_code == 400
    assert "confirmation" in response.json()["error"]


def test_studio_report_only_can_create_job_scaffold(tmp_path: Path) -> None:
    repo = tmp_path / "cli-repo"
    write(repo / "worker.py", "print('work')\n")
    write(repo / "helper.py", "print('helper')\n")
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    app = create_app(tmp_path / "studio", runner=FakeRunner(jobs), jobs=jobs)
    client = TestClient(app)

    assert client.post("/api/repo/local", json={"path": str(repo)}).status_code == 200
    assert client.post("/api/discover").status_code == 200
    state = client.get("/api/state").json()["state"]
    assert state["needs_scaffold"] is True
    assert client.get("/api/app-yaml").text == ""

    response = client.post(
        "/api/scaffold/app-yaml",
        json={
            "app_name": "network-mapper",
            "namespace": "network-mapper",
            "image": "network-mapper:dev",
            "workload_type": "job",
            "startup_command": "python -m network_mapper",
            "service_enabled": False,
            "restart_policy": "OnFailure",
        },
    )

    assert response.status_code == 200
    yaml_text = client.get("/api/app-yaml").text
    assert "type: job" in yaml_text
    assert "enabled: false" in yaml_text
    assert client.post("/api/check").status_code == 200


def test_studio_dockerfile_proposal_is_not_written_without_confirmation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "cli-repo"
    repo.mkdir()
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    app = create_app(tmp_path / "studio", runner=FakeRunner(jobs), jobs=jobs)
    client = TestClient(app)

    assert client.post("/api/repo/local", json={"path": str(repo)}).status_code == 200
    proposal = client.get("/api/dockerfile/proposal")
    assert proposal.status_code == 200
    assert "python:3.12-slim" in proposal.text
    response = client.post("/api/dockerfile/write", json={"confirm": False})

    assert response.status_code == 400
    assert not (repo / "Dockerfile").exists()
