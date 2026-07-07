# Module 15 - Repository Discovery readiness

Repository Discovery helps bootstrap a first `k8s-forge-app.yaml` from an existing application repository. It is a static analysis feature: it reads bounded project files, writes local discovery artifacts, and leaves the application repository untouched unless the chosen output directory points inside it.

## Command

```bash
k8s-forge discover PATH --output generated-discovery/ --force
```

`PATH` must be a local directory. `--output` defaults to `generated-discovery/`. Without `--force`, existing generated files are not overwritten.

## Generated files

```text
generated-discovery/
  discovery-report.md
  warnings.md
  k8s-forge-app.yaml
```

`k8s-forge-app.yaml` is generated only when confidence is `high` or `medium`. Low-confidence repositories receive the report and warnings only.

The YAML is a starter configuration, a readiness scaffold, and review-required material. It is not deployment-ready by default and does not prove that the application is compatible with Kubernetes.

## Static signals

Discovery inspects a small, bounded set of files:

- README files;
- `requirements.txt`, `pyproject.toml`, `setup.py`;
- `package.json`;
- `Dockerfile` or `dockerfile`;
- root `main.py`, `app.py`, `manage.py`;
- a limited number of Python files;
- `.github/workflows/*.yml` and `.github/workflows/*.yaml`;
- `scripts/*.sh` and `scripts/*.ps1`.

It skips large or generated areas such as `.git/`, virtual environments, `node_modules/`, `dist/`, `build/`, caches, database files, logs, PST/OST files, and other binary-looking artifacts.

## Detected application shape

The first implementation detects these broad shapes:

| Area | Signals |
| --- | --- |
| Python | Python dependency files, setup files, Python source files |
| Node.js | `package.json` |
| FastAPI | `fastapi`, `FastAPI(...)`, FastAPI imports, Uvicorn hints |
| Flask | `flask`, Flask imports, `Flask(...)`, `flask run` |
| Django | `django`, `manage.py`, `runserver` |
| Express | `express` dependency |
| Next.js | `next` dependency |

The rules are generic. They must not special-case a real repository name or application name.

## Port detection

Ports are selected from the strongest available signal:

1. `Dockerfile EXPOSE`;
2. `uvicorn ... --port`;
3. `flask run --port`;
4. `package.json` scripts with `--port` or `PORT=`;
5. generic `PORT` assignments;
6. README localhost URLs;
7. framework defaults: FastAPI/Django `8000`, Flask `5000`, Node/Express `3000`.

Inferred ports are reported as warnings because they may not match runtime behavior.

## Warnings and blockers

Warnings are review items that do not necessarily prevent a scaffold:

- missing Dockerfile;
- inferred port;
- inferred or missing startup command;
- environment variable names detected;
- SQLite or local file persistence;
- missing tests;
- existing CI that needs review.

Blockers are stronger signals that direct Linux Kubernetes deployment may not be appropriate:

- `pywin32`;
- `pythoncom`, `win32com`, `win32api`, `win32gui`;
- Outlook COM or Microsoft Outlook Desktop dependencies;
- Windows-only requirements;
- PowerShell-oriented startup;
- Windows local paths;
- desktop GUI dependencies;
- no supported web framework;
- no port detected.

Blockers do not prevent report generation. They change the recommended mode and may suppress YAML generation when confidence is low.

## Confidence

| Confidence | Meaning | Output |
| --- | --- | --- |
| `high` | Framework, explicit port, and plausible startup command with no major blockers | report, warnings, YAML |
| `medium` | Useful scaffold but review is required because of warnings, inferred data, or non-Linux blockers with enough HTTP evidence | report, warnings, YAML |
| `low` | Ambiguous repository, missing HTTP shape, missing port, or major blockers with insufficient confidence | report and warnings only |

Recommended modes are:

- `deployment-candidate`;
- `review-required`;
- `report-only`;
- `not-linux-kubernetes-ready`.

These modes are guidance for review. They are not runtime validation.

## Starter YAML

The generated YAML uses conservative values:

- normalized app name and namespace;
- placeholder image `ghcr.io/example/<app>:0.1.0`;
- one replica;
- detected or inferred container port;
- ClusterIP-style Service model used by `k8s-forge`;
- non-sensitive environment variables with review-required placeholder values;
- `secrets: {}`;
- optional readiness modules disabled.

Sensitive-looking variable names are reported but not rendered with values.

## Boundaries

`discover` does not:

- execute application code;
- install dependencies;
- build container images;
- inspect real runtime behavior;
- contact Kubernetes;
- contact a cloud provider;
- modify the analyzed repository;
- create commits or push code;
- deploy anything;
- create real secrets.

Manual review is required before using the generated `k8s-forge-app.yaml` with `check`, `render`, or any runtime workflow.

## Suggested workflow

```bash
k8s-forge discover /path/to/repo --output generated-discovery/
cat generated-discovery/discovery-report.md
cat generated-discovery/warnings.md
cp generated-discovery/k8s-forge-app.yaml ./k8s-forge-app.yaml
k8s-forge check k8s-forge-app.yaml
```

Only copy or adapt the YAML after reviewing warnings, blockers, image placeholder, ports, startup command assumptions, environment variables, and persistence needs.
