from pathlib import Path

import pytest

from k8s_forge.discovery import DiscoveryError, discover_repository


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def blocker_codes(repo: Path) -> set[str]:
    result = discover_repository(repo)
    return {blocker.code for blocker in result.blockers}


def test_discover_fastapi_repository(tmp_path: Path) -> None:
    repo = tmp_path / "weather-api"
    write(repo / "requirements.txt", "fastapi\nuvicorn\npytest\n")
    write(
        repo / "main.py",
        "from fastapi import FastAPI\n\napp = FastAPI()\n",
    )
    write(repo / "README.md", "Run with uvicorn main:app --port 8010\n")
    write(repo / "tests" / "test_app.py", "def test_ok():\n    assert True\n")

    result = discover_repository(repo)

    assert result.app_name == "weather-api"
    assert result.languages == ["Python"]
    assert "FastAPI" in result.frameworks
    assert result.detected_ports[0].port == 8010
    assert result.detected_ports[0].confidence == "high"
    assert result.startup_command == "uvicorn main:app --port 8010 --host 0.0.0.0"
    assert result.confidence == "medium"
    assert result.recommended_mode == "review-required"
    assert result.yaml_generated is True


def test_discover_dockerfile_expose_takes_strong_port_signal(tmp_path: Path) -> None:
    repo = tmp_path / "docker-fastapi"
    write(repo / "requirements.txt", "fastapi\nuvicorn\npytest\n")
    write(repo / "Dockerfile", "FROM python:3.12-slim\nEXPOSE 9000\n")
    write(repo / "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")

    result = discover_repository(repo)

    assert result.detected_ports[0].port == 9000
    assert result.detected_ports[0].source == "Dockerfile: EXPOSE"
    assert result.startup_command.endswith("--port 9000")


def test_discover_flask_repository(tmp_path: Path) -> None:
    repo = tmp_path / "flask-api"
    write(repo / "requirements.txt", "flask\npytest\n")
    write(repo / "app.py", "from flask import Flask\napp = Flask(__name__)\n")
    write(repo / "README.md", "Use flask run --port 5050 locally.\n")

    result = discover_repository(repo)

    assert "Flask" in result.frameworks
    assert result.detected_ports[0].port == 5050
    assert result.startup_command == "python -m flask run --host 0.0.0.0 --port 5050"


def test_discover_django_repository(tmp_path: Path) -> None:
    repo = tmp_path / "django-api"
    write(repo / "requirements.txt", "django\npytest\n")
    write(repo / "manage.py", "#!/usr/bin/env python\n")

    result = discover_repository(repo)

    assert "Django" in result.frameworks
    assert result.detected_ports[0].port == 8000
    assert result.detected_ports[0].confidence == "low"
    assert result.startup_command == "python manage.py runserver 0.0.0.0:8000"


def test_discover_node_express_repository(tmp_path: Path) -> None:
    repo = tmp_path / "node-api"
    write(
        repo / "package.json",
        """
        {
          "scripts": {"start": "node server.js --port 3001", "test": "node --test"},
          "dependencies": {"express": "^4.18.0"}
        }
        """,
    )

    result = discover_repository(repo)

    assert result.languages == ["Node.js"]
    assert "Express" in result.frameworks
    assert result.detected_ports[0].port == 3001
    assert result.startup_command == "npm start"
    assert result.tests_detected is True


def test_discover_python_without_web_framework_is_report_only(tmp_path: Path) -> None:
    repo = tmp_path / "worker"
    write(repo / "requirements.txt", "pytest\n")
    write(repo / "worker.py", "print('background job')\n")

    result = discover_repository(repo)

    assert result.confidence == "low"
    assert result.recommended_mode == "report-only"
    assert result.yaml_generated is False
    assert "no-web-framework" in {blocker.code for blocker in result.blockers}


@pytest.mark.parametrize("marker", ["pywin32", "pythoncom", "win32com", "win32api"])
def test_discover_windows_dependency_blockers(tmp_path: Path, marker: str) -> None:
    repo = tmp_path / f"windows-{marker}"
    write(repo / "requirements.txt", f"fastapi\nuvicorn\n{marker}\n")
    write(
        repo / "main.py",
        f"from fastapi import FastAPI\nimport {marker}\napp = FastAPI()\n",
    )
    write(repo / "README.md", "Run uvicorn main:app --port 8000\n")

    codes = blocker_codes(repo)

    assert marker.replace("_", "-") in codes


def test_discover_readme_windows_outlook_and_powershell_blockers(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "windows-desktop-api"
    write(repo / "requirements.txt", "fastapi\nuvicorn\n")
    write(repo / "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    write(
        repo / "README.md",
        """
        Run uvicorn main:app --port 8000.
        Requires Windows 10/11, Microsoft Outlook Desktop, Outlook COM,
        %LOCALAPPDATA%, C:\\Users\\example\\data, and a desktop GUI session.
        """,
    )
    write(repo / "scripts" / "start.ps1", "Write-Host 'start'\n")

    result = discover_repository(repo)

    assert result.recommended_mode == "not-linux-kubernetes-ready"
    assert result.yaml_generated is True
    assert "Microsoft Outlook Desktop dependency" in result.os_constraints
    assert {"microsoft-outlook-desktop", "windows-path", "powershell-script"} <= {
        blocker.code for blocker in result.blockers
    }


def test_discover_sqlite_and_file_write_warning(tmp_path: Path) -> None:
    repo = tmp_path / "sqlite-api"
    write(repo / "requirements.txt", "fastapi\nuvicorn\n")
    write(
        repo / "main.py",
        """
        from fastapi import FastAPI
        import sqlite3
        app = FastAPI()
        open("local.db", "w").write("demo")
        """,
    )

    result = discover_repository(repo)

    assert "SQLite or local database file" in result.volumes_needed
    assert "application file writes" in result.volumes_needed
    assert "local-persistence" in {warning.code for warning in result.warnings}


def test_discover_env_vars_without_sensitive_values(tmp_path: Path) -> None:
    repo = tmp_path / "env-api"
    write(repo / "requirements.txt", "fastapi\nuvicorn\n")
    write(
        repo / "main.py",
        """
        import os
        from fastapi import FastAPI
        app = FastAPI()
        backend = os.getenv("OLLAMA_BASE_URL")
        token = os.environ["API_TOKEN"]
        """,
    )

    result = discover_repository(repo)

    assert "OLLAMA_BASE_URL" in result.env_vars
    assert "API_TOKEN" in result.env_vars
    assert result.suggested_config is not None
    assert result.suggested_config.config["OLLAMA_BASE_URL"] == "review-required"
    assert "API_TOKEN" not in result.suggested_config.config


def test_discover_ci_detected(tmp_path: Path) -> None:
    repo = tmp_path / "ci-api"
    write(repo / "requirements.txt", "fastapi\nuvicorn\npytest\n")
    write(repo / "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    write(repo / ".github" / "workflows" / "ci.yml", "name: ci\n")

    result = discover_repository(repo)

    assert result.ci_detected is True
    assert "ci-detected" in {warning.code for warning in result.warnings}


def test_discover_missing_path_errors(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="does not exist"):
        discover_repository(tmp_path / "missing")


def test_discover_file_path_errors(tmp_path: Path) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text("not a repository", encoding="utf-8")

    with pytest.raises(DiscoveryError, match="not a directory"):
        discover_repository(file_path)
