# Operational Workflow

## Introduction

`k8s-forge` generates Kubernetes manifests from `app.yaml`, then delegates
cluster operations to `kubectl`. It does not replace Kubernetes, the Kubernetes
API server, RBAC, container registries, or cluster observability tools.

Before using `dry-run`, `diff`, `apply`, or `status`, `kubectl` must be
installed and configured. The active Kubernetes context must also be checked
before any command that talks to a real cluster.


## Local kind Bootstrap

`k8s-forge` can help prepare a local kind cluster. It does not install Docker,
kind, or kubectl for you. Install those tools first, then run:

```bash
k8s-forge doctor
k8s-forge cluster create --name devsecops
k8s-forge cluster status --name devsecops
```

To load a local Docker image into the kind cluster:

```bash
k8s-forge image load demo-app:latest --cluster devsecops
```

To remove the cluster, `cluster delete` asks for confirmation by default:

```bash
k8s-forge cluster delete --name devsecops
k8s-forge cluster delete --name devsecops --yes
```

## Recommended Pre-Checks

```bash
kubectl config current-context
kubectl get nodes
k8s-forge check app.yaml
k8s-forge render app.yaml --output generated/
```

`kubectl config current-context` shows which cluster and context `kubectl` will
use. This reduces the risk of applying changes to the wrong cluster.

`kubectl get nodes` confirms that the cluster is reachable and that the current
credentials can talk to the API server.

`k8s-forge check app.yaml` validates the local configuration file before any
manifests are generated.

`k8s-forge render app.yaml --output generated/` generates local manifests that
can be inspected before any cluster operation.

## `dry-run`

```bash
k8s-forge dry-run app.yaml --output generated/
```

This command:

- generates the manifests into the output directory;
- runs `kubectl apply --dry-run=server -f generated/`;
- validates the manifests against the Kubernetes API server;
- does not create or update resources.

`dry-run` requires a reachable cluster. It can fail if the namespace is invalid
or missing, the current user lacks permissions, the API server rejects a field,
or the manifests are invalid for the target cluster.

Run `dry-run` before `apply`.

## `diff`

```bash
k8s-forge diff app.yaml --output generated/
```

This command:

- generates the manifests into the output directory;
- runs `kubectl diff -f generated/`;
- shows what would change in the cluster.

Exit code behavior:

- `0`: no differences found;
- `1`: differences found, which is a normal result for `kubectl diff`;
- greater than `1`: real error, such as API, permission, or validation failure.

Read the diff before applying changes.

## `apply`

```bash
k8s-forge apply app.yaml --output generated/
```

This command:

- generates the manifests;
- prints a warning;
- asks for interactive confirmation;
- runs `kubectl apply -f generated/` only if the user confirms.

Use `apply` only after `check`, `render`, `dry-run`, and ideally `diff`.

For advanced or automated workflows, confirmation can be skipped explicitly:

```bash
k8s-forge apply app.yaml --output generated/ --yes
```

Avoid `--yes` when learning the workflow or when targeting an unfamiliar
cluster.

## `status`

```bash
k8s-forge status demo-app -n demo
```

This command runs a `kubectl get` query filtered by the application label. It
shows related Deployments, Pods, and Services for the selected namespace.

Use it to confirm that the application is visible in Kubernetes after applying
manifests.

## Complete Operational Scenario

```bash
k8s-forge doctor
k8s-forge cluster create --name devsecops
k8s-forge cluster status --name devsecops
k8s-forge init demo-app --image demo-app:latest
k8s-forge check app.yaml
k8s-forge render app.yaml --output generated/
k8s-forge image load demo-app:latest --cluster devsecops
k8s-forge dry-run app.yaml --output generated/
k8s-forge diff app.yaml --output generated/
k8s-forge apply app.yaml --output generated/
k8s-forge status demo-app -n demo-app
```

Step summary:

- `doctor` checks Docker, kind, kubectl, context, and visible nodes.
- `cluster create` creates the local kind cluster if needed.
- `cluster status` shows the local kind cluster state.
- `init` creates a generic starter `app.yaml`.
- `check` validates the configuration file.
- `render` writes local manifests for inspection.
- `image load` loads a local Docker image into kind.
- `dry-run` asks the Kubernetes API server to validate the manifests without
  applying them.
- `diff` shows what would change.
- `apply` applies the manifests after confirmation.
- `status` lists related Kubernetes resources.

## Common Failure Scenarios

### `kubectl` missing from `PATH`

Cause: `kubectl` is not installed or is not available in the shell `PATH`.

Diagnostic:

```bash
kubectl version --client
```

Correction: install `kubectl` and ensure the executable is available in `PATH`.

### Wrong Kubernetes context

Cause: `kubectl` is configured for a different cluster or namespace than the one
you intended to target.

Diagnostic:

```bash
kubectl config current-context
```

Risk: applying manifests to the wrong cluster.

Correction: switch to the intended context before running `dry-run`, `diff`, or
`apply`.

### Cluster unreachable

Cause: the Kubernetes API server is unavailable, credentials are expired, or the
network path is broken.

Diagnostic:

```bash
kubectl get nodes
```

Correction: restore cluster access, credentials, or network connectivity.

### `ImagePullBackOff`

Cause: Kubernetes cannot pull the configured image. The image may not exist, the
tag may be wrong, registry credentials may be missing, or a local image may not
be loaded into a local cluster.

For kind, local images often need to be loaded explicitly:

```bash
kind load docker-image demo-app:latest
```

Correction: publish or load the image, fix the tag, or configure registry
credentials.

### `CrashLoopBackOff`

Cause: the container starts and then crashes repeatedly.

Diagnostic:

```bash
kubectl logs deployment/demo-app -n demo-app
```

Correction: inspect application logs, environment variables, command arguments,
and runtime dependencies.

### `readOnlyRootFilesystem` errors

Cause: the generated Deployment sets `readOnlyRootFilesystem: true`, and the
application tries to write to the container root filesystem.

Correction: update the application to write to an allowed path. A future version
may add controlled temporary volume support or a carefully documented option to
change this behavior.

### Probe failures

Cause: configured endpoints such as `/healthz` or `/readyz` do not exist, return
an error, or take too long to respond.

Correction: update `app.yaml` to use real endpoints or implement the endpoints
in the application.

### Namespace or RBAC errors

Cause: the namespace does not exist, the namespace name is wrong, or the current
user lacks permission to create or update resources.

Diagnostics:

```bash
kubectl get namespace demo-app
kubectl auth can-i apply deployment -n demo-app
```

Correction: create or correct the namespace, or request the required RBAC
permissions.

## Current Guardrails

- `check` validates the configuration file before generation.
- `render` writes manifests locally without touching the cluster.
- `dry-run` validates against the Kubernetes API without applying resources.
- `diff` shows changes before apply.
- `apply` asks for confirmation unless `--yes` is passed.
- Tests mock `kubectl` and never touch a real cluster.

## Best Practices

- Always verify the active Kubernetes context.
- Always run `dry-run` before `apply`.
- Read the `diff` before applying changes.
- Avoid `--yes` when learning or when targeting an unfamiliar cluster.
- Keep generated manifests inspectable.
- Never commit real secrets.
- Use K9s or equivalent tools to observe Pods, Services, Events, and Logs.
