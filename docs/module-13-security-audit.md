# Module 13 - Security Audit Readiness

Module 13 generates a local, pedagogical security review for a `k8s-forge` application. It covers container hardening, Kubernetes manifests, RBAC, ServiceAccounts, Pod Security, NetworkPolicy, Ingress and TLS, sensitive configuration, and supply-chain readiness.

This module does not run scanners, contact the cluster, contact a cloud provider, or prove runtime compliance. It produces Markdown files that help a learner structure a manual review.

## What Security Audit Readiness Adds

The generated dossier separates the main review areas:

- container image traceability and runtime hardening;
- Kubernetes objects and labels;
- RBAC and ServiceAccount risk points;
- Pod Security recommendations;
- NetworkPolicy, Ingress, TLS, and cert-manager readiness;
- sensitive configuration handling;
- Trivy, Syft, Cosign, and CI supply-chain review;
- final hardening checklist.

## Configuration

```yaml
security:
  enabled: true
  projectName: weatherapi
  container:
    enabled: true
  manifests:
    enabled: true
  rbac:
    enabled: true
  podSecurity:
    enabled: true
  network:
    enabled: true
  secrets:
    enabled: true
  supplyChain:
    enabled: true
  checklist:
    enabled: true
  examples:
    enabled: true
```

If `projectName` is empty, the renderer uses `app.name`.

## Render Security Audit Files

```bash
k8s-forge security render app.yaml --output generated-security-audit/
```

Generated files:

```text
generated-security-audit/
  README.md
  container-security.md
  kubernetes-manifest-audit.md
  rbac-audit.md
  pod-security-audit.md
  network-security-audit.md
  secrets-audit.md
  supply-chain-security.md
  final-security-checklist.md
```

Use `--force` only when you intentionally want to replace existing generated audit files.

## Local Review vs Runtime Scan

Security Audit readiness is not a live scan. It does not inspect the cluster, query RBAC, inspect live Pods, or scan images. It explains what to verify and how each readiness module fits into a security review.

Supply-chain scripts remain in the Supply Chain module. CI workflow examples remain in the CI module. Doctor checks remain non-blocking diagnostics and are not extended by this module.

## Limits v0.16.0

- Markdown review only.
- No scanner execution.
- No cluster access.
- No cloud access.
- No new doctor checks.
- No generated runtime policy enforcement.
- No sensitive value generation.

This module is intended to be reused by the future Capstone module as part of the final DevSecOps lab summary.
