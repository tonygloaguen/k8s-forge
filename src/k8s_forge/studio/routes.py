# mypy: disable-error-code="import-not-found,untyped-decorator,valid-type,attr-defined"
"""FastAPI routes for Studio."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from k8s_forge.config_loader import load_app_config
from k8s_forge.discovery import discover_repository
from k8s_forge.discovery_renderer import render_discovery_files
from k8s_forge.exceptions import ConfigLoadError, RenderError
from k8s_forge.explain import build_explanation
from k8s_forge.explain_renderer import render_explanation
from k8s_forge.renderer import render_manifests
from k8s_forge.studio.command_runner import CommandRunner
from k8s_forge.studio.jobs import StudioJobManager
from k8s_forge.studio.pipeline import can_deploy, update_blockers_from_file
from k8s_forge.studio.scaffold import (
    AssistedScaffoldRequest,
    RestartPolicy,
    ScaffoldValidationError,
    WorkloadType,
    build_assisted_app_yaml,
    build_dockerfile_proposal,
)
from k8s_forge.studio.schemas import StudioState
from k8s_forge.studio.server import StudioDependencyError
from k8s_forge.studio.workspace import WorkspaceManager


@dataclass
class StudioRuntime:
    """Runtime objects shared by Studio routes."""

    workspace: WorkspaceManager
    jobs: StudioJobManager
    runner: CommandRunner


class StudioRouteError(ValueError):
    """Raised for route-level workflow errors."""


def _load_fastapi() -> tuple[Any, ...]:
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        msg = (
            "Studio dependencies are missing. Install with "
            'pip install -e ".[studio]" or pip install -e ".[dev,studio]".'
        )
        raise StudioDependencyError(msg) from exc
    return (
        FastAPI,
        WebSocket,
        WebSocketDisconnect,
        HTMLResponse,
        JSONResponse,
        PlainTextResponse,
        StaticFiles,
    )


def _json_error(message: str, status_code: int = 400) -> Any:
    _, _, _, _, JSONResponse, _, _ = _load_fastapi()
    return JSONResponse({"error": message}, status_code=status_code)


async def _internal_job(
    runtime: StudioRuntime, job_type: str, command: list[str], action: Any
) -> tuple[Any, dict[str, object]]:
    job = runtime.jobs.create_job(
        job_type, command, runtime.workspace.root, cancellable=False
    )
    await runtime.jobs.mark_started(job)
    try:
        result = action()
    except Exception as exc:  # noqa: BLE001 - surfaced as Studio job output
        await runtime.jobs.append_log(job, "stderr", str(exc))
        await runtime.jobs.mark_finished(job, "failed", 1)
        raise
    await runtime.jobs.append_log(job, "stdout", f"{job_type} completed")
    await runtime.jobs.mark_finished(job, "succeeded", 0)
    return result, job.to_dict()


def _repo_required(state: StudioState) -> Path:
    if not state.repo_path:
        raise StudioRouteError("Repository is not selected.")
    repo_path = Path(state.repo_path)
    if not repo_path.exists() or not repo_path.is_dir():
        raise StudioRouteError("Repository path is not a directory.")
    return repo_path


def _app_yaml_required(state: StudioState) -> Path:
    if not state.app_yaml_path:
        raise StudioRouteError("app.yaml is not available yet.")
    app_yaml = Path(state.app_yaml_path)
    if not app_yaml.exists():
        raise StudioRouteError("app.yaml does not exist.")
    return app_yaml


def _payload_workload_type(payload: dict[str, object]) -> WorkloadType:
    value = str(payload.get("workload_type", "deployment"))
    if value not in {"deployment", "worker", "job", "cronjob"}:
        raise ScaffoldValidationError("Invalid workload type.")
    return cast(WorkloadType, value)


def _payload_restart_policy(payload: dict[str, object]) -> RestartPolicy:
    value = str(payload.get("restart_policy", "Always"))
    if value not in {"Always", "Never", "OnFailure"}:
        raise ScaffoldValidationError("Invalid restartPolicy.")
    return cast(RestartPolicy, value)


def _payload_optional_int(payload: dict[str, object], key: str) -> int | None:
    value = payload.get(key)
    if value in {None, ""}:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise ScaffoldValidationError(f"{key} must be an integer.")


def create_app(
    workspace_root: Path,
    runner: CommandRunner | None = None,
    jobs: StudioJobManager | None = None,
) -> Any:
    """Create the FastAPI Studio application."""
    (
        FastAPI,
        WebSocket,
        WebSocketDisconnect,
        HTMLResponse,
        JSONResponse,
        PlainTextResponse,
        StaticFiles,
    ) = _load_fastapi()
    app = FastAPI(title="k8s-forge Studio")
    workspace = WorkspaceManager(workspace_root)
    workspace.prepare()
    job_manager = jobs or StudioJobManager(workspace.jobs_dir)
    command_runner = runner or CommandRunner(job_manager)
    runtime = StudioRuntime(workspace, job_manager, command_runner)
    app.state.runtime = runtime

    package_dir = Path(__file__).resolve().parent
    app.mount(
        "/static",
        StaticFiles(directory=package_dir / "static"),
        name="studio-static",
    )

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return (package_dir / "templates" / "index.html").read_text(encoding="utf-8")

    @app.get("/api/state")
    async def api_state() -> dict[str, object]:
        state = runtime.workspace.load_state()
        deploy_allowed, deploy_reason = can_deploy(
            state, Path(state.generated_k8s_dir or runtime.workspace.outputs_dir)
        )
        return {
            "state": state.to_dict(),
            "deploy_allowed": deploy_allowed,
            "deploy_reason": deploy_reason,
            "jobs": [job.to_dict() for job in runtime.jobs.list_jobs()],
        }

    @app.post("/api/repo/local")
    async def repo_local(payload: dict[str, str]) -> Any:
        repo_path = Path(payload.get("path", "")).expanduser().resolve()
        if not repo_path.exists() or not repo_path.is_dir():
            return _json_error("Repository path is not a directory.")
        state = runtime.workspace.load_state()
        state.repo_path = str(repo_path)
        state.state = "repo_ready"
        runtime.workspace.save_state(state)
        return {"repo_path": str(repo_path), "state": state.to_dict()}

    @app.post("/api/repo/clone")
    async def repo_clone(payload: dict[str, str]) -> Any:
        url = payload.get("url", "").strip()
        if not url:
            return _json_error("Git URL is required.")
        destination = runtime.workspace.repo_dir_from_url(url)
        if destination.exists():
            command = ["git", "-C", str(destination), "pull", "--ff-only"]
        else:
            command = ["git", "clone", url, str(destination)]
        job = await runtime.runner.run("git", command, runtime.workspace.root)
        if job.status == "succeeded":
            state = runtime.workspace.load_state()
            state.repo_path = str(destination)
            state.state = "repo_ready"
            runtime.workspace.save_state(state)
        return {"job": job.to_dict()}

    @app.post("/api/discover")
    async def api_discover() -> Any:
        state = runtime.workspace.load_state()
        try:
            repo_path = _repo_required(state)
        except StudioRouteError as exc:
            return _json_error(str(exc))
        discovery_dir = runtime.workspace.output_dir("generated-discovery")

        def action() -> list[Path]:
            result = discover_repository(repo_path)
            return render_discovery_files(result, discovery_dir, force=True)

        try:
            generated, job = await _internal_job(
                runtime, "discover", ["k8s-forge", "discover", str(repo_path)], action
            )
        except Exception as exc:  # noqa: BLE001
            return _json_error(str(exc), 500)
        state.discovery_dir = str(discovery_dir)
        app_yaml = discovery_dir / "k8s-forge-app.yaml"
        if app_yaml.exists():
            state.app_yaml_path = str(app_yaml)
            state.needs_scaffold = False
        else:
            state.app_yaml_path = ""
            state.needs_scaffold = True
        update_blockers_from_file(state, discovery_dir / "warnings.md")
        state.state = "discovered" if app_yaml.exists() else "scaffold_required"
        state.dry_run_ok = False
        runtime.workspace.save_state(state)
        return {"generated": [str(path) for path in generated], "job": job}

    @app.get("/api/scaffold/defaults")
    async def scaffold_defaults() -> dict[str, object]:
        state = runtime.workspace.load_state()
        repo_name = "discovered-app"
        if state.repo_path:
            repo_name = Path(state.repo_path).name.replace("_", "-").lower()
        return {
            "app_name": repo_name,
            "namespace": repo_name,
            "image": f"{repo_name}:dev",
            "workload_type": "job" if state.needs_scaffold else "deployment",
            "startup_command": "",
            "container_port": None,
            "service_enabled": False,
            "restart_policy": "OnFailure",
            "schedule": "",
            "persistence_required": False,
            "message": (
                "No app.yaml was generated. The repository does not expose enough "
                "reliable web deployment signals. Choose how to continue."
            ),
        }

    @app.post("/api/scaffold/app-yaml")
    async def scaffold_app_yaml(payload: dict[str, object]) -> Any:
        state = runtime.workspace.load_state()
        discovery_dir = (
            Path(state.discovery_dir)
            if state.discovery_dir
            else runtime.workspace.output_dir("generated-discovery")
        )
        discovery_dir.mkdir(parents=True, exist_ok=True)
        try:
            workload_type = _payload_workload_type(payload)
            restart_policy = _payload_restart_policy(payload)
            container_port = _payload_optional_int(payload, "container_port")
            request = AssistedScaffoldRequest(
                app_name=str(payload.get("app_name", "")).strip(),
                namespace=str(payload.get("namespace", "")).strip(),
                image=str(payload.get("image", "")).strip(),
                workload_type=workload_type,
                startup_command=str(payload.get("startup_command", "")).strip(),
                container_port=container_port,
                service_enabled=bool(payload.get("service_enabled", False)),
                restart_policy=restart_policy,
                schedule=str(payload.get("schedule", "")).strip(),
                persistence_required=bool(payload.get("persistence_required", False)),
            )
            yaml_text = build_assisted_app_yaml(request)
        except (ScaffoldValidationError, ValueError) as exc:
            return _json_error(str(exc))
        app_yaml = discovery_dir / "k8s-forge-app.yaml"
        app_yaml.write_text(yaml_text, encoding="utf-8")
        try:
            load_app_config(app_yaml)
        except ConfigLoadError as exc:
            return _json_error(str(exc))
        state.discovery_dir = str(discovery_dir)
        state.app_yaml_path = str(app_yaml)
        state.needs_scaffold = False
        state.state = "yaml_reviewed"
        state.dry_run_ok = False
        runtime.workspace.save_state(state)
        return {"path": str(app_yaml), "state": state.to_dict()}

    @app.get("/api/dockerfile/proposal", response_class=PlainTextResponse)
    async def dockerfile_proposal() -> str:
        state = runtime.workspace.load_state()
        workload_type: WorkloadType = "job"
        if state.app_yaml_path and Path(state.app_yaml_path).exists():
            try:
                workload_type = load_app_config(Path(state.app_yaml_path)).workload.type
            except ConfigLoadError:
                workload_type = "job"
        proposal = build_dockerfile_proposal(workload_type)
        state.dockerfile_proposal = proposal
        runtime.workspace.save_state(state)
        return proposal

    @app.post("/api/dockerfile/write")
    async def dockerfile_write(payload: dict[str, object]) -> Any:
        state = runtime.workspace.load_state()
        try:
            repo_path = _repo_required(state)
        except StudioRouteError as exc:
            return _json_error(str(exc))
        confirm = bool(payload.get("confirm", False))
        overwrite = bool(payload.get("overwrite", False))
        dockerfile = repo_path / "Dockerfile"
        if not confirm:
            return _json_error(
                "Explicit confirmation is required before writing Dockerfile."
            )
        if dockerfile.exists() and not overwrite:
            return _json_error(
                "Dockerfile already exists; explicit overwrite is required."
            )
        content = str(payload.get("content") or state.dockerfile_proposal or "")
        if not content.strip():
            return _json_error("Dockerfile proposal is empty.")
        dockerfile.write_text(content, encoding="utf-8")
        return {"path": str(dockerfile)}

    @app.get("/api/discovery/report", response_class=PlainTextResponse)
    async def discovery_report() -> str:
        state = runtime.workspace.load_state()
        path = Path(state.discovery_dir) / "discovery-report.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @app.get("/api/discovery/warnings", response_class=PlainTextResponse)
    async def discovery_warnings() -> str:
        state = runtime.workspace.load_state()
        path = Path(state.discovery_dir) / "warnings.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @app.get("/api/app-yaml", response_class=PlainTextResponse)
    async def get_app_yaml() -> str:
        state = runtime.workspace.load_state()
        try:
            path = _app_yaml_required(state)
        except StudioRouteError:
            return ""
        return path.read_text(encoding="utf-8")

    @app.post("/api/app-yaml")
    async def save_app_yaml(payload: dict[str, str]) -> Any:
        state = runtime.workspace.load_state()
        try:
            path = _app_yaml_required(state)
        except StudioRouteError as exc:
            return _json_error(str(exc))
        content = payload.get("content", "")
        path.write_text(content, encoding="utf-8")
        state.state = "yaml_reviewed"
        state.dry_run_ok = False
        runtime.workspace.save_state(state)
        return {"path": str(path), "state": state.to_dict()}

    @app.post("/api/check")
    async def api_check() -> Any:
        state = runtime.workspace.load_state()
        try:
            app_yaml = _app_yaml_required(state)
        except StudioRouteError as exc:
            return _json_error(str(exc))

        def action() -> str:
            load_app_config(app_yaml)
            return "configuration is valid"

        try:
            _, job = await _internal_job(
                runtime, "check", ["k8s-forge", "check", str(app_yaml)], action
            )
        except ConfigLoadError as exc:
            return _json_error(str(exc))
        state.state = "checked"
        runtime.workspace.save_state(state)
        return {"job": job, "state": state.to_dict()}

    @app.post("/api/explain")
    async def api_explain() -> Any:
        state = runtime.workspace.load_state()
        try:
            app_yaml = _app_yaml_required(state)
        except StudioRouteError as exc:
            return _json_error(str(exc))

        def action() -> str:
            config = load_app_config(app_yaml)
            return render_explanation(build_explanation(config))

        try:
            explanation, job = await _internal_job(
                runtime, "explain", ["k8s-forge", "explain", str(app_yaml)], action
            )
        except ConfigLoadError as exc:
            return _json_error(str(exc))
        state.last_explain = explanation
        state.state = "explained"
        runtime.workspace.save_state(state)
        return {"explain": explanation, "job": job, "state": state.to_dict()}

    @app.post("/api/render")
    async def api_render() -> Any:
        state = runtime.workspace.load_state()
        try:
            app_yaml = _app_yaml_required(state)
        except StudioRouteError as exc:
            return _json_error(str(exc))
        output_dir = runtime.workspace.output_dir("generated-k8s")

        def action() -> list[Path]:
            return render_manifests(load_app_config(app_yaml), output_dir)

        try:
            generated, job = await _internal_job(
                runtime, "render", ["k8s-forge", "render", str(app_yaml)], action
            )
        except (ConfigLoadError, RenderError) as exc:
            return _json_error(str(exc))
        state.generated_k8s_dir = str(output_dir)
        state.state = "manifests_rendered"
        state.dry_run_ok = False
        runtime.workspace.save_state(state)
        return {"generated": [str(path) for path in generated], "job": job}

    @app.post("/api/docker/build")
    async def api_docker_build(payload: dict[str, str]) -> Any:
        state = runtime.workspace.load_state()
        try:
            repo_path = _repo_required(state)
        except StudioRouteError as exc:
            return _json_error(str(exc))
        dockerfile = repo_path / "Dockerfile"
        if not dockerfile.exists():
            return _json_error("Dockerfile is missing; review before generating one.")
        image = payload.get("image", "").strip()
        if not image:
            try:
                image = load_app_config(_app_yaml_required(state)).app.image
            except (StudioRouteError, ConfigLoadError):
                image = "k8s-forge-studio:dev"
        job = await runtime.runner.run(
            "docker-build",
            ["docker", "build", "-t", image, "."],
            repo_path,
        )
        return {"job": job.to_dict(), "image": image}

    @app.post("/api/kind/load")
    async def api_kind_load(payload: dict[str, str]) -> Any:
        image = payload.get("image", "").strip()
        if not image:
            return _json_error("Image is required for kind load.")
        job = await runtime.runner.run(
            "kind-load",
            ["kind", "load", "docker-image", image],
            runtime.workspace.root,
        )
        return {"job": job.to_dict(), "image": image}

    @app.post("/api/dry-run")
    async def api_dry_run() -> Any:
        state = runtime.workspace.load_state()
        manifests_dir = Path(state.generated_k8s_dir)
        if not manifests_dir.exists():
            return _json_error("Rendered manifests are missing.")
        job = await runtime.runner.run(
            "kubectl-dry-run",
            ["kubectl", "apply", "--dry-run=client", "-f", str(manifests_dir)],
            runtime.workspace.root,
        )
        if job.status == "succeeded":
            state.dry_run_ok = True
            state.state = "dry_run_ok"
            runtime.workspace.save_state(state)
        return {"job": job.to_dict(), "state": state.to_dict()}

    @app.post("/api/deploy")
    async def api_deploy(payload: dict[str, bool]) -> Any:
        state = runtime.workspace.load_state()
        manifests_dir = Path(state.generated_k8s_dir)
        allowed, reason = can_deploy(state, manifests_dir)
        if not payload.get("confirm", False):
            return _json_error("Explicit deploy confirmation is required.")
        if not allowed:
            return _json_error(reason)
        job = await runtime.runner.run(
            "kubectl-deploy",
            ["kubectl", "apply", "-f", str(manifests_dir)],
            runtime.workspace.root,
        )
        if job.status == "succeeded":
            state.state = "deployed"
            runtime.workspace.save_state(state)
        return {"job": job.to_dict(), "state": state.to_dict()}

    @app.post("/api/status")
    async def api_status() -> Any:
        state = runtime.workspace.load_state()
        try:
            config = load_app_config(_app_yaml_required(state))
        except (StudioRouteError, ConfigLoadError) as exc:
            return _json_error(str(exc))
        job = await runtime.runner.run(
            "kubectl-status",
            ["kubectl", "get", "all", "-n", config.app.namespace],
            runtime.workspace.root,
        )
        return {"job": job.to_dict()}

    @app.get("/api/jobs")
    async def api_jobs() -> dict[str, object]:
        return {"jobs": [job.to_dict() for job in runtime.jobs.list_jobs()]}

    @app.get("/api/jobs/{job_id}")
    async def api_job(job_id: str) -> Any:
        job = runtime.jobs.get_job(job_id)
        if not job:
            return _json_error("Job not found.", 404)
        log = job.log_path.read_text(encoding="utf-8") if job.log_path.exists() else ""
        return {"job": job.to_dict(), "log": log}

    @app.websocket("/ws/jobs")
    async def ws_jobs(websocket: WebSocket) -> None:
        await websocket.accept()
        queue = await runtime.jobs.subscribe()
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            runtime.jobs.unsubscribe(queue)
        except asyncio.CancelledError:
            runtime.jobs.unsubscribe(queue)
            raise

    return app
