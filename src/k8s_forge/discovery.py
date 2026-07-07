"""Static repository discovery for app.yaml scaffolding."""

from __future__ import annotations

import json
import re
import shlex
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Confidence = Literal["high", "medium", "low"]
RecommendedMode = Literal[
    "deployment-candidate",
    "review-required",
    "report-only",
    "not-linux-kubernetes-ready",
]
PortConfidence = Literal["high", "medium", "low"]
WorkloadType = Literal["deployment", "worker", "job", "cronjob"]

MAX_FILE_BYTES = 200_000
MAX_PYTHON_FILES = 200
SKIPPED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
}
SKIPPED_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pst",
    ".ost",
    ".log",
    ".pyc",
    ".pyo",
}
ROOT_FILE_NAMES = {
    "README",
    "README.md",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "package.json",
    "Dockerfile",
    "dockerfile",
    "main.py",
    "app.py",
    "manage.py",
}
SECRET_ENV_MARKERS = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "API_KEY",
    "PRIVATE_KEY",
    "CREDENTIAL",
)
GENERIC_README_ENV_WORDS = {
    "API",
    "APACHE",
    "CLI",
    "COM",
    "CONTRIBUTING",
    "CSS",
    "GET",
    "HTML",
    "HTTP",
    "HTTPS",
    "JSON",
    "LICENSE",
    "MIT",
    "POST",
    "README",
    "REST",
    "SQL",
    "URL",
    "YAML",
}

WINDOWS_PATTERNS = (
    ("pywin32", "Windows-only pywin32 dependency"),
    ("pythoncom", "Windows COM automation dependency"),
    ("win32com", "Windows COM automation dependency"),
    ("win32api", "Windows API dependency"),
    ("win32gui", "Windows GUI dependency"),
    ("outlook com", "Outlook COM desktop dependency"),
    ("microsoft outlook desktop", "Microsoft Outlook Desktop dependency"),
    ("windows 10/11", "Windows desktop operating system requirement"),
    ("windows-only", "Windows-only requirement"),
    ("%localappdata%", "Windows local application data path"),
    ("com object", "COM object dependency"),
)


@dataclass(frozen=True)
class DetectedDependency:
    """A dependency detected from repository metadata."""

    name: str
    source: str
    category: str


@dataclass(frozen=True)
class DetectedPort:
    """A port detected from repository files."""

    port: int
    source: str
    confidence: PortConfidence


@dataclass(frozen=True)
class DiscoveryWarning:
    """A non-blocking repository discovery warning."""

    code: str
    message: str
    impact: str
    recommendation: str


@dataclass(frozen=True)
class DiscoveryBlocker:
    """A blocker for direct Linux Kubernetes readiness."""

    code: str
    message: str
    impact: str
    recommendation: str


@dataclass(frozen=True)
class SuggestedAppConfig:
    """Starter app.yaml values inferred from discovery."""

    app_name: str
    namespace: str
    image: str
    replicas: int
    container_port: int
    service_port: int
    service_enabled: bool
    workload_type: WorkloadType
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    restart_policy: str = "Always"
    schedule: str = ""
    config: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RepositoryDiscoveryResult:
    """Static discovery result for an application repository."""

    app_name: str
    repo_path: Path
    inspected_files: list[str]
    languages: list[str]
    frameworks: list[str]
    dependencies: list[DetectedDependency]
    detected_ports: list[DetectedPort]
    startup_command: str | None
    dockerfile_present: bool
    requirements_present: bool
    pyproject_present: bool
    package_json_present: bool
    env_vars: list[str]
    tests_detected: bool
    ci_detected: bool
    volumes_needed: list[str]
    os_constraints: list[str]
    warnings: list[DiscoveryWarning]
    blockers: list[DiscoveryBlocker]
    confidence: Confidence
    recommended_mode: RecommendedMode
    suggested_config: SuggestedAppConfig | None
    yaml_generated: bool


@dataclass(frozen=True)
class _InspectedFile:
    path: Path
    relative_path: str
    text: str


class DiscoveryError(ValueError):
    """Raised when repository discovery cannot start."""


def discover_repository(repo_path: Path) -> RepositoryDiscoveryResult:
    """Statically inspect a repository and return a discovery result."""
    root = repo_path.expanduser().resolve()
    if not root.exists():
        msg = f"Repository path does not exist: {repo_path}"
        raise DiscoveryError(msg)
    if not root.is_dir():
        msg = f"Repository path is not a directory: {repo_path}"
        raise DiscoveryError(msg)

    files = _collect_inspected_files(root)
    text_by_name = {file.relative_path: file.text for file in files}
    all_text = "\n".join(f"{file.relative_path}\n{file.text}" for file in files)
    all_text_lower = all_text.lower()

    dependencies = _detect_dependencies(files)
    dependency_names = {dependency.name.lower() for dependency in dependencies}
    languages = _detect_languages(
        root, files, any(dependency.category == "python" for dependency in dependencies)
    )
    frameworks = _detect_frameworks(root, files, dependency_names, all_text_lower)
    detected_ports = _detect_ports(files, frameworks)
    startup_command = _detect_startup_command(root, files, frameworks, detected_ports)
    if startup_command is None and not frameworks:
        startup_command = _detect_cli_startup_command(root, files)
    suggested_workload_type = _suggest_workload_type(frameworks, startup_command)
    env_vars = _detect_env_vars(files)
    volumes_needed = _detect_volumes(files, all_text_lower)
    blockers, os_constraints = _detect_blockers(dependency_names, all_text_lower)

    dockerfile_present = (root / "Dockerfile").exists() or (
        root / "dockerfile"
    ).exists()
    requirements_present = (root / "requirements.txt").exists()
    pyproject_present = (root / "pyproject.toml").exists()
    package_json_present = (root / "package.json").exists()
    tests_detected = _tests_detected(root, files, text_by_name)
    ci_detected = any(
        file.relative_path.startswith(".github/workflows/") for file in files
    )

    warnings = _build_warnings(
        dockerfile_present=dockerfile_present,
        detected_ports=detected_ports,
        startup_command=startup_command,
        env_vars=env_vars,
        volumes_needed=volumes_needed,
        tests_detected=tests_detected,
        ci_detected=ci_detected,
        frameworks=frameworks,
    )
    if not frameworks and startup_command is None:
        blockers.append(
            DiscoveryBlocker(
                code="no-workload-shape",
                message=(
                    "No supported web framework or CLI startup command was detected."
                ),
                impact="k8s-forge cannot infer a Kubernetes workload shape reliably.",
                recommendation=(
                    "Create a Web, Worker, Job, or CronJob scaffold manually."
                ),
            )
        )
    if suggested_workload_type == "deployment" and not detected_ports:
        blockers.append(
            DiscoveryBlocker(
                code="no-port",
                message="No application port could be detected or inferred.",
                impact="A Kubernetes Service cannot be scaffolded confidently.",
                recommendation="Document the listening port or add Dockerfile EXPOSE.",
            )
        )

    confidence, recommended_mode = _resolve_confidence(
        frameworks=frameworks,
        detected_ports=detected_ports,
        startup_command=startup_command,
        blockers=blockers,
        warnings=warnings,
        suggested_workload_type=suggested_workload_type,
    )
    app_name = _normalize_name(root.name)
    selected_port = (
        detected_ports[0].port
        if detected_ports
        else _default_container_port(frameworks)
    )
    suggested_config = None
    yaml_generated = confidence in {"high", "medium"}
    if yaml_generated:
        config_values = {
            name: "review-required" for name in env_vars if not _is_secret_like(name)
        }
        if not config_values:
            config_values = {"DISCOVERY_REVIEW": "required"}
        suggested_config = SuggestedAppConfig(
            app_name=app_name,
            namespace=app_name,
            image=f"ghcr.io/example/{app_name}:0.1.0",
            replicas=1,
            container_port=selected_port,
            service_port=80,
            service_enabled=suggested_workload_type == "deployment",
            workload_type=suggested_workload_type,
            command=_command_tokens(startup_command),
            args=_argument_tokens(startup_command),
            restart_policy=(
                "OnFailure" if suggested_workload_type == "job" else "Always"
            ),
            config=config_values,
        )

    return RepositoryDiscoveryResult(
        app_name=app_name,
        repo_path=root,
        inspected_files=[file.relative_path for file in files],
        languages=languages,
        frameworks=frameworks,
        dependencies=dependencies,
        detected_ports=detected_ports,
        startup_command=startup_command,
        dockerfile_present=dockerfile_present,
        requirements_present=requirements_present,
        pyproject_present=pyproject_present,
        package_json_present=package_json_present,
        env_vars=env_vars,
        tests_detected=tests_detected,
        ci_detected=ci_detected,
        volumes_needed=volumes_needed,
        os_constraints=os_constraints,
        warnings=warnings,
        blockers=blockers,
        confidence=confidence,
        recommended_mode=recommended_mode,
        suggested_config=suggested_config,
        yaml_generated=yaml_generated,
    )


def _collect_inspected_files(root: Path) -> list[_InspectedFile]:
    candidates: list[Path] = []
    python_count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or _should_skip(path, root):
            continue
        relative = path.relative_to(root).as_posix()
        if _is_selected_static_file(path, root, relative):
            candidates.append(path)
        elif path.suffix == ".py" and python_count < MAX_PYTHON_FILES:
            candidates.append(path)
            python_count += 1
    inspected: list[_InspectedFile] = []
    for path in candidates:
        text = _read_limited_text(path)
        if text is None:
            continue
        inspected.append(
            _InspectedFile(
                path=path,
                relative_path=path.relative_to(root).as_posix(),
                text=text,
            )
        )
    return inspected


def _is_selected_static_file(path: Path, root: Path, relative: str) -> bool:
    is_root_file = path.parent == root and path.name in ROOT_FILE_NAMES
    is_workflow = relative.startswith(".github/workflows/") and path.suffix in {
        ".yml",
        ".yaml",
    }
    is_script = relative.startswith("scripts/") and path.suffix in {".ps1", ".sh"}
    return is_root_file or is_workflow or is_script


def _should_skip(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    if any(part in SKIPPED_DIRS for part in relative_parts):
        return True
    return path.suffix.lower() in SKIPPED_SUFFIXES


def _read_limited_text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()[:MAX_FILE_BYTES]
    except OSError:
        return None
    return raw.decode("utf-8", errors="ignore")


def _detect_dependencies(files: list[_InspectedFile]) -> list[DetectedDependency]:
    dependencies: dict[tuple[str, str], DetectedDependency] = {}
    for file in files:
        if file.relative_path == "requirements.txt":
            for name in _dependencies_from_requirements(file.text):
                dependencies[(name, file.relative_path)] = DetectedDependency(
                    name=name, source=file.relative_path, category="python"
                )
        elif file.relative_path == "pyproject.toml":
            for name in _dependencies_from_pyproject(file.text):
                dependencies[(name, file.relative_path)] = DetectedDependency(
                    name=name, source=file.relative_path, category="python"
                )
        elif file.relative_path == "package.json":
            for name in _dependencies_from_package_json(file.text):
                dependencies[(name, file.relative_path)] = DetectedDependency(
                    name=name, source=file.relative_path, category="node"
                )
    return sorted(dependencies.values(), key=lambda item: (item.category, item.name))


def _dependencies_from_requirements(text: str) -> list[str]:
    names: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", stripped)
        if match:
            names.append(_normalize_dependency_name(match.group(1)))
    return names


def _dependencies_from_pyproject(text: str) -> list[str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    raw_dependencies: list[str] = []
    project = data.get("project")
    if isinstance(project, dict):
        dependencies = project.get("dependencies")
        if isinstance(dependencies, list):
            raw_dependencies.extend(str(item) for item in dependencies)
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for values in optional.values():
                if isinstance(values, list):
                    raw_dependencies.extend(str(item) for item in values)
    tool = data.get("tool")
    poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
    if isinstance(poetry, dict):
        dependencies = poetry.get("dependencies")
        if isinstance(dependencies, dict):
            raw_dependencies.extend(
                str(name) for name in dependencies if name != "python"
            )
    names = []
    for dependency in raw_dependencies:
        match = re.match(r"([A-Za-z0-9_.-]+)", dependency)
        if match:
            names.append(_normalize_dependency_name(match.group(1)))
    return names


def _dependencies_from_package_json(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    names: list[str] = []
    for section in ("dependencies", "devDependencies"):
        values = data.get(section)
        if isinstance(values, dict):
            names.extend(str(name).lower() for name in values)
    return names


def _normalize_dependency_name(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _detect_languages(
    root: Path, files: list[_InspectedFile], has_python_dependencies: bool
) -> list[str]:
    languages: list[str] = []
    if has_python_dependencies or any(file.path.suffix == ".py" for file in files):
        languages.append("Python")
    if (root / "package.json").exists():
        languages.append("Node.js")
    if not languages:
        languages.append("unknown")
    return languages


def _detect_frameworks(
    root: Path,
    files: list[_InspectedFile],
    dependency_names: set[str],
    all_text_lower: str,
) -> list[str]:
    frameworks: list[str] = []
    python_text = "\n".join(file.text for file in files if file.path.suffix == ".py")
    python_text_lower = python_text.lower()
    package_json = _package_json(root)
    if (
        "fastapi" in dependency_names
        or "from fastapi import fastapi" in python_text_lower
        or "import fastapi" in python_text_lower
        or re.search(r"\bFastAPI\s*\(", python_text)
        or "uvicorn" in all_text_lower
    ):
        frameworks.append("FastAPI")
    if (
        "flask" in dependency_names
        or "from flask import flask" in python_text_lower
        or re.search(r"\bFlask\s*\(", python_text)
        or "flask run" in all_text_lower
    ):
        frameworks.append("Flask")
    if (
        "django" in dependency_names
        or (root / "manage.py").exists()
        or "runserver" in all_text_lower
    ):
        frameworks.append("Django")
    if package_json:
        dependencies = _dependencies_from_package_json(package_json)
        if "express" in dependencies:
            frameworks.append("Express")
        elif "next" in dependencies:
            frameworks.append("Next.js")
        else:
            frameworks.append("Node")
    return _unique(frameworks)


def _package_json(root: Path) -> str | None:
    path = root / "package.json"
    if not path.exists():
        return None
    return _read_limited_text(path)


def _detect_ports(
    files: list[_InspectedFile], frameworks: list[str]
) -> list[DetectedPort]:
    ports: list[DetectedPort] = []
    for file in files:
        text = file.text
        if file.path.name.lower() == "dockerfile":
            for match in re.finditer(r"(?im)^\s*EXPOSE\s+(\d{2,5})", text):
                ports.append(
                    DetectedPort(
                        int(match.group(1)), f"{file.relative_path}: EXPOSE", "high"
                    )
                )
        for match in re.finditer(r"(?i)uvicorn[^\n\r]*--port\s+(\d{2,5})", text):
            ports.append(
                DetectedPort(
                    int(match.group(1)), f"{file.relative_path}: uvicorn --port", "high"
                )
            )
        for match in re.finditer(r"(?i)flask\s+run[^\n\r]*--port\s+(\d{2,5})", text):
            ports.append(
                DetectedPort(
                    int(match.group(1)), f"{file.relative_path}: flask --port", "high"
                )
            )
        if file.relative_path == "package.json":
            for match in re.finditer(r"(?i)(?:--port\s+|PORT=)(\d{2,5})", text):
                ports.append(
                    DetectedPort(
                        int(match.group(1)), "package.json: script port", "medium"
                    )
                )
        for match in re.finditer(r"(?i)\bPORT\b\s*[:=]\s*[\"\']?(\d{2,5})", text):
            ports.append(
                DetectedPort(
                    int(match.group(1)), f"{file.relative_path}: PORT", "medium"
                )
            )
        for match in re.finditer(r"(?i)(?:localhost|127\.0\.0\.1):([0-9]{2,5})", text):
            ports.append(
                DetectedPort(
                    int(match.group(1)), f"{file.relative_path}: localhost", "medium"
                )
            )
    valid_ports = [port for port in ports if 1 <= port.port <= 65535]
    if valid_ports:
        return _dedupe_ports(valid_ports)
    fallback = _framework_default_port(frameworks)
    if fallback:
        return [DetectedPort(fallback, "framework default", "low")]
    return []


def _framework_default_port(frameworks: list[str]) -> int | None:
    if "Flask" in frameworks:
        return 5000
    if "Express" in frameworks or "Next.js" in frameworks or "Node" in frameworks:
        return 3000
    if "FastAPI" in frameworks or "Django" in frameworks:
        return 8000
    return None


def _default_container_port(frameworks: list[str]) -> int:
    return _framework_default_port(frameworks) or 8000


def _dedupe_ports(ports: list[DetectedPort]) -> list[DetectedPort]:
    seen: set[int] = set()
    deduped: list[DetectedPort] = []
    for port in ports:
        if port.port in seen:
            continue
        seen.add(port.port)
        deduped.append(port)
    return deduped


def _detect_startup_command(
    root: Path,
    files: list[_InspectedFile],
    frameworks: list[str],
    ports: list[DetectedPort],
) -> str | None:
    for file in files:
        for line in file.text.splitlines():
            command = _extract_uvicorn_command(line)
            if command:
                return _normalize_startup_host(command)
    port = ports[0].port if ports else _default_container_port(frameworks)
    if "FastAPI" in frameworks:
        if _python_file_exposes_app(root / "main.py", "FastAPI"):
            return f"python -m uvicorn main:app --host 0.0.0.0 --port {port}"
        if _python_file_exposes_app(root / "app.py", "FastAPI"):
            return f"python -m uvicorn app:app --host 0.0.0.0 --port {port}"
    if "Flask" in frameworks:
        return f"python -m flask run --host 0.0.0.0 --port {port}"
    if "Django" in frameworks and (root / "manage.py").exists():
        return f"python manage.py runserver 0.0.0.0:{port}"
    if any(framework in frameworks for framework in ("Express", "Next.js", "Node")):
        package_json = _package_json(root)
        if package_json and '"start"' in package_json:
            return "npm start"
    return None


def _detect_cli_startup_command(root: Path, files: list[_InspectedFile]) -> str | None:
    pyproject = _read_limited_text(root / "pyproject.toml")
    if pyproject:
        script = _script_command_from_pyproject(pyproject)
        if script:
            return script
    root_python_files = [
        file.path
        for file in files
        if file.path.parent == root
        and file.path.suffix == ".py"
        and file.path.name not in {"setup.py", "conftest.py"}
    ]
    if (root / "main.py").exists():
        return "python main.py"
    if len(root_python_files) == 1:
        return f"python {root_python_files[0].name}"
    return None


def _script_command_from_pyproject(text: str) -> str | None:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    scripts = project.get("scripts")
    if not isinstance(scripts, dict) or not scripts:
        return None
    name, target = next(iter(scripts.items()))
    if not isinstance(target, str) or ":" not in target:
        return str(name)
    module, _, function = target.partition(":")
    return f"python -c 'import {module}; {module}.{function}()'"


def _suggest_workload_type(
    frameworks: list[str], startup_command: str | None
) -> WorkloadType:
    if frameworks:
        return "deployment"
    if startup_command:
        return "job"
    return "deployment"


def _command_tokens(command: str | None) -> list[str]:
    if not command:
        return []
    try:
        parts = shlex.split(command)
    except ValueError:
        return []
    return parts[:1]


def _argument_tokens(command: str | None) -> list[str]:
    if not command:
        return []
    try:
        parts = shlex.split(command)
    except ValueError:
        return []
    return parts[1:]


def _extract_uvicorn_command(line: str) -> str | None:
    match = re.search(
        r"(?i)(?:^|[`\s])(python\s+-m\s+uvicorn\s+[^`]+|uvicorn\s+[^`]+)",
        line.strip(),
    )
    if not match:
        return None
    command = match.group(1).strip().strip("`")
    if ":" not in command:
        return None
    return command


def _normalize_startup_host(command: str) -> str:
    if "--host" in command:
        return re.sub(r"--host\s+\S+", "--host 0.0.0.0", command)
    if "uvicorn" in command:
        return f"{command} --host 0.0.0.0"
    return command


def _python_file_exposes_app(path: Path, factory_name: str) -> bool:
    text = _read_limited_text(path) if path.exists() else None
    if not text:
        return False
    return bool(re.search(rf"\bapp\s*=\s*{factory_name}\s*\(", text))


def _detect_env_vars(files: list[_InspectedFile]) -> list[str]:
    code_env_vars: set[str] = set()
    readme_texts: list[str] = []
    for file in files:
        code_env_vars.update(_python_env_vars(file.text))
        if _is_readme(file):
            readme_texts.append(file.text)

    prefixes = _env_prefixes(code_env_vars)
    readme_env_vars: set[str] = set()
    for text in readme_texts:
        readme_env_vars.update(_readme_env_vars(text, prefixes))

    env_vars = code_env_vars | readme_env_vars
    return sorted(var for var in env_vars if _is_plausible_env_var(var))


def _python_env_vars(text: str) -> set[str]:
    env_vars: set[str] = set()
    for pattern in (
        r"os\.getenv\(\s*[\"']([A-Z][A-Z0-9_]{2,})[\"']",
        r"os\.environ\.get\(\s*[\"']([A-Z][A-Z0-9_]{2,})[\"']",
        r"os\.environ\[\s*[\"']([A-Z][A-Z0-9_]{2,})[\"']\s*\]",
    ):
        env_vars.update(re.findall(pattern, text))
    return env_vars


def _is_readme(file: _InspectedFile) -> bool:
    name = file.relative_path.lower()
    return name == "readme" or name.startswith("readme.")


def _readme_env_vars(text: str, prefixes: set[str]) -> set[str]:
    env_vars: set[str] = set()
    env_section = _readme_environment_section(text)
    if env_section:
        env_vars.update(_uppercase_underscore_names(env_section))
    for candidate in _uppercase_underscore_names(text):
        if any(candidate.startswith(f"{prefix}_") for prefix in prefixes):
            env_vars.add(candidate)
    return env_vars


def _uppercase_underscore_names(text: str) -> set[str]:
    return set(re.findall(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b", text))


def _env_prefixes(env_vars: set[str]) -> set[str]:
    prefixes: set[str] = set()
    for name in env_vars:
        parts = name.split("_")
        if len(parts) >= 3:
            prefixes.add("_".join(parts[:2]))
        if len(parts) >= 2:
            prefixes.add(parts[0])
    return prefixes


def _readme_environment_section(text: str) -> str:
    lines = text.splitlines()
    captured: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        is_heading = stripped.startswith("#")
        normalized = stripped.strip("# ").lower()
        if is_heading:
            if in_section:
                break
            in_section = normalized in {
                "environment",
                "environment variables",
                "configuration",
                "configuration variables",
            }
            continue
        if in_section:
            captured.append(line)
    return "\n".join(captured)


def _is_plausible_env_var(name: str) -> bool:
    if name in GENERIC_README_ENV_WORDS:
        return False
    return "_" in name or name.startswith(("PORT", "HOST"))


def _detect_volumes(files: list[_InspectedFile], all_text_lower: str) -> list[str]:
    volumes: list[str] = []
    if re.search(r"\b(sqlite|sqlite3)\b|\.sqlite\b|\.db\b", all_text_lower):
        volumes.append("SQLite or local database file")
    for marker, label in (
        ("uploads", "uploads directory"),
        ("attachments", "attachments directory"),
        ("local data", "local data directory"),
        ("localappdata", "local application data directory"),
    ):
        if marker in all_text_lower:
            volumes.append(label)
    if any(
        "open(" in file.text or ".write_text(" in file.text
        for file in files
        if file.path.suffix == ".py"
    ):
        volumes.append("application file writes")
    return _unique(volumes)


def _detect_blockers(
    dependency_names: set[str], all_text_lower: str
) -> tuple[list[DiscoveryBlocker], list[str]]:
    blockers: list[DiscoveryBlocker] = []
    constraints: list[str] = []
    for pattern, message in WINDOWS_PATTERNS:
        normalized = pattern.lower()
        normalized_dependency = _normalize_dependency_name(pattern)
        matched = (
            normalized_dependency in dependency_names or normalized in all_text_lower
        )
        if not matched:
            continue
        constraints.append(message)
        blockers.append(
            DiscoveryBlocker(
                code=_normalize_name(pattern),
                message=message,
                impact=(
                    "This signal usually prevents direct Linux Kubernetes "
                    "deployment of the full application."
                ),
                recommendation=(
                    "Split Linux-containerizable HTTP components from Windows "
                    "or desktop-specific workers."
                ),
            )
        )
    if re.search(r"[A-Za-z]:\\", all_text_lower):
        constraints.append("Windows absolute path")
        blockers.append(
            DiscoveryBlocker(
                code="windows-path",
                message="Windows absolute paths were detected.",
                impact="Hard-coded local paths do not map cleanly to Linux containers.",
                recommendation=(
                    "Move path configuration into environment variables and "
                    "review persistence needs."
                ),
            )
        )
    if "powershell" in all_text_lower or ".ps1" in all_text_lower:
        constraints.append("PowerShell script dependency")
        blockers.append(
            DiscoveryBlocker(
                code="powershell-script",
                message="PowerShell-oriented scripts were detected.",
                impact="Startup or operational scripts may be Windows-specific.",
                recommendation=(
                    "Provide Linux-compatible container entrypoints before deployment."
                ),
            )
        )
    if "desktop gui" in all_text_lower or "gui" in all_text_lower:
        constraints.append("Desktop GUI dependency")
        blockers.append(
            DiscoveryBlocker(
                code="desktop-gui",
                message="Desktop GUI dependency was detected.",
                impact=(
                    "GUI dependencies are not suitable for a normal Linux web "
                    "container."
                ),
                recommendation=(
                    "Separate GUI or desktop automation from the web API service."
                ),
            )
        )
    return _dedupe_blockers(blockers), _unique(constraints)


def _build_warnings(
    *,
    dockerfile_present: bool,
    detected_ports: list[DetectedPort],
    startup_command: str | None,
    env_vars: list[str],
    volumes_needed: list[str],
    tests_detected: bool,
    ci_detected: bool,
    frameworks: list[str],
) -> list[DiscoveryWarning]:
    warnings: list[DiscoveryWarning] = []
    if not dockerfile_present:
        warnings.append(
            DiscoveryWarning(
                "dockerfile-missing",
                "No Dockerfile was detected.",
                "The generated image reference is a placeholder.",
                "Create and review a Dockerfile before building an image.",
            )
        )
    if detected_ports and detected_ports[0].confidence == "low":
        warnings.append(
            DiscoveryWarning(
                "port-inferred",
                f"Port {detected_ports[0].port} was inferred from framework defaults.",
                "The application may listen on a different port.",
                "Document the port explicitly or add Dockerfile EXPOSE.",
            )
        )
    if startup_command is None:
        warnings.append(
            DiscoveryWarning(
                "startup-unknown",
                "No reliable startup command was detected.",
                (
                    "The generated scaffold cannot describe how the container "
                    "should start."
                ),
                "Document the startup command before building an image.",
            )
        )
    if env_vars:
        warnings.append(
            DiscoveryWarning(
                "env-vars-detected",
                "Environment variables were detected.",
                "Values need manual review and sensitive values must not be generated.",
                (
                    "Move non-sensitive values to config and sensitive values "
                    "to an external secret workflow."
                ),
            )
        )
    if volumes_needed:
        warnings.append(
            DiscoveryWarning(
                "local-persistence",
                "Local persistence or file writes were detected.",
                "Container restarts may lose local state without a storage design.",
                (
                    "Review whether a PVC, external database, or external "
                    "storage service is needed."
                ),
            )
        )
    if not tests_detected:
        warnings.append(
            DiscoveryWarning(
                "tests-missing",
                "No tests were detected.",
                "CI readiness may need project-specific test commands.",
                "Add tests or document validation commands.",
            )
        )
    if ci_detected:
        warnings.append(
            DiscoveryWarning(
                "ci-detected",
                "Existing CI workflows were detected.",
                "Generated CI readiness should be reviewed against current workflows.",
                "Avoid overwriting existing CI without review.",
            )
        )
    if not frameworks:
        warnings.append(
            DiscoveryWarning(
                "framework-unconfirmed",
                "No supported web framework was confirmed.",
                "The repository may not be an HTTP application.",
                "Use a manual app.yaml or document the framework/startup command.",
            )
        )
    return warnings


def _resolve_confidence(
    *,
    frameworks: list[str],
    detected_ports: list[DetectedPort],
    startup_command: str | None,
    blockers: list[DiscoveryBlocker],
    warnings: list[DiscoveryWarning],
    suggested_workload_type: WorkloadType,
) -> tuple[Confidence, RecommendedMode]:
    has_framework = bool(frameworks)
    has_port = bool(detected_ports)
    explicit_port = has_port and detected_ports[0].confidence in {"high", "medium"}
    has_startup = startup_command is not None
    has_major_blocker = bool(blockers)
    if suggested_workload_type == "job":
        if has_major_blocker:
            return "low", "not-linux-kubernetes-ready"
        if has_startup:
            return "medium", "review-required"
        return "low", "report-only"
    if not has_framework or not has_port:
        return "low", "report-only"
    if has_major_blocker:
        if explicit_port and has_startup:
            return "medium", "not-linux-kubernetes-ready"
        return "low", "not-linux-kubernetes-ready"
    if explicit_port and has_startup and not warnings:
        return "high", "deployment-candidate"
    if explicit_port and has_startup:
        return "medium", "review-required"
    return "medium", "review-required"


def _tests_detected(
    root: Path, files: list[_InspectedFile], text_by_name: dict[str, str]
) -> bool:
    if (root / "tests").exists() or (root / "test").exists():
        return True
    if any(
        file.path.name.startswith("test_") and file.path.suffix == ".py"
        for file in files
    ):
        return True
    package_json = text_by_name.get("package.json")
    if package_json and '"test"' in package_json:
        return True
    return "pytest" in text_by_name.get("requirements.txt", "").lower()


def _normalize_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "discovered-app"


def _is_secret_like(name: str) -> bool:
    upper = name.upper()
    return any(marker in upper for marker in SECRET_ENV_MARKERS)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _dedupe_blockers(blockers: list[DiscoveryBlocker]) -> list[DiscoveryBlocker]:
    seen: set[str] = set()
    result: list[DiscoveryBlocker] = []
    for blocker in blockers:
        key = blocker.code
        if key in seen:
            continue
        seen.add(key)
        result.append(blocker)
    return result
