# k8s-forge

`k8s-forge` is a generic Python tool for generating standard Kubernetes
manifests for stateless containerized web applications.

The project is intentionally application-agnostic: every application-specific
value must come from a user-provided `app.yaml` file. No application name is
hardcoded in the implementation.

## Planned Workflow

The intended workflow is:

```text
init -> check -> render -> dry-run -> diff -> apply -> status
```

Example command flow:

```bash
k8s-forge init demo-app
k8s-forge check app.yaml
k8s-forge render app.yaml --output generated/
k8s-forge dry-run app.yaml --output generated/
k8s-forge diff app.yaml --output generated/
k8s-forge apply app.yaml --output generated/
k8s-forge status demo-app -n demo
```

`demo-app` is only a documentation example. Real values should come from the
user's configuration.

## MVP Scope

The MVP will generate these Kubernetes resources:

- Namespace
- ConfigMap
- Secret
- Deployment
- Service

The initial skeleton does not yet generate complete Kubernetes manifests and
does not call `kubectl`.

## Secrets Warning

Do not commit real secrets. Values placed in `app.yaml` or generated manifests
may be stored in plain text during the MVP. Use local placeholder values for
development and rely on an appropriate secret management process for real
deployments.

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
