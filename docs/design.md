# k8s-forge Design

## Goal

`k8s-forge` is a small, generic generator for Kubernetes manifests. Users
describe an application in `app.yaml`; the tool validates the configuration and
will render standard YAML manifests. The full configuration reference lives in
[config-reference.md](config-reference.md). Operational usage is documented in
[operations.md](operations.md).

## Core Rules

- Application names are never hardcoded.
- Runtime values come from the user configuration.
- Rendering should be deterministic to make diffs useful.
- Kubernetes command execution should be explicit and controlled.
- Code should be typed, testable, and low side effect.

## Planned Components

- `cli.py`: Typer command surface.
- `models.py`: Pydantic models for user configuration.
- `config_loader.py`: YAML loading and validation entry points.
- `renderer.py`: raw Kubernetes manifest rendering.
- `supply_chain_renderer.py`: local Trivy, Syft, and Cosign readiness script rendering.
- `ci_renderer.py`: GitHub Actions CI readiness workflow rendering.
- `gitops_renderer.py`: ArgoCD GitOps readiness manifest rendering.
- `helm_renderer.py`: local Helm chart rendering from the same validated config.
- `kubectl.py`: safe wrapper around `kubectl`.
- `local_cluster.py`: safe local command helpers for Docker, kind, and kubectl diagnostics.
- `exceptions.py`: project-specific exceptions.

## MVP Resources

The current raw Kubernetes render target is:

- Namespace
- ConfigMap
- Secret
- Deployment
- Service
- optional HorizontalPodAutoscaler
- optional Ingress
- optional Linkerd pod-template annotations
- optional ingress-only NetworkPolicy
- optional namespace-scoped Kyverno Policy

The Helm renderer generates a local chart for the same application model. It
does not run Helm and does not install releases. Ingress rendering targets existing ingress-nginx and optional cert-manager prerequisites. Mesh readiness targets existing Linkerd prerequisites and only annotates Deployment pod templates when explicitly enabled. NetworkPolicy rendering targets CNI-compatible clusters and does not install or replace the CNI. Kyverno rendering generates namespace-scoped Audit policies and does not install Kyverno. Supply Chain rendering generates local helper scripts and does not install Trivy, Syft, or Cosign. CI rendering generates GitHub Actions workflow files and does not push images, create secrets, or deploy Kubernetes resources. GitOps rendering generates ArgoCD Application manifests and does not install ArgoCD, push Git, apply manifests, or sync applications. Global default-deny, egress NetworkPolicy, ClusterPolicy, Kustomize, and direct Kubernetes API usage remain outside the current scope.

## Observability Readiness

`observability_renderer.py` should remain separate from raw Kubernetes, Helm, CI, Supply Chain, and GitOps renderers. It produces local Prometheus and Grafana examples only and does not install or configure a monitoring stack.

`logging_renderer.py` should remain separate from metrics observability. It produces local Loki, LogQL, collector-note, and Grafana logs dashboard examples only and does not install or configure a logging stack.

`tracing_renderer.py` should remain separate from metrics observability and logging. It produces local OpenTelemetry, Tempo, TraceQL, collector-note, and Grafana traces dashboard examples only and does not install or configure a tracing stack.

`terraform_renderer.py` should remain separate from Kubernetes, Helm, GitOps, and CI renderers. It produces local Terraform examples only and does not run Terraform, contact clouds, create access material, generate cluster config files, or provision resources.
