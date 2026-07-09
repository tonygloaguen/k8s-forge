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


class KindRunner(FakeRunner):
    def __init__(
        self,
        jobs: StudioJobManager,
        clusters: list[str] | None = None,
        fail_load: bool = False,
    ) -> None:
        super().__init__(jobs)
        self.clusters = clusters or []
        self.fail_load = fail_load

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
        if command == ["kind", "get", "clusters"]:
            for cluster in self.clusters:
                await self.jobs.append_log(job, "stdout", cluster)
            await self.jobs.mark_finished(job, "succeeded", 0)
        elif command[0:3] == ["kind", "load", "docker-image"] and self.fail_load:
            await self.jobs.append_log(
                job, "stderr", 'ERROR: no nodes found for cluster "kind"'
            )
            await self.jobs.mark_finished(job, "failed", 1)
        else:
            await self.jobs.append_log(job, "stdout", "fake command completed")
            await self.jobs.mark_finished(job, "succeeded", 0)
        return job


class DeployRunner(FakeRunner):
    def __init__(
        self,
        jobs: StudioJobManager,
        *,
        existing_job: bool = False,
        immutable_apply: bool = False,
    ) -> None:
        super().__init__(jobs)
        self.existing_job = existing_job
        self.immutable_apply = immutable_apply

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
        if command[0:3] == ["kubectl", "get", "job"]:
            if self.existing_job:
                await self.jobs.append_log(job, "stdout", "job.batch/network-mapper")
                await self.jobs.mark_finished(job, "succeeded", 0)
            else:
                await self.jobs.append_log(
                    job, "stderr", "Error from server (NotFound)"
                )
                await self.jobs.mark_finished(job, "failed", 1)
        elif command[0:2] == ["kubectl", "apply"] and self.immutable_apply:
            await self.jobs.append_log(
                job,
                "stderr",
                (
                    'The Job "network-mapper" is invalid: '
                    "spec.template: field is immutable"
                ),
            )
            await self.jobs.mark_finished(job, "failed", 1)
        elif command[0:2] == ["kubectl", "logs"]:
            await self.jobs.append_log(job, "stdout", "line one")
            await self.jobs.append_log(job, "stdout", "line two")
            await self.jobs.mark_finished(job, "succeeded", 0)
        else:
            await self.jobs.append_log(job, "stdout", "fake command completed")
            await self.jobs.mark_finished(job, "succeeded", 0)
        return job


def prepare_deployable_config(client: TestClient, app: object, workload: str) -> Path:
    payload: dict[str, object] = {
        "app_name": "network-mapper",
        "namespace": "network-mapper",
        "image": "network-mapper:dev",
        "workload_type": workload,
        "startup_command": "python -m network_mapper",
        "service_enabled": False,
        "restart_policy": "OnFailure",
    }
    if workload == "deployment":
        payload.update(
            {
                "container_port": 8000,
                "service_enabled": True,
                "restart_policy": "Always",
            }
        )
    response = client.post("/api/scaffold/app-yaml", json=payload)
    assert response.status_code == 200
    runtime = app.state.runtime
    generated_k8s = runtime.workspace.output_dir("generated-k8s")
    generated_k8s.mkdir(parents=True, exist_ok=True)
    state = runtime.workspace.load_state()
    state.generated_k8s_dir = str(generated_k8s)
    state.dry_run_ok = True
    state.docker_build_ok = True
    state.kind_load_ok = True
    state.state = "dry_run_ok"
    runtime.workspace.save_state(state)
    return generated_k8s


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


def test_studio_state_guides_scaffold_required(tmp_path: Path) -> None:
    repo = tmp_path / "python-tool"
    write(repo / "requirements.txt", "requests\n")
    write(repo / "python_tool" / "__init__.py", "")
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    app = create_app(tmp_path / "studio", runner=FakeRunner(jobs), jobs=jobs)
    client = TestClient(app)

    assert client.post("/api/repo/local", json={"path": str(repo)}).status_code == 200
    state = app.state.runtime.workspace.load_state()
    state.needs_scaffold = True
    state.app_yaml_path = ""
    state.state = "scaffold_required"
    app.state.runtime.workspace.save_state(state)

    response = client.get("/api/state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"]["needs_scaffold"] is True
    assert payload["current_state"] == (
        "Assisted scaffold required: no app.yaml was generated."
    )
    assert payload["next_action"] == "Create an assisted scaffold, then run Check."


def test_studio_scaffold_defaults_from_repo_path(tmp_path: Path) -> None:
    repo = tmp_path / "python-tool"
    write(repo / "requirements.txt", "requests\n")
    write(repo / "python_tool" / "__init__.py", "")
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    app = create_app(tmp_path / "studio", runner=FakeRunner(jobs), jobs=jobs)
    client = TestClient(app)

    assert client.post("/api/repo/local", json={"path": str(repo)}).status_code == 200
    state = app.state.runtime.workspace.load_state()
    state.needs_scaffold = True
    state.state = "scaffold_required"
    app.state.runtime.workspace.save_state(state)

    response = client.get("/api/scaffold/defaults")

    assert response.status_code == 200
    defaults = response.json()
    assert defaults["app_name"] == "python-tool"
    assert defaults["namespace"] == "python-tool"
    assert defaults["image"] == "python-tool:dev"
    assert defaults["workload_type"] == "job"
    assert defaults["startup_command"] == "python -m python_tool --help"
    assert defaults["service_enabled"] is False
    assert defaults["ingress_enabled"] is False
    assert defaults["restart_policy"] == "OnFailure"


def test_studio_existing_dockerfile_is_reported_and_protected(tmp_path: Path) -> None:
    repo = tmp_path / "cli-repo"
    write(repo / "Dockerfile", "FROM python:3.12-slim\n")
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    app = create_app(tmp_path / "studio", runner=FakeRunner(jobs), jobs=jobs)
    client = TestClient(app)

    assert client.post("/api/repo/local", json={"path": str(repo)}).status_code == 200
    state_response = client.get("/api/state")
    assert state_response.status_code == 200
    dockerfile_state = state_response.json()["dockerfile"]
    assert dockerfile_state["exists"] is True
    assert dockerfile_state["path"].endswith("Dockerfile")

    response = client.post(
        "/api/dockerfile/write",
        json={"confirm": True, "overwrite": True, "content": "FROM scratch\n"},
    )

    assert response.status_code == 400
    assert "strong confirmation" in response.json()["error"]
    assert (repo / "Dockerfile").read_text(encoding="utf-8") == (
        "FROM python:3.12-slim\n"
    )


def test_studio_check_without_app_yaml_returns_next_action(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    app = create_app(tmp_path / "studio", runner=FakeRunner(jobs), jobs=jobs)
    client = TestClient(app)

    response = client.post("/api/check")

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "app.yaml is not available yet."
    assert payload["next_action"] == "Create an assisted scaffold, then run Check."


def test_studio_websocket_sends_connected_event(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    app = create_app(tmp_path / "studio", runner=FakeRunner(jobs), jobs=jobs)

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/jobs") as websocket,
    ):
        event = websocket.receive_json()

    assert event == {
        "type": "connected",
        "message": "Studio job stream connected",
    }


def test_studio_state_exposes_output_paths(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    app = create_app(tmp_path / "studio", runner=FakeRunner(jobs), jobs=jobs)
    client = TestClient(app)

    response = client.get("/api/state")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert paths["studio_output_dir"].endswith("outputs")
    assert paths["generated_discovery_dir"].endswith("outputs/generated-discovery")
    assert paths["generated_k8s_dir"].endswith("outputs/generated-k8s")


def test_studio_render_response_contains_output_dir(tmp_path: Path) -> None:
    repo = create_fastapi_repo(tmp_path)
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    app = create_app(tmp_path / "studio", runner=FakeRunner(jobs), jobs=jobs)
    client = TestClient(app)

    assert client.post("/api/repo/local", json={"path": str(repo)}).status_code == 200
    assert client.post("/api/discover").status_code == 200
    response = client.post("/api/render")

    assert response.status_code == 200
    assert response.json()["output_dir"].endswith("outputs/generated-k8s")


def test_studio_kind_clusters_prefers_devsecops(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = KindRunner(jobs, clusters=["kind", "devsecops"])
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)

    response = client.get("/api/kind/clusters")

    assert response.status_code == 200
    payload = response.json()
    assert payload["clusters"] == ["kind", "devsecops"]
    assert payload["preferred"] == "devsecops"


def test_studio_kind_load_uses_named_cluster(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = KindRunner(jobs, clusters=["devsecops"])
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)

    response = client.post(
        "/api/kind/load", json={"image": "network-mapper:dev", "cluster": "devsecops"}
    )

    assert response.status_code == 200
    assert response.json()["cluster"] == "devsecops"
    assert runner.commands[-1] == [
        "kind",
        "load",
        "docker-image",
        "network-mapper:dev",
        "--name",
        "devsecops",
    ]


def test_studio_kind_load_failure_reports_no_nodes_reason(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = KindRunner(jobs, fail_load=True)
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)

    response = client.post(
        "/api/kind/load", json={"image": "network-mapper:dev", "cluster": "kind"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["status"] == "failed"
    assert payload["cluster"] == "kind"
    assert payload["reason"] == 'ERROR: no nodes found for cluster "kind"'


def test_studio_job_deploy_blocks_when_job_exists(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = DeployRunner(jobs, existing_job=True)
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)
    prepare_deployable_config(client, app, "job")

    response = client.post("/api/deploy", json={"confirm": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["deploy_status"] == "blocked_existing_job"
    assert payload["job_exists"] is True
    assert payload["job_name"] == "network-mapper"
    assert payload["namespace"] == "network-mapper"
    assert payload["reason"] == "Kubernetes Job spec.template is immutable"
    assert runner.commands == [
        ["kubectl", "get", "job", "network-mapper", "-n", "network-mapper"]
    ]


def test_studio_delete_existing_job_and_redeploy_requires_confirmation(
    tmp_path: Path,
) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = DeployRunner(jobs, existing_job=True)
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)
    prepare_deployable_config(client, app, "job")

    response = client.post("/api/deploy/job/redeploy", json={"confirmation": "wrong"})

    assert response.status_code == 400
    assert not runner.commands


def test_studio_delete_existing_job_and_redeploy_runs_delete_then_apply(
    tmp_path: Path,
) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = DeployRunner(jobs, existing_job=True)
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)
    generated_k8s = prepare_deployable_config(client, app, "job")

    response = client.post(
        "/api/deploy/job/redeploy",
        json={"confirmation": "DELETE JOB AND REDEPLOY"},
    )

    assert response.status_code == 200
    assert response.json()["job"]["status"] == "succeeded"
    assert response.json()["deploy_status"] == "succeeded"
    assert runner.commands == [
        [
            "kubectl",
            "delete",
            "job",
            "network-mapper",
            "-n",
            "network-mapper",
            "--ignore-not-found",
        ],
        ["kubectl", "apply", "-f", str(generated_k8s)],
    ]


def test_studio_job_immutable_apply_failure_gets_clear_reason(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = DeployRunner(jobs, existing_job=False, immutable_apply=True)
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)
    prepare_deployable_config(client, app, "job")

    response = client.post("/api/deploy", json={"confirm": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["status"] == "failed"
    assert payload["deploy_status"] == "blocked_existing_job"
    assert payload["reason"] == "Existing Kubernetes Job cannot be updated in place."
    assert payload["state"]["deploy_blocked_next_action"] == (
        "Delete existing Job and redeploy, or delete the Job manually."
    )


def test_studio_deployment_deploy_uses_apply_directly(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = DeployRunner(jobs)
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)
    generated_k8s = prepare_deployable_config(client, app, "deployment")

    response = client.post("/api/deploy", json={"confirm": True})

    assert response.status_code == 200
    assert response.json()["job"]["status"] == "succeeded"
    assert response.json()["deploy_status"] == "succeeded"
    assert runner.commands == [["kubectl", "apply", "-f", str(generated_k8s)]]


def test_studio_delete_existing_job_and_redeploy_bad_confirmation_message(
    tmp_path: Path,
) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = DeployRunner(jobs, existing_job=True)
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)
    prepare_deployable_config(client, app, "job")

    response = client.post(
        "/api/deploy/job/redeploy", json={"confirmation": "network-mapper"}
    )

    assert response.status_code == 400
    assert (
        response.json()["error"]
        == "Confirmation text did not match. No Job was deleted."
    )
    assert not runner.commands


def test_studio_redeploy_success_clears_blocked_state(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = DeployRunner(jobs, existing_job=True)
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)
    prepare_deployable_config(client, app, "job")

    blocked = client.post("/api/deploy", json={"confirm": True})
    assert blocked.json()["deploy_status"] == "blocked_existing_job"
    response = client.post(
        "/api/deploy/job/redeploy",
        json={"confirmation": "DELETE JOB AND REDEPLOY"},
    )

    assert response.status_code == 200
    state = response.json()["state"]
    assert state["deploy_status"] == "succeeded"
    assert state["deploy_blocked_reason"] == ""
    assert state["deploy_blocked_next_action"] == ""


def test_studio_logs_require_successful_deploy(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    app = create_app(tmp_path / "studio", runner=DeployRunner(jobs), jobs=jobs)
    client = TestClient(app)
    prepare_deployable_config(client, app, "job")

    response = client.post("/api/logs")

    assert response.status_code == 400
    assert "Deploy must succeed" in response.json()["error"]


def test_studio_job_logs_use_controlled_job_command(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = DeployRunner(jobs)
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)
    prepare_deployable_config(client, app, "job")
    assert client.post("/api/deploy", json={"confirm": True}).status_code == 200

    response = client.post("/api/logs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["status"] == "succeeded"
    assert payload["workload_type"] == "job"
    assert payload["command"] == "kubectl logs -n network-mapper job/network-mapper"
    assert payload["logs"] == "line one\nline two"
    assert payload["state"]["logs_ok"] is True
    assert runner.commands[-1] == [
        "kubectl",
        "logs",
        "-n",
        "network-mapper",
        "job/network-mapper",
    ]


def test_studio_deployment_logs_use_label_selector(tmp_path: Path) -> None:
    jobs = StudioJobManager(tmp_path / "studio" / "jobs")
    runner = DeployRunner(jobs)
    app = create_app(tmp_path / "studio", runner=runner, jobs=jobs)
    client = TestClient(app)
    prepare_deployable_config(client, app, "deployment")
    assert client.post("/api/deploy", json={"confirm": True}).status_code == 200

    response = client.post("/api/logs")

    assert response.status_code == 200
    assert response.json()["workload_type"] == "deployment"
    assert runner.commands[-1] == [
        "kubectl",
        "logs",
        "-n",
        "network-mapper",
        "-l",
        "app=network-mapper",
        "--tail=200",
    ]
