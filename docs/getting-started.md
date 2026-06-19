# Getting Started

## Install Locally

```bash
python -m pip install -e ".[dev]"
```

## Check The CLI

```bash
k8s-forge --help
```

The initial project skeleton exposes the planned commands, but most commands are
not implemented yet.

## Future Example

```bash
k8s-forge init demo-app
k8s-forge check app.yaml
k8s-forge render app.yaml --output generated/
```

`demo-app` is only an example name. The tool must remain generic and should use
values from the user's `app.yaml`.
