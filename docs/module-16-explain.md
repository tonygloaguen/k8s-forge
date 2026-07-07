# Module 16 - Explain app configuration

`k8s-forge explain PATH` reads an existing `k8s-forge-app.yaml`, validates it
with the same loader used by `check`, and prints a pedagogical explanation of
what the configuration means.

The command is read-only. It does not modify the file, render manifests, contact
Kubernetes, install tools, create secrets, commit, push, or deploy anything.

## Usage

```bash
k8s-forge explain generated-discovery/k8s-forge-app.yaml
```

Use it after `init`, `discover`, or manual edits when you want to understand a
configuration before running `check` or any render workflow.

## What It Explains

The output covers:

- application name, namespace, image, replicas, and container port;
- Service and Ingress exposure;
- ConfigMap and Secret inputs;
- resources and HTTP probes;
- autoscaling;
- NetworkPolicy and Kyverno readiness;
- Supply Chain, CI, GitOps, observability, logging, and tracing;
- Terraform, Ansible, Security Audit, and Capstone readiness;
- risks and next manual steps.

## Pedagogical Warnings

`explain` highlights common starter-configuration risks:

- placeholder images such as `ghcr.io/example/...`;
- values marked `review-required`;
- discovery-generated review markers;
- disabled Ingress, NetworkPolicy, autoscaling, Security Audit, or Capstone;
- missing probes;
- disabled secrets;
- missing resource requests or limits.

These warnings are educational. They do not prove that an application is secure,
deployable, or production-ready.

## Limits

`explain` does not inspect a live cluster, build images, run scanners, execute
Terraform, run Ansible, or validate runtime dependencies. It only explains the
local configuration file after schema validation.
