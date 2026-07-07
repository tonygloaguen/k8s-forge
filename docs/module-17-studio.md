# Module 17 - Studio local GUI

`k8s-forge studio` starts a local browser interface for the repository discovery,
configuration review, and local Kubernetes readiness workflow.

Studio is a local lab tool. It binds to `127.0.0.1` by default, keeps a local
workspace, streams job output to the browser, and requires review before any
runtime action.

## Install

Studio dependencies are optional so the normal CLI stays lightweight:

```bash
pip install -e ".[studio]"
```

For development:

```bash
pip install -e ".[dev,studio]"
```

## Run

```bash
k8s-forge studio --host 127.0.0.1 --port 8765 --workspace .k8s-forge-studio
```

Then open:

```text
http://127.0.0.1:8765
```

## Workflow

The MVP supports:

1. selecting a local repository;
2. cloning or pulling a Git repository;
3. running repository discovery;
4. reading `discovery-report.md` and `warnings.md`;
5. editing `k8s-forge-app.yaml`;
6. running `check`;
7. running `explain`;
8. rendering manifests to `generated-k8s/`;
9. running `kubectl apply --dry-run=client`;
10. viewing stdout/stderr job logs.

## Guardrails

Studio does not accept arbitrary shell commands. The backend builds all commands
from an allowlist and never uses `shell=True`.

Allowed external commands are limited to controlled forms of:

- `git clone` and `git pull`;
- `docker build`;
- `kind load docker-image`;
- `kubectl apply --dry-run=client`;
- confirmed `kubectl apply`;
- `kubectl get`, `kubectl logs`, and `kubectl port-forward`.

Studio rejects workflows such as Git push, Kubernetes delete, Helm install,
Terraform apply, Ansible playbook execution, and free-form shell commands.

Deploy remains guarded by:

- a successful dry-run;
- explicit user confirmation;
- no critical Windows/COM/Desktop discovery blockers;
- rendered manifests present in the workspace.

## Workspace

Studio writes under `.k8s-forge-studio/` by default:

```text
.k8s-forge-studio/
  repos/
  jobs/
  logs/
  outputs/
  state.json
```

Job logs are kept in `jobs/<job-id>.log`.

## Limits

v1.3.0 is focused on local kind-style workflows and review. It does not provide
multi-user authentication, cloud deployment, production deployment, advanced
Dockerfile generation, secret management, Helm install, Terraform apply, or
Ansible playbook execution.
