from pathlib import Path

import pytest

from k8s_forge.ansible_renderer import (
    render_ansible_files,
    resolve_ansible_project_name,
)
from k8s_forge.exceptions import RenderError
from k8s_forge.models import AppConfig


def _base_config() -> dict[str, object]:
    return {
        "app": {
            "name": "weatherapi",
            "namespace": "weather",
            "image": "weatherapi:0.1.0",
            "containerPort": 8000,
            "replicas": 2,
        },
        "service": {"enabled": True, "port": 80},
    }


def _enabled_config() -> dict[str, object]:
    config = _base_config()
    config["ansible"] = {
        "enabled": True,
        "projectName": "",
        "inventory": {"type": "local", "hosts": ["localhost"]},
        "playbook": {"name": "site.yml"},
        "roles": {"enabled": True},
        "collections": {
            "kubernetes": {"enabled": True},
            "community": {"enabled": False},
        },
        "examples": {"enabled": True},
    }
    return config


def _read_generated_text(root: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_resolve_ansible_project_name_falls_back_to_app_name() -> None:
    config = AppConfig.model_validate(_enabled_config())

    assert resolve_ansible_project_name(config) == "weatherapi"


def test_resolve_ansible_project_name_uses_configured_name() -> None:
    config_data = _enabled_config()
    ansible = config_data["ansible"]
    assert isinstance(ansible, dict)
    ansible["projectName"] = "weather-automation"
    config = AppConfig.model_validate(config_data)

    assert resolve_ansible_project_name(config) == "weather-automation"


def test_no_files_generated_when_ansible_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    generated = render_ansible_files(config, tmp_path)

    assert generated == []
    assert not (tmp_path / "README.md").exists()


def test_ansible_renderer_generates_expected_files(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    generated = render_ansible_files(config, tmp_path)

    assert {str(path.relative_to(tmp_path)) for path in generated} == {
        "README.md",
        "ansible.cfg",
        "inventory.ini",
        "site.yml",
        "group_vars/all.yml",
        "roles/README.md",
    }
    assert "Ansible Readiness" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_ansible_files_contain_app_context_and_local_inventory(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_ansible_files(config, tmp_path)

    combined = _read_generated_text(tmp_path)
    inventory = (tmp_path / "inventory.ini").read_text(encoding="utf-8")
    playbook = (tmp_path / "site.yml").read_text(encoding="utf-8")
    variables = (tmp_path / "group_vars" / "all.yml").read_text(encoding="utf-8")
    assert "weatherapi" in combined
    assert "weather" in combined
    assert "localhost ansible_connection=local" in inventory
    assert "ansible.builtin.debug" in playbook
    assert "ansible.builtin.assert" in playbook
    assert 'app_name: "weatherapi"' in variables
    assert 'namespace: "weather"' in variables


def test_ansible_renderer_respects_disabled_examples(tmp_path: Path) -> None:
    config_data = _enabled_config()
    ansible = config_data["ansible"]
    assert isinstance(ansible, dict)
    examples = ansible["examples"]
    assert isinstance(examples, dict)
    examples["enabled"] = False
    config = AppConfig.model_validate(config_data)

    generated = render_ansible_files(config, tmp_path)

    assert "site.yml" not in {str(path.relative_to(tmp_path)) for path in generated}
    assert not (tmp_path / "site.yml").exists()


def test_ansible_renderer_respects_disabled_roles(tmp_path: Path) -> None:
    config_data = _enabled_config()
    ansible = config_data["ansible"]
    assert isinstance(ansible, dict)
    roles = ansible["roles"]
    assert isinstance(roles, dict)
    roles["enabled"] = False
    config = AppConfig.model_validate(config_data)

    generated = render_ansible_files(config, tmp_path)

    assert "roles/README.md" not in {
        str(path.relative_to(tmp_path)) for path in generated
    }
    assert not (tmp_path / "roles" / "README.md").exists()


def test_ansible_output_contains_no_sensitive_or_active_task_content(
    tmp_path: Path,
) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_ansible_files(config, tmp_path)

    combined = _read_generated_text(tmp_path).lower()
    forbidden = [
        "secret",
        "token",
        "credential",
        "password",
        "private key",
        "ssh",
        "scp",
        "ansible-playbook",
        "kubectl apply",
        "helm install",
        "helm upgrade",
        "terraform apply",
        "terraform destroy",
        "ansible.builtin.shell",
        "ansible.builtin.command",
        "ansible.builtin.package",
        "ansible.builtin.service",
        "community.docker",
        "kubernetes.core.k8s",
    ]
    for value in forbidden:
        assert value not in combined
    assert "192.168." not in combined
    assert "10.0." not in combined


def test_ansible_renderer_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_ansible_files(config, tmp_path)

    with pytest.raises(RenderError, match="use --force"):
        render_ansible_files(config, tmp_path)


def test_ansible_renderer_overwrites_with_force(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())
    render_ansible_files(config, tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("old", encoding="utf-8")

    render_ansible_files(config, tmp_path, force=True)

    assert "Ansible Readiness" in readme.read_text(encoding="utf-8")
