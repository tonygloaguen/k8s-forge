# Getting Started

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
k8s-forge init demo-app
k8s-forge check app.yaml
k8s-forge render app.yaml --output generated/
k8s-forge dry-run app.yaml --output generated/
```

`init` generates a generic configuration base to adapt before use. `demo-app`
is only an example name; real values should come from the user's `app.yaml`.

Read [config-reference.md](config-reference.md) for the full `app.yaml` format,
field constraints, and examples.
