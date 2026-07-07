"""Studio job management and event broadcasting."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from k8s_forge.studio.schemas import JobStatus, StudioJob


class StudioJobManager:
    """Track Studio jobs and publish log events."""

    def __init__(self, jobs_dir: Path) -> None:
        self.jobs_dir = jobs_dir
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, StudioJob] = {}
        self._subscribers: set[asyncio.Queue[dict[str, object]]] = set()

    def create_job(
        self,
        job_type: str,
        command: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        cancellable: bool = True,
    ) -> StudioJob:
        """Create and register a queued job."""
        job_id = uuid4().hex[:12]
        job = StudioJob(
            id=job_id,
            type=job_type,
            status="queued",
            command=command,
            cwd=cwd,
            env=env or {},
            started_at=None,
            finished_at=None,
            exit_code=None,
            log_path=self.jobs_dir / f"{job_id}.log",
            cancellable=cancellable,
        )
        self._jobs[job.id] = job
        job.log_path.write_text("", encoding="utf-8")
        return job

    def list_jobs(self) -> list[StudioJob]:
        """Return jobs in insertion order."""
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> StudioJob | None:
        """Return a job by id."""
        return self._jobs.get(job_id)

    async def publish(self, event: dict[str, object]) -> None:
        """Publish an event to all subscribers."""
        for queue in list(self._subscribers):
            await queue.put(event)

    async def subscribe(self) -> asyncio.Queue[dict[str, object]]:
        """Subscribe to job events."""
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        """Remove a subscriber."""
        self._subscribers.discard(queue)

    async def mark_started(self, job: StudioJob) -> None:
        """Mark a job running."""
        job.status = "running"
        job.started_at = datetime.now(UTC)
        await self.publish({"event": "job_started", "job_id": job.id})

    async def append_log(self, job: StudioJob, stream: str, line: str) -> None:
        """Append a log line and publish it."""
        with job.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stream}] {line}\n")
        await self.publish(
            {"event": "job_log", "job_id": job.id, "stream": stream, "line": line}
        )

    async def mark_finished(
        self, job: StudioJob, status: JobStatus, exit_code: int
    ) -> None:
        """Mark a job finished."""
        job.status = status
        job.exit_code = exit_code
        job.finished_at = datetime.now(UTC)
        event = {
            "succeeded": "job_succeeded",
            "failed": "job_failed",
            "cancelled": "job_cancelled",
        }.get(status, "job_failed")
        await self.publish({"event": event, "job_id": job.id, "exit_code": exit_code})
