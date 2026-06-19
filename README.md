# k8s-forge

`k8s-forge` is a generic Python tool for generating standard Kubernetes
manifests for stateless containerized web applications.

The project is intentionally application-agnostic: every application-specific
value must come from a user-provided `app.yaml` file. No application name is
hardcoded in the implementation.

## Workflow

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

The MVP renders these Kubernetes resources:

- Namespace
- ConfigMap, only when `config` is non-empty
- Secret, only when `secrets` is non-empty
- Deployment
- Service, only when `service.enabled` is `true`

The current implementation renders manifests and can run controlled `kubectl` commands through a single safe wrapper.

## Rendering

Generate manifests from an application configuration:

```bash
k8s-forge render examples/demo-app.yaml --output generated/
```

For a complete configuration, this writes:

```text
generated/00-namespace.yaml
generated/10-configmap.yaml
generated/20-secret.yaml
generated/30-deployment.yaml
generated/40-service.yaml
```

Known generated files are overwritten on each render. Files with other names in
the output directory are left untouched.


## Kubernetes Commands

Validate and render before touching a cluster:

```bash
k8s-forge check examples/demo-app.yaml
k8s-forge render examples/demo-app.yaml --output generated/
```

Use server-side dry-run and diff before applying changes:

```bash
k8s-forge dry-run examples/demo-app.yaml --output generated/
k8s-forge diff examples/demo-app.yaml --output generated/
```

Apply asks for interactive confirmation by default:

```bash
k8s-forge apply examples/demo-app.yaml --output generated/
```

For automation, confirmation can be skipped explicitly:

```bash
k8s-forge apply examples/demo-app.yaml --output generated/ --yes
```

Check deployed resources with the application name and namespace:

```bash
k8s-forge status demo-app -n demo
```

All `kubectl` calls use `subprocess.run` without `shell=True`, capture
stdout/stderr, and use a timeout. Tests must mock the subprocess boundary and
must never depend on a real Kubernetes cluster or run a real `kubectl apply`.

## Secrets Warning

Do not commit real secrets. Values placed in `app.yaml` or generated manifests
may be stored in plain text during the MVP. The MVP uses Kubernetes
`stringData` for readability and should only be used with placeholder values in
examples and tests.

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
