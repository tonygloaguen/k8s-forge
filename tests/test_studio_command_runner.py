import asyncio
from pathlib import Path

import pytest

from k8s_forge.studio.command_runner import (
    CommandRejectedError,
    CommandRunner,
    validate_allowed_command,
)
from k8s_forge.studio.jobs import StudioJobManager


def test_allowed_commands_are_accepted() -> None:
    validate_allowed_command(["git", "clone", "https://example/repo.git", "repo"])
    validate_allowed_command(["git", "-C", "repo", "pull", "--ff-only"])
    validate_allowed_command(["docker", "build", "-t", "demo:dev", "."])
    validate_allowed_command(["kind", "load", "docker-image", "demo:dev"])
    validate_allowed_command(
        ["kubectl", "apply", "--dry-run=client", "-f", "generated"]
    )
    validate_allowed_command(["kubectl", "get", "all", "-n", "demo"])


@pytest.mark.parametrize(
    "command",
    [
        ["git", "push"],
        ["kubectl", "delete", "pod", "x"],
        ["helm", "install", "x", "chart"],
        ["terraform", "apply"],
        ["ansible-playbook", "site.yml"],
        ["rm", "-rf", "/tmp/x"],
    ],
)
def test_forbidden_commands_are_rejected(command: list[str]) -> None:
    with pytest.raises(CommandRejectedError):
        validate_allowed_command(command)


class _FakeReader:
    def __init__(self, lines: list[bytes]) -> None:
        self.lines = lines

    async def readline(self) -> bytes:
        if self.lines:
            return self.lines.pop(0)
        return b""


class _FakeProcess:
    def __init__(self) -> None:
        self.stdout = _FakeReader([b"hello\n"])
        self.stderr = _FakeReader([b"warn\n"])
        self.returncode = 0

    async def wait(self) -> int:
        return 0

    def kill(self) -> None:
        self.returncode = 124

    def terminate(self) -> None:
        self.returncode = -1


def test_command_runner_uses_exec_without_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_exec(*args: str, **kwargs: object) -> _FakeProcess:
        calls.append({"args": args, "kwargs": kwargs})
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    jobs = StudioJobManager(tmp_path / "jobs")
    runner = CommandRunner(jobs)

    job = asyncio.run(runner.run("status", ["kubectl", "get", "pods"], tmp_path))

    assert job.status == "succeeded"
    assert "shell" not in calls[0]["kwargs"]
    assert "hello" in job.log_path.read_text(encoding="utf-8")
    assert "warn" in job.log_path.read_text(encoding="utf-8")
