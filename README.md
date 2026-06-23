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
- generate a local Helm chart from the same `app.yaml`;
- generate optional Ingress-NGINX compatible Ingress resources;
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
- `helm render` for generating a local Helm chart
- generation of Namespace, ConfigMap, Secret, Deployment, Service, optional HorizontalPodAutoscaler, and optional Ingress

Out of scope:

- NetworkPolicy
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
k8s-forge helm render app.yaml --output charts/
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
k8s-forge helm render app.yaml --output charts/
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
generated/50-hpa.yaml        # only when autoscaling.enabled is true
```

Optional resources are generated only when enabled by `app.yaml`:

- ConfigMap is rendered only when `config` is non-empty.
- Secret is rendered only when `secrets` is non-empty.
- Service is rendered only when `service.enabled` is `true`.
- HorizontalPodAutoscaler is rendered only when `autoscaling.enabled` is `true`.

Known generated files are overwritten on each render. Files with other names in
the output directory are left untouched.


## Generated Helm Chart

`k8s-forge helm render app.yaml --output charts/` writes a local chart to
`charts/<app.name>/`. The chart includes `Chart.yaml`, `values.yaml`, and Helm
templates for ConfigMap, Secret, Deployment, Service, and HPA. It does not
contact the cluster and does not run `helm` automatically.

After generation, validate manually:

```bash
helm lint charts/demo-app
helm template demo-app charts/demo-app -n demo-app
```

## Module 3 Ingress

When `ingress.enabled` is true, `k8s-forge` renders raw and Helm Ingress resources for an existing ingress-nginx controller. It does not install ingress-nginx, cert-manager, ClusterIssuers, DNS, or `/etc/hosts` entries.

## Local kind Bootstrap

`k8s-forge doctor` checks Docker, kind, kubectl, the current context, and
visible nodes.
`k8s-forge cluster create --name devsecops` creates a local kind cluster when it
does not already exist. `k8s-forge image load IMAGE --cluster devsecops` loads a
local Docker image into that kind cluster.

## Pedagogical CLI Output

`k8s-forge` intentionally prints short explanations before important actions.
The goal is to make the raw Kubernetes workflow understandable: local rendering,
server-side dry-run, apply, Deployment replicas, Services, HPA, and
metrics-server status. These messages are educational and do not change the
underlying manifests or kubectl commands.

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
- [Debian/Ubuntu installation](docs/debian-install.md)
- [Configuration reference](docs/config-reference.md)
- [Operational workflow](docs/operations.md)
- [Module 2 Kubernetes raw workflow](docs/module-2-kubernetes.md)
- [Module 2 Helm workflow](docs/module-2-helm.md)
- [Module 3 Ingress workflow](docs/module-3-ingress.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Real app case study: weatherapi-platform](docs/real-app-weatherapi.md)
- [Design notes](docs/design.md)
- [Release checklist](docs/release-checklist.md)

## Local Release Check

Build the package and verify it installs into a clean temporary virtualenv:

```bash
python -m build
bash scripts/check_release.sh
```

The release check verifies wheel/sdist creation, installation of the wheel, the
`k8s-forge` console command, and manifest generation from the installed wheel.
It does not call `kubectl apply` and does not require a Kubernetes cluster.

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
