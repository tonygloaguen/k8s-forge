# Changelog

This changelog summarizes product milestones for `k8s-forge`. It is not a commit-by-commit history.


## v1.1.0 - Repository discovery / app.yaml scaffolding

- Adds generic static repository discovery with `k8s-forge discover PATH`.
- Generates local discovery reports, warnings, and starter `k8s-forge-app.yaml` scaffolds when confidence is sufficient.
- Detects common Python/Node frameworks, ports, startup hints, env vars, persistence signals, and Kubernetes Linux blockers without executing application code.
- Keeps discovery as readiness-only review material, not a Kubernetes compatibility proof.

## v1.0.0 - Stabilisation finale

- Stabilizes the CLI, README, documentation, examples, tests, packaging, release checklist, changelog, and pedagogical wording.
- Keeps `k8s-forge` focused on generating, explaining, and diagnosing readiness assets without automatic deployment or platform installation.
- Adds no new readiness module.

## v0.17.0 - Capstone readiness

- Adds the final local DevSecOps lab synthesis.
- Aggregates previous readiness modules into Markdown review material.
- Prepares the project for v1.0.0 stabilization.

## v0.16.0 - Security Audit readiness

- Adds a local Markdown security review covering containers, manifests, RBAC, Pod Security, NetworkPolicy, secrets handling, and supply chain posture.
- Keeps security review educational and non-runtime.

## v0.15.0 - Ansible readiness

- Adds local Ansible automation examples.
- Documents inventory, playbook, roles, group variables, and collections without running Ansible or opening remote connections.

## v0.14.0 - Terraform readiness

- Adds local Terraform examples for Infrastructure as Code review.
- Covers providers, variables, outputs, local backend posture, and manual workflow boundaries.

## v0.13.0 - Tracing readiness

- Adds OpenTelemetry, OTLP, Tempo, TraceQL, and Grafana traces examples.
- Documents instrumentation and tracing stack requirements without installing a collector or backend.

## v0.12.0 - Logging readiness

- Adds Loki, LogQL, Promtail collector notes, and Grafana logs dashboard examples.
- Keeps log collection setup manual.

## v0.11.0 - Observability readiness

- Adds Prometheus Operator ServiceMonitor generation and a Grafana dashboard JSON model.
- Documents metrics endpoint and monitoring stack prerequisites.

## v0.10.0 - ArgoCD / GitOps readiness

- Adds ArgoCD Application manifest generation for Helm-based delivery review.
- Keeps Git push, ArgoCD installation, credentials, and sync manual.

## v0.9.0 - GitHub Actions CI readiness

- Adds GitHub Actions workflow generation for Python checks, package build, image scan, SBOM, and artifacts.

## v0.8.0 - Supply Chain readiness

- Adds local scripts for Trivy, Syft, and optional Cosign workflows.
- Keeps tool execution explicit and reviewable.

## v0.7.0 - Kyverno readiness

- Adds namespace-scoped Kyverno Policy generation in Audit mode.
- Documents Kyverno runtime prerequisites.

## v0.6.0 - NetworkPolicy readiness

- Adds ingress-only NetworkPolicy generation.
- Documents CNI dependency for enforcement.

## v0.5.0 - Linkerd readiness

- Adds Linkerd injection annotation readiness.
- Keeps Linkerd installation and runtime validation manual.

## v0.4.0 - Ingress / cert-manager readiness

- Adds Ingress generation and cert-manager annotation readiness.
- Keeps ingress controller, DNS, TLS issuer, and certificate validation manual.

## v0.3.0 - Helm chart renderer

- Adds local Helm chart generation from `app.yaml`.
- Keeps Helm execution and deployment manual.

## v0.2.0 - Kubernetes raw renderer

- Establishes raw Kubernetes manifest rendering for the application model.
- Covers Namespace, ConfigMap, Secret placeholder, Deployment, Service, and HPA readiness.

## v0.1.1

- Stabilizes the initial local MVP baseline.

## v0.1.0

- Introduces the initial local CLI foundation for generating and reviewing Kubernetes application manifests.
