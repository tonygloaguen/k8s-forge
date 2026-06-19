# k8s-forge

`k8s-forge` is a generic Python CLI for generating Kubernetes manifests for
stateless containerized web applications from a user-owned `app.yaml` file.

Status: local MVP. The project is ready to install and test locally, but it is
not a full deployment platform and does not replace Kubernetes or `kubectl`.

The project is intentionally application-agnostic. Application-specific values
must come from `app.yaml`; implementation logic must not hardcode an application
name.

## What It Does

`k8s-forge` can:

- create a starter `app.yaml` with `init`;
- validate `app.yaml` with Pydantic models;
- render Kubernetes YAML manifests locally;
- run guarded `kubectl` workflows for `dry-run`, `diff`, `apply`, and `status`;
- check local Docker/kind/kubectl prerequisites and manage a local kind cluster;
- keep generated manifests inspectable before cluster operations.

## MVP Scope

Included:

- `init`
- `check`
- `render`
- `dry-run`
- `diff`
- `apply` with confirmation
- `status`
- `doctor`
- `cluster create`, `cluster status`, `cluster delete` for kind
- `image load` for loading local Docker images into kind
- generation of Namespace, ConfigMap, Secret, Deployment, and Service

Out of scope:

- Ingress
- HPA
- NetworkPolicy
- Helm
- Kustomize
- LangGraph
- real secret management
- Python Kubernetes client
- Kubernetes operator behavior

## Local Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
k8s-forge --help
```

## Quick Example

```bash
k8s-forge doctor
k8s-forge cluster create --name devsecops
k8s-forge cluster status --name devsecops
k8s-forge init demo-app
k8s-forge check app.yaml
k8s-forge render app.yaml --output generated/
k8s-forge image load demo-app:latest --cluster devsecops
k8s-forge dry-run app.yaml --output generated/
k8s-forge diff app.yaml --output generated/
k8s-forge apply app.yaml --output generated/
k8s-forge status demo-app -n demo-app
```

`demo-app` is only a documentation example. Real values should come from the
user's configuration.

## Main Commands

```bash
k8s-forge doctor
k8s-forge cluster create --name devsecops
k8s-forge cluster status --name devsecops
k8s-forge cluster delete --name devsecops
k8s-forge image load demo-app:latest --cluster devsecops
k8s-forge init demo-app
k8s-forge init demo-app --namespace demo --image demo-app:1.0.0 --port 8000
k8s-forge check app.yaml
k8s-forge render app.yaml --output generated/
k8s-forge dry-run app.yaml --output generated/
k8s-forge diff app.yaml --output generated/
k8s-forge apply app.yaml --output generated/
k8s-forge apply app.yaml --output generated/ --yes
k8s-forge status demo-app -n demo-app
```

## Generated Kubernetes Objects

For a complete configuration, `render` writes:

```text
generated/00-namespace.yaml
generated/10-configmap.yaml
generated/20-secret.yaml
generated/30-deployment.yaml
generated/40-service.yaml
```

Optional resources are generated only when enabled by `app.yaml`:

- ConfigMap is rendered only when `config` is non-empty.
- Secret is rendered only when `secrets` is non-empty.
- Service is rendered only when `service.enabled` is `true`.

Known generated files are overwritten on each render. Files with other names in
the output directory are left untouched.

## Local kind Bootstrap

`k8s-forge doctor` checks Docker, kind, kubectl, the current context, and
visible nodes.
`k8s-forge cluster create --name devsecops` creates a local kind cluster when it
does not already exist. `k8s-forge image load IMAGE --cluster devsecops` loads a
local Docker image into that kind cluster.

## Guardrails

- `check` validates the configuration before rendering.
- `render` only writes local YAML files.
- `dry-run` asks the Kubernetes API server to validate manifests without
  applying them.
- `diff` shows what would change before applying.
- `apply` asks for confirmation unless `--yes` is passed.
- `kubectl` calls go through one wrapper using `subprocess.run` without
  `shell=True`.
- Tests mock `kubectl` and must not depend on a real Kubernetes cluster.

## Secrets Warning

Do not commit real secrets. Values placed in `app.yaml` or generated manifests
may be stored in plain text during the MVP. The MVP uses Kubernetes
`stringData` for readability and should only be used with placeholder values in
examples and tests.

## Documentation

- [Getting started](docs/getting-started.md)
- [Configuration reference](docs/config-reference.md)
- [Operational workflow](docs/operations.md)
- [Design notes](docs/design.md)

## Development

Install with development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run checks:

```bash
ruff format --check .
ruff check .
mypy src
bandit -r src
pip-audit --skip-editable
pytest -q
```
