"""Studio server launcher."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


class StudioDependencyError(RuntimeError):
    """Raised when optional Studio dependencies are missing."""


class StudioHostError(ValueError):
    """Raised when Studio is asked to bind to a non-local host."""


def _require_local_host(host: str) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        msg = "Studio only binds to 127.0.0.1 or localhost."
        raise StudioHostError(msg)


def run_studio(host: str, port: int, workspace: Path) -> None:
    """Run the local Studio server."""
    _require_local_host(host)
    try:
        uvicorn: Any = importlib.import_module("uvicorn")
    except ImportError as exc:
        msg = (
            "Studio dependencies are missing.\n"
            "Install with:\n"
            'pip install -e ".[studio]"\n'
            "or for development:\n"
            'pip install -e ".[dev,studio]"'
        )
        raise StudioDependencyError(msg) from exc

    from k8s_forge.studio.routes import create_app

    uvicorn.run(create_app(workspace), host=host, port=port)
