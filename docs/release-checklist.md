# Release Checklist v0.1.0

This checklist prepares a local GitHub release for `k8s-forge` v0.1.0.
It does not publish to PyPI and does not create a GitHub release
automatically.

## 1. Git Pre-Checks

Check the repository state before tagging:

```bash
git status
git log --oneline --max-count=5
```

Success criteria:

- the working tree is clean;
- no unexpected deleted or untracked files remain;
- the latest commits match the intended release content.

## 2. Local Quality

Run the local quality gate:

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src
.venv/bin/python -m bandit -r src
.venv/bin/python -m pip_audit --skip-editable
.venv/bin/python -m pytest -q
```

All commands must complete successfully before tagging.

## 3. Packaging

Build the package and run the local release installation check:

```bash
.venv/bin/python -m build
bash scripts/check_release.sh
```

Verify that the expected artifacts exist:

```bash
test -f dist/k8s_forge-0.1.0-py3-none-any.whl
test -f dist/k8s_forge-0.1.0.tar.gz
```

Success criteria:

- wheel and sdist are built;
- the wheel installs in a temporary virtualenv;
- the installed `k8s-forge` command runs;
- Jinja2 templates are included in the installed package;
- manifests can be rendered from the installed wheel.

## 4. Local Functional Check

Run a minimal functional flow without touching a Kubernetes cluster:

```bash
k8s-forge --help
k8s-forge init demo-app --output /tmp/k8s-forge-demo.yaml --force
k8s-forge check /tmp/k8s-forge-demo.yaml
k8s-forge render /tmp/k8s-forge-demo.yaml --output /tmp/k8s-forge-generated
```

Expected generated files:

```text
/tmp/k8s-forge-generated/00-namespace.yaml
/tmp/k8s-forge-generated/10-configmap.yaml
/tmp/k8s-forge-generated/20-secret.yaml
/tmp/k8s-forge-generated/30-deployment.yaml
/tmp/k8s-forge-generated/40-service.yaml
```

## 5. Git Tag

Create and push the release tag after the quality and packaging checks pass:

```bash
git tag -a v0.1.0 -m "Release v0.1.0 local MVP"
git push origin main
git push origin v0.1.0
```

Do not tag with a dirty working tree.

## 6. GitHub Release Text

Title:

```text
v0.1.0 - Local MVP
```

Release notes:

```markdown
## Summary

`k8s-forge` v0.1.0 is a local MVP for generating Kubernetes manifests for
stateless containerized web applications from a generic `app.yaml` file.

The tool is intentionally application-agnostic: application names, images,
ports, namespaces, labels, configuration values, and secrets placeholders come
from the user configuration.

## Included

- `k8s-forge doctor` for local Docker/kind/kubectl checks.
- `k8s-forge cluster create/status/delete` for local kind clusters.
- `k8s-forge image load` for loading a local Docker image into kind.
- `k8s-forge init` for generating a starter `app.yaml`.
- `k8s-forge check` for validating configuration.
- `k8s-forge render` for generating Kubernetes YAML locally.
- `k8s-forge dry-run` using `kubectl apply --dry-run=server`.
- `k8s-forge diff` using `kubectl diff`.
- `k8s-forge apply` with interactive confirmation by default.
- `k8s-forge status` for Deployment, Pod, and Service visibility.
- Generation of Namespace, ConfigMap, Secret, Deployment, and Service.

## Out of Scope

- PyPI publication.
- Helm.
- Kustomize.
- LangGraph.
- Ingress.
- HPA.
- NetworkPolicy.
- Real secret management.
- Python Kubernetes client.
- Kubernetes operator behavior.

## Known Limitations

- `app.yaml` secrets are educational placeholders and must not contain real
  committed secrets.
- `apply --yes` is intended for advanced or automated use.
- Local cluster support assumes Docker, kind, and kubectl are installed by the
  user.
- Tests mock external commands and do not validate against a real Kubernetes
  cluster.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

k8s-forge doctor
k8s-forge cluster create --name devsecops
k8s-forge init demo-app
k8s-forge check app.yaml
k8s-forge render app.yaml --output generated/
k8s-forge image load demo-app:latest --cluster devsecops
k8s-forge dry-run app.yaml --output generated/
k8s-forge diff app.yaml --output generated/
k8s-forge apply app.yaml --output generated/
k8s-forge status demo-app -n demo-app
```
```

## 7. Success Criteria

The release is ready when:

- GitHub Actions CI is green;
- the working tree is clean;
- local quality checks pass;
- the wheel is built;
- the sdist is built;
- installation from the wheel is validated in a temporary virtualenv;
- the `k8s-forge` CLI is available from the installed wheel;
- manifests are generated successfully;
- documentation is present and linked from the README.
