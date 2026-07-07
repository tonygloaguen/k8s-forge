from k8s_forge.config_loader import load_app_config
from k8s_forge.studio.scaffold import (
    AssistedScaffoldRequest,
    ScaffoldValidationError,
    build_assisted_app_yaml,
    build_dockerfile_proposal,
)


def test_assisted_web_scaffold_generates_valid_app_yaml(tmp_path):
    yaml_text = build_assisted_app_yaml(
        AssistedScaffoldRequest(
            app_name="demo-api",
            namespace="demo-api",
            image="demo-api:dev",
            workload_type="deployment",
            startup_command="python -m uvicorn main:app --host 0.0.0.0 --port 8000",
            container_port=8000,
            service_enabled=True,
        )
    )
    path = tmp_path / "k8s-forge-app.yaml"
    path.write_text(yaml_text, encoding="utf-8")

    config = load_app_config(path)

    assert config.workload.type == "deployment"
    assert config.workload.command == ["python"]
    assert config.service.enabled is True


def test_assisted_job_scaffold_disables_service(tmp_path):
    yaml_text = build_assisted_app_yaml(
        AssistedScaffoldRequest(
            app_name="network-mapper",
            namespace="network-mapper",
            image="network-mapper:dev",
            workload_type="job",
            startup_command="python -m network_mapper",
            service_enabled=False,
            restart_policy="OnFailure",
        )
    )
    path = tmp_path / "k8s-forge-app.yaml"
    path.write_text(yaml_text, encoding="utf-8")

    config = load_app_config(path)

    assert config.workload.type == "job"
    assert config.workload.command == ["python"]
    assert config.workload.args == ["-m", "network_mapper"]
    assert config.service.enabled is False


def test_assisted_cronjob_requires_schedule():
    try:
        build_assisted_app_yaml(
            AssistedScaffoldRequest(
                app_name="network-mapper",
                namespace="network-mapper",
                image="network-mapper:dev",
                workload_type="cronjob",
                startup_command="python -m network_mapper",
                service_enabled=False,
                restart_policy="OnFailure",
            )
        )
    except ScaffoldValidationError as exc:
        assert "schedule" in str(exc)
    else:
        raise AssertionError("expected ScaffoldValidationError")


def test_assisted_job_rejects_enabled_service():
    try:
        build_assisted_app_yaml(
            AssistedScaffoldRequest(
                app_name="network-mapper",
                namespace="network-mapper",
                image="network-mapper:dev",
                workload_type="job",
                startup_command="python -m network_mapper",
                service_enabled=True,
                restart_policy="OnFailure",
            )
        )
    except ScaffoldValidationError as exc:
        assert "Service disabled" in str(exc)
    else:
        raise AssertionError("expected ScaffoldValidationError")


def test_dockerfile_proposal_is_not_written(tmp_path):
    proposal = build_dockerfile_proposal("job")

    assert "python:3.12-slim" in proposal
    assert "MODULE_NAME" in proposal
    assert "USER 10001:10001" in proposal
    assert "COPY --chown=10001:10001 . ." in proposal
    assert not (tmp_path / "Dockerfile").exists()


def test_dockerfile_web_proposal_contains_uvicorn():
    proposal = build_dockerfile_proposal("deployment")

    assert "uvicorn" in proposal
    assert "EXPOSE 8000" in proposal
    assert "USER 10001:10001" in proposal
    assert "COPY --chown=10001:10001 . ." in proposal
