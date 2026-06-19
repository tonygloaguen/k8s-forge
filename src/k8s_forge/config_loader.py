"""YAML configuration loading."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from k8s_forge.exceptions import ConfigLoadError
from k8s_forge.models import AppConfig


def load_app_config(path: Path) -> AppConfig:
    """Load and validate an application configuration file."""
    try:
        raw_content = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"Unable to read configuration file: {path}"
        raise ConfigLoadError(msg) from exc

    try:
        data: Any = yaml.safe_load(raw_content)
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML configuration file: {path}"
        raise ConfigLoadError(msg) from exc

    if not isinstance(data, dict):
        msg = "Configuration root must be a YAML mapping."
        raise ConfigLoadError(msg)

    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        msg = "Configuration validation failed."
        raise ConfigLoadError(msg) from exc
