from pathlib import Path

from k8s_forge.models import AppConfig
from k8s_forge.supply_chain_renderer import (
    render_supply_chain_files,
    resolve_supply_chain_image,
)


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
    config["supplyChain"] = {
        "enabled": True,
        "image": "weatherapi:0.1.0",
        "scan": {
            "enabled": True,
            "tool": "trivy",
            "severity": ["HIGH", "CRITICAL"],
        },
        "sbom": {
            "enabled": True,
            "tool": "syft",
            "format": "cyclonedx-json",
        },
        "signing": {
            "enabled": False,
            "tool": "cosign",
            "keyless": True,
        },
    }
    return config


def test_resolve_supply_chain_image_falls_back_to_app_image() -> None:
    config_data = _base_config()
    config_data["supplyChain"] = {"enabled": True, "image": ""}
    config = AppConfig.model_validate(config_data)

    assert resolve_supply_chain_image(config) == "weatherapi:0.1.0"


def test_no_files_generated_when_supply_chain_disabled(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_base_config())

    generated = render_supply_chain_files(config, tmp_path)

    assert generated == []
    assert not (tmp_path / "README.md").exists()


def test_supply_chain_generates_readme_scan_and_sbom(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    generated = render_supply_chain_files(config, tmp_path)

    assert [path.name for path in generated] == [
        "README.md",
        "scan-image.sh",
        "generate-sbom.sh",
    ]
    assert (tmp_path / "reports").is_dir()
    assert "weatherapi:0.1.0" in (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "trivy image --severity HIGH,CRITICAL" in (
        tmp_path / "scan-image.sh"
    ).read_text(encoding="utf-8")
    assert 'syft "weatherapi:0.1.0" -o cyclonedx-json=reports/sbom.cdx.json' in (
        tmp_path / "generate-sbom.sh"
    ).read_text(encoding="utf-8")


def test_supply_chain_generates_signing_scripts_only_when_enabled(
    tmp_path: Path,
) -> None:
    config_data = _enabled_config()
    supply_chain = config_data["supplyChain"]
    assert isinstance(supply_chain, dict)
    signing = supply_chain["signing"]
    assert isinstance(signing, dict)
    signing["enabled"] = True
    config = AppConfig.model_validate(config_data)

    generated = render_supply_chain_files(config, tmp_path)

    assert "sign-image.sh" in [path.name for path in generated]
    assert "verify-image.sh" in [path.name for path in generated]
    assert "cosign sign --yes" in (tmp_path / "sign-image.sh").read_text(
        encoding="utf-8"
    )
    assert "cosign verify" in (tmp_path / "verify-image.sh").read_text(encoding="utf-8")


def test_supply_chain_scripts_are_executable(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_supply_chain_files(config, tmp_path)

    assert (tmp_path / "scan-image.sh").stat().st_mode & 0o111
    assert (tmp_path / "generate-sbom.sh").stat().st_mode & 0o111


def test_supply_chain_uses_configured_severities_and_sbom_format(
    tmp_path: Path,
) -> None:
    config_data = _enabled_config()
    supply_chain = config_data["supplyChain"]
    assert isinstance(supply_chain, dict)
    scan = supply_chain["scan"]
    sbom = supply_chain["sbom"]
    assert isinstance(scan, dict)
    assert isinstance(sbom, dict)
    scan["severity"] = ["MEDIUM", "HIGH"]
    sbom["format"] = "spdx-json"
    config = AppConfig.model_validate(config_data)

    render_supply_chain_files(config, tmp_path)

    assert "--severity MEDIUM,HIGH" in (tmp_path / "scan-image.sh").read_text(
        encoding="utf-8"
    )
    assert "spdx-json=reports/sbom.spdx.json" in (
        tmp_path / "generate-sbom.sh"
    ).read_text(encoding="utf-8")


def test_supply_chain_output_contains_no_secret_words(tmp_path: Path) -> None:
    config = AppConfig.model_validate(_enabled_config())

    render_supply_chain_files(config, tmp_path)

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in tmp_path.iterdir()
        if path.is_file()
    ).lower()
    assert "password" not in combined
    assert "token" not in combined
    assert "private key" not in combined


def test_supply_chain_renderer_does_not_delete_user_files(tmp_path: Path) -> None:
    user_file = tmp_path / "notes.txt"
    user_file.write_text("keep me", encoding="utf-8")
    config = AppConfig.model_validate(_enabled_config())

    render_supply_chain_files(config, tmp_path)

    assert user_file.read_text(encoding="utf-8") == "keep me"
