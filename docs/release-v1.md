# v1.0.0 Release Hardening

`k8s-forge` v1.0.0 is the stabilization milestone for the pedagogical DevSecOps Cloud-Native lab. It does not add a new readiness module. It makes the existing command surface, documentation, examples, packaging, tests, and release process coherent enough to present as a stable learning tool.

## Positioning

`k8s-forge` generates, explains, and diagnoses. It helps learners understand how raw Kubernetes, Helm, ingress, service mesh readiness, policy, supply chain, CI, GitOps, observability, logging, tracing, Terraform, Ansible, Security Audit, and Capstone synthesis fit together.

It remains a local educational generator. Generated files are meant for manual review before any external workflow.

## Stabilized Modules

- Kubernetes raw manifests.
- Helm chart rendering.
- Ingress and cert-manager readiness.
- Linkerd readiness.
- NetworkPolicy readiness.
- Kyverno readiness.
- Supply Chain readiness.
- GitHub Actions CI readiness.
- ArgoCD GitOps readiness.
- Observability readiness.
- Logging readiness.
- Tracing readiness.
- Terraform readiness.
- Ansible readiness.
- Security Audit readiness.
- Capstone readiness.

## Non-Goals

`k8s-forge` does not install platform components, deploy automatically, push Git changes, create secrets, provision infrastructure, run Ansible playbooks, run runtime security scans, or prove compliance. Existing explicit runtime commands such as `dry-run`, `diff`, `apply`, `status`, `cluster`, and `image` stay visible CLI actions controlled by the user.

## Manual Dependencies

Depending on the lab path, users may install or configure Kubernetes, Docker, kind, kubectl, ingress-nginx, cert-manager, Linkerd, Kyverno, ArgoCD, Prometheus Operator, Grafana, Loki, Tempo, OpenTelemetry Collector, Terraform, Ansible, Trivy, Syft, or Cosign. These dependencies are not installed by `k8s-forge`.

## Final Validation Path

1. Confirm the repository is clean.
2. Run the Python quality gate.
3. Build wheel and source distribution.
4. Install the wheel into a temporary virtual environment.
5. Run CLI smoke tests.
6. Validate checked-in examples.
7. Review docs, generated templates, and release notes.
8. Perform the final version bump and tag only after the release gate passes.

## Limits

The v1.0.0 release is stable in scope, not a guarantee that a user runtime platform is installed, healthy, compliant, or production ready. Runtime validation remains a separate manual workflow.

## After v1.0.0

Future work should prefer maintenance, documentation clarity, smaller UX improvements, and compatibility checks over new large readiness modules. Larger features should be considered only after the v1 command and schema surfaces are kept stable.
