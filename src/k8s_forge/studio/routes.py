# mypy: disable-error-code="import-not-found,untyped-decorator,valid-type,attr-defined"
"""FastAPI routes for Studio."""

from __future__ import annotations

import asyncio
import re
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
    globals()["WebSocket"] = WebSocket
    globals()["WebSocketDisconnect"] = WebSocketDisconnect
    return (
        FastAPI,
        WebSocket,
        WebSocketDisconnect,
        HTMLResponse,
        JSONResponse,
        PlainTextResponse,
        StaticFiles,
    )


def _json_error(
    message: str, status_code: int = 400, next_action: str | None = None
) -> Any:
    _, _, _, _, JSONResponse, _, _ = _load_fastapi()
    payload: dict[str, str] = {"error": message}
    if next_action:
        payload["next_action"] = next_action
    return JSONResponse(payload, status_code=status_code)


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


def _normalize_repo_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower().replace("_", "-"))
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "discovered-app"


def _infer_python_module(repo_path: Path, app_name: str) -> str:
    candidate = app_name.replace("-", "_")
    if (repo_path / candidate).is_dir() or (repo_path / f"{candidate}.py").exists():
        return candidate
    py_files = sorted(
        file
        for file in repo_path.glob("*.py")
        if file.name not in {"setup.py", "conftest.py"}
    )
    if len(py_files) == 1:
        return py_files[0].stem
    return ""


def _has_python_signals(repo_path: Path) -> bool:
    return any(
        (repo_path / marker).exists()
        for marker in ("requirements.txt", "pyproject.toml", "setup.py")
    ) or any(repo_path.glob("*.py"))


def _build_next_action(state: StudioState) -> str:
    if state.needs_scaffold:
        return "Create an assisted scaffold, then run Check."
    if not state.repo_path:
        return "Select a repository or clone one."
    if state.state == "repo_ready":
        return "Run Discover."
    if not state.app_yaml_path:
        return (
            "Run Discover or create an assisted scaffold if discovery was report-only."
        )
    if state.state == "yaml_reviewed":
        return "Run Check."
    if state.state == "checked":
        return "Run Explain or Render."
    if state.state == "explained":
        return "Run Render."
    if state.state == "manifests_rendered":
        return "Run Dry-run."
    if state.logs_ok:
        return "Review logs and production handoff checklist."
    if state.deploy_status == "succeeded":
        return "Run Status, then read logs." if not state.status_ok else "Read logs."
    if state.deploy_status == "blocked_existing_job":
        return "Delete existing Job and redeploy, or delete the Job manually."
    if state.dry_run_ok:
        return "Review the exact command and confirm Deploy only for a local lab."
    return "Run Check."


def _current_state_summary(state: StudioState) -> str:
    if state.needs_scaffold:
        return "Assisted scaffold required: no app.yaml was generated."
    if not state.repo_path:
        return "No repository selected."
    if not state.app_yaml_path:
        return "Repository selected, no app.yaml available yet."
    return f"Pipeline state: {state.state}"


def _read_job_log_lines(job: Any, stream: str | None = None) -> list[str]:
    if not job.log_path.exists():
        return []
    prefix = f"[{stream}] " if stream else ""
    lines: list[str] = []
    for raw_line in job.log_path.read_text(encoding="utf-8").splitlines():
        if stream and not raw_line.startswith(prefix):
            continue
        line = raw_line.removeprefix(prefix)
        if not stream and line.startswith("[") and "] " in line:
            line = line.split("] ", 1)[1]
        if line.strip():
            lines.append(line.strip())
    return lines


def _parse_kind_clusters(job: Any) -> list[str]:
    clusters: list[str] = []
    for line in _read_job_log_lines(job, "stdout"):
        cluster = line.strip()
        if cluster and cluster not in clusters:
            clusters.append(cluster)
    return clusters


def _preferred_kind_cluster(clusters: list[str]) -> str:
    if "devsecops" in clusters:
        return "devsecops"
    if "kind" in clusters:
        return "kind"
    return clusters[0] if clusters else ""


def _job_failure_reason(job: Any) -> str:
    stderr_lines = _read_job_log_lines(job, "stderr")
    if stderr_lines:
        return stderr_lines[-1]
    all_lines = _read_job_log_lines(job)
    return all_lines[-1] if all_lines else "command failed"


def _job_immutable_failure(job: Any) -> bool:
    text = "\n".join(_read_job_log_lines(job)).lower()
    return "job" in text and "field is immutable" in text


def _deploy_failure_reason(job: Any) -> str:
    if _job_immutable_failure(job):
        return "Existing Kubernetes Job cannot be updated in place."
    return _job_failure_reason(job)


def _app_context_from_state(state: StudioState) -> dict[str, object]:
    if not state.app_yaml_path:
        return {}
    try:
        config = load_app_config(Path(state.app_yaml_path))
    except (ConfigLoadError, FileNotFoundError):
        return {}
    return {
        "name": config.app.name,
        "namespace": config.app.namespace,
        "image": config.app.image,
        "workload_type": config.workload.type,
    }


def _latest_cronjob_job_name(job: Any, app_name: str) -> str:
    candidates: list[str] = []
    for line in _read_job_log_lines(job, "stdout"):
        parts = line.split()
        if not parts or parts[0].lower() == "name":
            continue
        name = parts[0]
        if name == app_name or name.startswith(f"{app_name}-"):
            candidates.append(name)
    return candidates[-1] if candidates else ""


def _job_log_text(job: Any) -> str:
    return "\n".join(_read_job_log_lines(job))


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
        dockerfile_path = (
            Path(state.repo_path) / "Dockerfile" if state.repo_path else None
        )
        discovery_dir = state.discovery_dir or str(
            runtime.workspace.output_dir("generated-discovery")
        )
        generated_k8s_dir = state.generated_k8s_dir or str(
            runtime.workspace.output_dir("generated-k8s")
        )
        return {
            "state": state.to_dict(),
            "current_state": _current_state_summary(state),
            "next_action": _build_next_action(state),
            "deploy_allowed": deploy_allowed,
            "deploy_reason": deploy_reason,
            "paths": {
                "studio_output_dir": str(runtime.workspace.outputs_dir),
                "generated_discovery_dir": discovery_dir,
                "generated_k8s_dir": generated_k8s_dir,
            },
            "app_context": _app_context_from_state(state),
            "dockerfile": {
                "exists": bool(dockerfile_path and dockerfile_path.exists()),
                "path": str(dockerfile_path) if dockerfile_path else "",
            },
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
        repo_path = Path(state.repo_path) if state.repo_path else None
        app_name = _normalize_repo_name(
            repo_path.name if repo_path else "discovered-app"
        )
        python_module = _infer_python_module(repo_path, app_name) if repo_path else ""
        python_cli_probable = bool(repo_path and _has_python_signals(repo_path))
        startup_command = f"python -m {python_module} --help" if python_module else ""
        workload_type = (
            "job" if state.needs_scaffold and python_cli_probable else "deployment"
        )
        return {
            "app_name": app_name,
            "namespace": app_name,
            "image": f"{app_name}:dev",
            "workload_type": workload_type,
            "startup_command": startup_command,
            "container_port": None,
            "service_enabled": workload_type == "deployment",
            "ingress_enabled": False,
            "restart_policy": "OnFailure"
            if workload_type in {"job", "cronjob"}
            else "Always",
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
        state.docker_build_ok = False
        state.kind_load_ok = False
        state.status_ok = False
        state.logs_ok = False
        state.last_logs = ""
        state.deploy_status = "not_started"
        state.deploy_blocked_reason = ""
        state.deploy_blocked_next_action = ""
        runtime.workspace.save_state(state)
        return {
            "path": str(app_yaml),
            "state": state.to_dict(),
            "message": "[OK] app.yaml created",
            "next_action": "[NEXT] Run Check",
        }

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
        if dockerfile.exists():
            if not overwrite:
                return _json_error(
                    (
                        "Dockerfile already exists; use the existing Dockerfile "
                        "or confirm overwrite."
                    ),
                    next_action=(
                        "Choose Use existing Dockerfile, or type "
                        "OVERWRITE DOCKERFILE before overwriting."
                    ),
                )
            if payload.get("overwrite_confirmation") != "OVERWRITE DOCKERFILE":
                return _json_error(
                    "Dockerfile overwrite requires strong confirmation.",
                    next_action=(
                        "Type OVERWRITE DOCKERFILE to replace the existing Dockerfile."
                    ),
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
        state.docker_build_ok = False
        state.kind_load_ok = False
        state.status_ok = False
        state.logs_ok = False
        state.last_logs = ""
        state.deploy_status = "not_started"
        state.deploy_blocked_reason = ""
        state.deploy_blocked_next_action = ""
        runtime.workspace.save_state(state)
        return {"path": str(path), "state": state.to_dict()}

    @app.post("/api/check")
    async def api_check() -> Any:
        state = runtime.workspace.load_state()
        try:
            app_yaml = _app_yaml_required(state)
        except StudioRouteError as exc:
            return _json_error(
                str(exc), next_action="Create an assisted scaffold, then run Check."
            )

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
            return _json_error(
                str(exc), next_action="Create an assisted scaffold, then run Explain."
            )

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
            return _json_error(
                str(exc), next_action="Create an assisted scaffold, then run Render."
            )
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
        state.deploy_status = "not_started"
        state.status_ok = False
        state.logs_ok = False
        state.last_logs = ""
        state.deploy_blocked_reason = ""
        state.deploy_blocked_next_action = ""
        runtime.workspace.save_state(state)
        return {
            "generated": [str(path) for path in generated],
            "output_dir": str(output_dir),
            "job": job,
        }

    @app.post("/api/docker/build")
    async def api_docker_build(payload: dict[str, str]) -> Any:
        state = runtime.workspace.load_state()
        try:
            repo_path = _repo_required(state)
        except StudioRouteError as exc:
            return _json_error(str(exc))
        try:
            app_yaml = _app_yaml_required(state)
            image = load_app_config(app_yaml).app.image
        except (StudioRouteError, ConfigLoadError) as exc:
            return _json_error(
                str(exc),
                next_action=(
                    "Create an assisted scaffold with an image before Docker build."
                ),
            )
        dockerfile = repo_path / "Dockerfile"
        if not dockerfile.exists():
            return _json_error(
                "Dockerfile is missing; review or write a Dockerfile before build.",
                next_action=(
                    "Review the Dockerfile proposal, then write it with confirmation."
                ),
            )
        requested_image = payload.get("image", "").strip()
        if requested_image:
            image = requested_image
        job = await runtime.runner.run(
            "docker-build",
            ["docker", "build", "-t", image, "."],
            repo_path,
        )
        state.docker_build_ok = job.status == "succeeded"
        if state.docker_build_ok:
            state.kind_load_ok = False
            state.deploy_status = "not_started"
        runtime.workspace.save_state(state)
        return {"job": job.to_dict(), "image": image, "state": state.to_dict()}

    @app.get("/api/kind/clusters")
    async def api_kind_clusters() -> dict[str, object]:
        job = await runtime.runner.run(
            "kind-clusters",
            ["kind", "get", "clusters"],
            runtime.workspace.root,
        )
        clusters = _parse_kind_clusters(job) if job.status == "succeeded" else []
        preferred = _preferred_kind_cluster(clusters)
        return {
            "clusters": clusters,
            "preferred": preferred,
            "available": bool(preferred),
            "message": "Kind cluster detected"
            if preferred
            else "No kind cluster found",
            "job": job.to_dict(),
        }

    @app.post("/api/kind/load")
    async def api_kind_load(payload: dict[str, str]) -> Any:
        image = payload.get("image", "").strip()
        cluster = payload.get("cluster", "").strip()
        if not image:
            return _json_error("Image is required for kind load.")
        if not cluster:
            clusters_job = await runtime.runner.run(
                "kind-clusters",
                ["kind", "get", "clusters"],
                runtime.workspace.root,
            )
            cluster = _preferred_kind_cluster(_parse_kind_clusters(clusters_job))
        if not cluster:
            return _json_error(
                "No kind cluster found.",
                next_action="Create a kind cluster or select an existing cluster.",
            )
        command = ["kind", "load", "docker-image", image, "--name", cluster]
        job = await runtime.runner.run(
            "kind-load",
            command,
            runtime.workspace.root,
        )
        state = runtime.workspace.load_state()
        state.kind_load_ok = job.status == "succeeded"
        if state.kind_load_ok:
            state.deploy_status = "not_started"
        runtime.workspace.save_state(state)
        reason = _job_failure_reason(job) if job.status == "failed" else ""
        return {
            "job": job.to_dict(),
            "image": image,
            "cluster": cluster,
            "reason": reason,
            "state": state.to_dict(),
        }

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
            state.deploy_status = "not_started"
            state.deploy_blocked_reason = ""
            state.deploy_blocked_next_action = ""
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
        try:
            config = load_app_config(_app_yaml_required(state))
        except (StudioRouteError, ConfigLoadError) as exc:
            return _json_error(str(exc))
        state.deploy_status = "running"
        runtime.workspace.save_state(state)
        if config.workload.type == "job":
            get_command = [
                "kubectl",
                "get",
                "job",
                config.app.name,
                "-n",
                config.app.namespace,
            ]
            get_job = await runtime.runner.run(
                "kubectl-get-job",
                get_command,
                runtime.workspace.root,
            )
            if get_job.status == "succeeded":
                state.state = "deploy_blocked"
                state.deploy_status = "blocked_existing_job"
                state.deploy_blocked_reason = (
                    "Kubernetes Job spec.template is immutable"
                )
                state.deploy_blocked_next_action = "Delete existing Job and redeploy"
                runtime.workspace.save_state(state)
                return {
                    "deploy_status": "blocked_existing_job",
                    "job_exists": True,
                    "job_name": config.app.name,
                    "namespace": config.app.namespace,
                    "reason": state.deploy_blocked_reason,
                    "next_action": state.deploy_blocked_next_action,
                    "command": " ".join(get_command),
                    "job": get_job.to_dict(),
                    "state": state.to_dict(),
                }
        command = ["kubectl", "apply", "-f", str(manifests_dir)]
        job = await runtime.runner.run(
            "kubectl-deploy",
            command,
            runtime.workspace.root,
        )
        if job.status == "succeeded":
            state.state = "deployed"
            state.deploy_status = "succeeded"
            state.deploy_blocked_reason = ""
            state.deploy_blocked_next_action = ""
            state.status_ok = False
            state.logs_ok = False
            state.last_logs = ""
            runtime.workspace.save_state(state)
        else:
            reason = _deploy_failure_reason(job)
            state.deploy_status = "failed"
            if reason == "Existing Kubernetes Job cannot be updated in place.":
                state.state = "deploy_blocked"
                state.deploy_status = "blocked_existing_job"
                state.deploy_blocked_reason = reason
                state.deploy_blocked_next_action = (
                    "Delete existing Job and redeploy, or delete the Job manually."
                )
            runtime.workspace.save_state(state)
        return {
            "deploy_status": state.deploy_status,
            "job_exists": False,
            "job": job.to_dict(),
            "state": state.to_dict(),
            "namespace": config.app.namespace,
            "manifests_dir": str(manifests_dir),
            "command": " ".join(command),
            "reason": _deploy_failure_reason(job) if job.status == "failed" else "",
            "next_action": "Run Status, then read logs."
            if job.status == "succeeded"
            else "Delete existing Job and redeploy, or delete the Job manually.",
        }

    @app.post("/api/deploy/job/redeploy")
    async def api_delete_job_and_redeploy(payload: dict[str, str]) -> Any:
        state = runtime.workspace.load_state()
        manifests_dir = Path(state.generated_k8s_dir)
        allowed, reason = can_deploy(state, manifests_dir)
        confirmation = payload.get("confirmation", "")
        if confirmation != "DELETE JOB AND REDEPLOY":
            return _json_error(
                "Confirmation text did not match. No Job was deleted.",
                next_action=(
                    "Type exactly DELETE JOB AND REDEPLOY to delete the Job "
                    "and redeploy."
                ),
            )
        if not allowed:
            return _json_error(reason)
        try:
            config = load_app_config(_app_yaml_required(state))
        except (StudioRouteError, ConfigLoadError) as exc:
            return _json_error(str(exc))
        if config.workload.type != "job":
            return _json_error(
                "Delete existing Job and redeploy is only for workload.type=job."
            )
        state.deploy_status = "running"
        runtime.workspace.save_state(state)
        delete_command = [
            "kubectl",
            "delete",
            "job",
            config.app.name,
            "-n",
            config.app.namespace,
            "--ignore-not-found",
        ]
        delete_job = await runtime.runner.run(
            "kubectl-delete-job",
            delete_command,
            runtime.workspace.root,
        )
        if delete_job.status != "succeeded":
            state.deploy_status = "failed"
            runtime.workspace.save_state(state)
            return {
                "deploy_status": "failed",
                "delete_job": delete_job.to_dict(),
                "job": delete_job.to_dict(),
                "state": state.to_dict(),
                "job_name": config.app.name,
                "namespace": config.app.namespace,
                "manifests_dir": str(manifests_dir),
                "delete_command": " ".join(delete_command),
                "reason": _job_failure_reason(delete_job),
            }
        apply_command = ["kubectl", "apply", "-f", str(manifests_dir)]
        apply_job = await runtime.runner.run(
            "kubectl-deploy",
            apply_command,
            runtime.workspace.root,
        )
        if apply_job.status == "succeeded":
            state.state = "deployed"
            state.deploy_status = "succeeded"
            state.deploy_blocked_reason = ""
            state.deploy_blocked_next_action = ""
            state.status_ok = False
            state.logs_ok = False
            state.last_logs = ""
            runtime.workspace.save_state(state)
        else:
            state.deploy_status = "failed"
            runtime.workspace.save_state(state)
        return {
            "deploy_status": state.deploy_status,
            "delete_job": delete_job.to_dict(),
            "job": apply_job.to_dict(),
            "state": state.to_dict(),
            "job_name": config.app.name,
            "namespace": config.app.namespace,
            "manifests_dir": str(manifests_dir),
            "delete_command": " ".join(delete_command),
            "apply_command": " ".join(apply_command),
            "reason": _deploy_failure_reason(apply_job)
            if apply_job.status == "failed"
            else "",
            "next_action": "Run Status, then read logs."
            if apply_job.status == "succeeded"
            else "Review delete/apply output.",
        }

    @app.post("/api/logs")
    async def api_logs() -> Any:
        state = runtime.workspace.load_state()
        if state.deploy_status != "succeeded":
            return _json_error(
                "Deploy must succeed before reading logs.",
                next_action="Deploy to the local lab, then read logs.",
            )
        try:
            config = load_app_config(_app_yaml_required(state))
        except (StudioRouteError, ConfigLoadError) as exc:
            return _json_error(str(exc))
        namespace = config.app.namespace
        app_name = config.app.name
        workload_type = config.workload.type
        if workload_type == "job":
            command = ["kubectl", "logs", "-n", namespace, f"job/{app_name}"]
        elif workload_type == "cronjob":
            get_command = [
                "kubectl",
                "get",
                "jobs",
                "-n",
                namespace,
                "--sort-by=.metadata.creationTimestamp",
            ]
            get_job = await runtime.runner.run(
                "kubectl-get-jobs", get_command, runtime.workspace.root
            )
            if get_job.status != "succeeded":
                state.logs_ok = False
                state.last_logs = _job_log_text(get_job)
                runtime.workspace.save_state(state)
                return {
                    "job": get_job.to_dict(),
                    "workload_type": workload_type,
                    "namespace": namespace,
                    "command": " ".join(get_command),
                    "logs": state.last_logs,
                    "reason": _job_failure_reason(get_job),
                    "next_action": "Run Status and inspect CronJob state.",
                    "state": state.to_dict(),
                }
            latest_job = _latest_cronjob_job_name(get_job, app_name)
            if not latest_job:
                state.logs_ok = False
                state.last_logs = _job_log_text(get_job)
                runtime.workspace.save_state(state)
                return _json_error(
                    "No Job created by the CronJob was found.",
                    next_action=(
                        "Run Status and wait for a CronJob run before reading logs."
                    ),
                )
            command = ["kubectl", "logs", "-n", namespace, f"job/{latest_job}"]
        else:
            command = [
                "kubectl",
                "logs",
                "-n",
                namespace,
                "-l",
                f"app={app_name}",
                "--tail=200",
            ]
        job = await runtime.runner.run("kubectl-logs", command, runtime.workspace.root)
        state.logs_ok = job.status == "succeeded"
        state.last_logs = _job_log_text(job)
        runtime.workspace.save_state(state)
        return {
            "job": job.to_dict(),
            "workload_type": workload_type,
            "namespace": namespace,
            "command": " ".join(command),
            "logs": state.last_logs,
            "reason": _job_failure_reason(job) if job.status == "failed" else "",
            "next_action": "Review logs and production handoff checklist"
            if job.status == "succeeded"
            else "Run Status and inspect pod/job state.",
            "state": state.to_dict(),
        }

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
        state.status_ok = job.status == "succeeded"
        runtime.workspace.save_state(state)
        return {"job": job.to_dict(), "state": state.to_dict()}

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
        queue: asyncio.Queue[dict[str, object]] | None = None
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "connected",
                "message": "Studio job stream connected",
            }
        )
        try:
            queue = await runtime.jobs.subscribe()
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced to Studio clients
            await websocket.send_json(
                {
                    "type": "error",
                    "message": str(exc),
                }
            )
        finally:
            if queue is not None:
                runtime.jobs.unsubscribe(queue)

    return app
