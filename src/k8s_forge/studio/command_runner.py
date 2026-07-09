"""Controlled command execution for Studio."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from pathlib import Path

from k8s_forge.studio.jobs import StudioJobManager
from k8s_forge.studio.schemas import JobStatus, StudioJob

LogCallback = Callable[[StudioJob, str, str], Awaitable[None]]


class CommandRejectedError(ValueError):
    """Raised when a command is outside the Studio allowlist."""


FORBIDDEN_TOKENS = (
    "push",
    "install",
    "terraform",
    "ansible-playbook",
    "rm",
)


def _contains_forbidden_token(command: list[str]) -> bool:
    joined = " ".join(command).lower()
    return any(token in joined for token in FORBIDDEN_TOKENS)


def validate_allowed_command(command: list[str]) -> None:
    """Validate that a command is in the Studio allowlist."""
    if not command:
        msg = "empty command is not allowed"
        raise CommandRejectedError(msg)
    if _contains_forbidden_token(command):
        msg = f"command contains a forbidden token: {' '.join(command)}"
        raise CommandRejectedError(msg)

    program = command[0]
    allowed = False
    if program == "git":
        allowed = len(command) >= 2 and command[1] == "clone"
        allowed = allowed or (
            len(command) >= 4 and command[1] == "-C" and command[3] == "pull"
        )
    elif program == "docker":
        allowed = len(command) >= 2 and command[1] == "build"
    elif program == "kind":
        allowed = len(command) >= 3 and command[1:3] == ["load", "docker-image"]
        allowed = allowed or command == ["kind", "get", "clusters"]
    elif program == "kubectl":
        allowed = len(command) >= 2 and command[1] in {
            "apply",
            "get",
            "logs",
            "port-forward",
        }
        allowed = allowed or (
            len(command) == 7
            and command[1:3] == ["delete", "job"]
            and command[4] == "-n"
            and command[6] == "--ignore-not-found"
        )

    if not allowed:
        msg = f"command is not allowed in Studio: {' '.join(command)}"
        raise CommandRejectedError(msg)


class CommandRunner:
    """Run allowlisted commands without shell expansion."""

    def __init__(self, jobs: StudioJobManager) -> None:
        self.jobs = jobs
        self.processes: dict[str, asyncio.subprocess.Process] = {}

    async def run(
        self,
        job_type: str,
        command: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: int = 300,
    ) -> StudioJob:
        """Run a command and stream stdout/stderr to the job manager."""
        validate_allowed_command(command)
        job = self.jobs.create_job(job_type, command, cwd, env=env)
        await self.jobs.mark_started(job)
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(cwd),
                env=merged_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self.processes[job.id] = process
            await asyncio.wait_for(self._stream_process(job, process), timeout=timeout)
            exit_code = await process.wait()
        except TimeoutError:
            timeout_process = self.processes.get(job.id)
            if timeout_process:
                timeout_process.kill()
                await timeout_process.wait()
            await self.jobs.append_log(job, "stderr", "command timed out")
            await self.jobs.mark_finished(job, "failed", 124)
            return job
        finally:
            self.processes.pop(job.id, None)

        status: JobStatus = "succeeded" if exit_code == 0 else "failed"
        await self.jobs.mark_finished(job, status, exit_code)
        return job

    async def _stream_process(
        self, job: StudioJob, process: asyncio.subprocess.Process
    ) -> None:
        async def stream_reader(
            reader: asyncio.StreamReader | None, stream: str
        ) -> None:
            if reader is None:
                return
            while True:
                raw_line = await reader.readline()
                if not raw_line:
                    break
                line = raw_line.decode(errors="replace").rstrip()
                await self.jobs.append_log(job, stream, line)

        await asyncio.gather(
            stream_reader(process.stdout, "stdout"),
            stream_reader(process.stderr, "stderr"),
        )

    async def cancel(self, job_id: str) -> bool:
        """Cancel a running job when possible."""
        process = self.processes.get(job_id)
        job = self.jobs.get_job(job_id)
        if process is None or job is None or not job.cancellable:
            return False
        process.terminate()
        await process.wait()
        await self.jobs.mark_finished(job, "cancelled", -1)
        self.processes.pop(job_id, None)
        return True
