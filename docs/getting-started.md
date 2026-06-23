# Getting Started

## Debian/Ubuntu Prerequisites

On Debian or Ubuntu, install venv support before creating `.venv`:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
```

If your distribution uses a version-specific Python package, install the
matching venv package, for example `python3.13-venv`.

Create the project directory before cloning if it does not exist:

```bash
mkdir -p ~/projets
cd ~/projets
```

Read [debian-install.md](debian-install.md) for the complete Debian/Ubuntu setup
and common installation errors such as `ensurepip is not available`, missing
`.venv/bin/activate`, or `k8s-forge: command not found`.

## Install Locally

```bash
python -m pip install -e ".[dev]"
```

## Check The CLI

```bash
k8s-forge --help
```

The CLI can initialize, validate, render, and run guarded kubectl workflows.

## Basic Flow

```bash
k8s-forge doctor
k8s-forge cluster create --name devsecops
k8s-forge init demo-app
k8s-forge check app.yaml
k8s-forge render app.yaml --output generated/
k8s-forge helm render app.yaml --output charts/
k8s-forge image load demo-app:latest --cluster devsecops
k8s-forge dry-run app.yaml --output generated/
```

After creating a kind cluster, `k8s-forge` waits for nodes to become Ready.
During `dry-run`, it warns if the configured namespace does not really exist
because server-side dry-run does not persist the generated Namespace manifest.

`init` generates a generic configuration base to adapt before use. `demo-app`
is only an example name; real values should come from the user's `app.yaml`.

Read [config-reference.md](config-reference.md) for the full `app.yaml` format,
field constraints, and examples.

For real existing applications, keep `k8s-forge` files separate from existing
Kubernetes or Helm assets. Use a dedicated config such as `k8s-forge-app.yaml`
and render into a dedicated directory such as `generated-k8s-forge/`. See
[real-app-weatherapi.md](real-app-weatherapi.md) for a tested FastAPI example.

## Module 2 Kubernetes

For the raw Kubernetes training workflow with multiple replicas, HPA,
metrics-server notes, and Pod reconciliation, read
[module-2-kubernetes.md](module-2-kubernetes.md).


## Module 2 Helm

After understanding the raw Kubernetes resources, generate a local Helm chart
from the same `app.yaml`:

```bash
k8s-forge helm render app.yaml --output charts/
helm lint charts/demo-app
helm template demo-app charts/demo-app -n demo-app
```

Read [module-2-helm.md](module-2-helm.md) for chart structure, validation, and
migration from raw `k8s-forge` resources.

## Module 3 Ingress

For HTTP routing with ingress-nginx and optional cert-manager annotations, read [module-3-ingress.md](module-3-ingress.md). `k8s-forge` renders Ingress resources but does not install ingress-nginx, cert-manager, or edit `/etc/hosts`.

## Module 3 Linkerd

For service mesh readiness with Linkerd, read [module-3-linkerd.md](module-3-linkerd.md). `k8s-forge` can annotate the Deployment pod template for Linkerd injection, but it does not install Linkerd or run `linkerd inject`.

## Module 4 NetworkPolicy

For Kubernetes network security readiness, read [module-4-networkpolicy.md](module-4-networkpolicy.md). `k8s-forge` renders an ingress-only policy but does not install or replace the CNI plugin.

## Next Step: Operational Workflow

After generating and validating `app.yaml`, read [operations.md](operations.md)
for the recommended `dry-run`, `diff`, `apply`, and `status` workflow against a
real Kubernetes cluster.

## Documentation

- [Debian/Ubuntu installation](debian-install.md)
- [Troubleshooting](troubleshooting.md)
- [Real app case study](real-app-weatherapi.md)
- [Configuration reference](config-reference.md)
- [Operational workflow](operations.md)
- [Module 2 Kubernetes raw workflow](module-2-kubernetes.md)
- [Module 2 Helm workflow](module-2-helm.md)
- [Module 3 Ingress workflow](module-3-ingress.md)
- [Module 3 Linkerd service mesh workflow](module-3-linkerd.md)
- [Module 4 NetworkPolicy workflow](module-4-networkpolicy.md)
- [Design notes](design.md)

## Local Release Check

Before publishing or pushing a release candidate, run:

```bash
python -m build
bash scripts/check_release.sh
```

This builds the wheel and sdist, installs the wheel into a clean temporary
virtualenv, checks `k8s-forge --help`, and renders manifests from the installed
console command.

## Next step: Kyverno readiness

After NetworkPolicy readiness, see [Module 4 Kyverno](module-4-kyverno.md) to generate namespace-scoped Audit policies and understand PolicyReports.
