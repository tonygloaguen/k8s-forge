"""Manifest rendering entry points.

Full Kubernetes manifest generation is intentionally outside this initial
skeleton.
"""

from pathlib import Path

from k8s_forge.exceptions import RenderError
from k8s_forge.models import AppConfig


def render_manifests(config: AppConfig, output_dir: Path) -> list[Path]:
    """Render Kubernetes manifests.

    This placeholder keeps the public interface in place without implementing
    the MVP rendering logic yet.
    """
    _ = (config, output_dir)
    msg = "Manifest rendering is not implemented yet."
    raise RenderError(msg)
