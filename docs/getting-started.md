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
k8s-forge image load demo-app:latest --cluster devsecops
k8s-forge dry-run app.yaml --output generated/
```

`init` generates a generic configuration base to adapt before use. `demo-app`
is only an example name; real values should come from the user's `app.yaml`.

Read [config-reference.md](config-reference.md) for the full `app.yaml` format,
field constraints, and examples.

For real existing applications, keep `k8s-forge` files separate from existing
Kubernetes or Helm assets. Use a dedicated config such as `k8s-forge-app.yaml`
and render into a dedicated directory such as `generated-k8s-forge/`. See
[real-app-weatherapi.md](real-app-weatherapi.md) for a tested FastAPI example.

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
