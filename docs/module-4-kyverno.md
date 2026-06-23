# Module 4 - Kyverno Readiness

This module adds an educational Kyverno policy layer after Kubernetes raw manifests, Helm, Ingress, Linkerd readiness, and NetworkPolicy readiness.

`k8s-forge` generates Kyverno policy manifests, but it does not install Kyverno and does not modify admission control settings automatically.

## What Kyverno Does

Kyverno is a Kubernetes admission controller. It can validate resources when they are submitted to the API server and can also scan existing resources in the background.

In this project, Kyverno is used to observe whether generated workloads follow baseline security and metadata practices.

## Audit vs Enforce

`Audit` reports violations without blocking resources. This is the default because the lab should remain deployable while users learn what the policy reports.

`Enforce` can reject resources that violate the policy. Use it only after validating the policy impact in `Audit` mode.

## Policy vs ClusterPolicy

`k8s-forge v0.7.0` generates namespace-scoped `Policy` resources, not `ClusterPolicy` resources.

This keeps the impact limited to the application namespace and avoids surprising cluster-wide behavior.

## Configuration

```yaml
policy:
  enabled: true
  provider: kyverno
  profile: baseline
  validationFailureAction: Audit
  background: true
  rules:
    requireRecommendedLabels: true
    disallowPrivilegedContainers: true
    requireRunAsNonRoot: true
    requireResources: true
    disallowLatestTag: true
```

## Baseline Rules

The baseline profile can generate these checks:

- `require-recommended-labels`: requires `app.kubernetes.io/name` and `app.kubernetes.io/managed-by` on application resources.
- `disallow-privileged-containers`: audits privileged containers.
- `require-run-as-non-root`: audits workloads that do not declare non-root execution.
- `require-resources`: audits containers without CPU and memory requests and limits.
- `disallow-latest-tag`: audits images using the `latest` tag.

## NetworkPolicy vs Kyverno

NetworkPolicy controls traffic between pods when the CNI enforces it.

Kyverno validates Kubernetes resource configuration through admission policies and PolicyReports. It does not replace NetworkPolicy, Ingress, or a service mesh.

## Manual Kyverno Prerequisite

Install Kyverno manually when you want the cluster to audit or enforce generated policies. `k8s-forge` only generates manifests and diagnostics.

After Kyverno is installed, useful checks are:

```bash
kubectl -n kyverno get pods
kubectl get crd | grep kyverno
kubectl get policyreport -A
```

## Validation With weatherapi-platform

```bash
cp k8s-forge-app-netpol.yaml k8s-forge-app-kyverno.yaml
```

Add the `policy` section shown above, then run:

```bash
k8s-forge check k8s-forge-app-kyverno.yaml

k8s-forge render k8s-forge-app-kyverno.yaml   --output generated-k8s-forge-kyverno/

k8s-forge helm render k8s-forge-app-kyverno.yaml   --output charts-generated-kyverno

cat generated-k8s-forge-kyverno/80-kyverno-policy.yaml

helm lint charts-generated-kyverno/weatherapi
helm template weatherapi charts-generated-kyverno/weatherapi -n weather-helm

k8s-forge doctor
```

Without Kyverno installed, the policy YAML and Helm chart can still be reviewed locally. The cluster will not audit or enforce the policy until Kyverno is installed.

With Kyverno installed manually later:

```bash
kubectl -n kyverno get pods
kubectl -n weather-helm get policy
kubectl -n weather-helm describe policy weatherapi-baseline
kubectl get policyreport -A
```

## Limits in v0.7.0

- No automatic Kyverno installation.
- No `ClusterPolicy` generation.
- No `Enforce` by default.
- No mutation rules.
- No generated policy exceptions.
- No OPA/Gatekeeper integration.
- No GitOps, Terraform, or Ansible integration.
