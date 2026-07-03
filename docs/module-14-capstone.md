# Module 14 - Capstone Readiness

Module 14 generates the final local synthesis of the DevSecOps Cloud-Native lab. It aggregates all previous readiness layers into a Markdown dossier suitable for a technical report, internship report, training handout, DevSecOps review, or preparation toward `v1.0.0`.

The Capstone module does not deploy, scan, contact the cluster, contact a cloud provider, push Git changes, create sensitive values, or validate runtime compliance. It documents what has been generated, what remains manual, runtime dependencies, limits, and the full DevSecOps chain.

## What Capstone Adds

The generated dossier covers:

- Kubernetes raw manifests;
- Helm chart rendering;
- Ingress and TLS readiness;
- Linkerd readiness;
- NetworkPolicy readiness;
- Kyverno readiness;
- Supply Chain readiness;
- CI GitHub Actions readiness;
- GitOps ArgoCD readiness;
- Observability readiness;
- Logging readiness;
- Tracing readiness;
- Terraform readiness;
- Ansible readiness;
- Security Audit readiness.

## Configuration

```yaml
capstone:
  enabled: true
  projectName: weatherapi
  report:
    title: "WeatherAPI DevSecOps Cloud-Native Lab"
    audience: technical
  checklist:
    enabled: true
  architecture:
    enabled: true
  devsecopsMatrix:
    enabled: true
  modulesSummary:
    enabled: true
  manualSteps:
    enabled: true
  runtimeDependencies:
    enabled: true
  securitySummary:
    enabled: true
  v1Readiness:
    enabled: true
  examples:
    enabled: true
```

If `projectName` is empty, k8s-forge uses `app.name`. If `report.title` is empty, it uses `<app.name> DevSecOps Cloud-Native Lab`. Supported audiences are `technical`, `training`, and `internship`.

## Render Capstone Files

```bash
k8s-forge capstone render app.yaml --output generated-capstone/
```

Generated files:

```text
generated-capstone/
  README.md
  lab-summary.md
  architecture-overview.md
  devsecops-chain.md
  modules-summary.md
  validation-checklist.md
  manual-steps.md
  runtime-dependencies.md
  security-summary.md
  v1-readiness.md
  final-report-outline.md
```

Use `--force` only when replacing existing generated Capstone files intentionally.

## Security Audit Integration

Capstone explicitly includes `v0.16.0 Security Audit readiness`. It summarizes container hardening, Pod Security, RBAC, ServiceAccounts, secrets handling, NetworkPolicy, Kyverno, Supply Chain, and CI security review. It does not run scanners or prove runtime compliance.

## v1.0.0 Preparation

The `v1-readiness.md` file lists stabilization work: docs consistency, CLI consistency, example validation, tests, release checklist, UX review, and optional changelog generation. Capstone is the last synthesis layer before a possible `v1.0.0` stabilization phase.

## Limits v0.17.0

- Markdown generation only.
- No deployment.
- No scan execution.
- No cluster access.
- No cloud access.
- No new doctor checks.
- No generated sensitive values.
- No production release automation.
