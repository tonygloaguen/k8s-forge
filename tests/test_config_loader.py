from pathlib import Path

import pytest

from k8s_forge.config_loader import load_app_config
from k8s_forge.exceptions import ConfigLoadError

ROOT = Path(__file__).resolve().parents[1]


def test_load_demo_app_example() -> None:
    config = load_app_config(ROOT / "examples" / "demo-app.yaml")

    assert config.app.name == "demo-app"
    assert config.app.namespace == "demo"
    assert config.app.image == "ghcr.io/example/demo-app:1.0.0"


def test_load_admin_api_example() -> None:
    config = load_app_config(ROOT / "examples" / "admin-api.yaml")

    assert config.app.name == "admin-api"
    assert config.app.namespace == "admin"
    assert config.app.image == "ghcr.io/example/admin-api:2.1.0"


def test_load_app_config_rejects_invalid_yaml_root(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(ConfigLoadError, match="YAML mapping"):
        load_app_config(config_path)


def test_load_app_config_rejects_invalid_port(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
app:
  name: invalid-app
  namespace: invalid
  image: ghcr.io/example/invalid-app:1.0.0
  containerPort: 70000
  replicas: 1
service:
  enabled: true
  port: 80
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigLoadError, match="containerPort"):
        load_app_config(config_path)
