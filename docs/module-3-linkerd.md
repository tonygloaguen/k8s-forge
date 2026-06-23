# Module 3 Linkerd Service Mesh Readiness

## Why Service Mesh After Ingress

Ingress handles traffic entering the cluster. A Service gives the application a
stable internal address. A service mesh focuses on traffic between workloads
inside the cluster. In the lab sequence, Linkerd comes after raw Kubernetes,
Helm, and Ingress because the application should already have a stable
Deployment, Service, probes, and optional HTTP routing.

`k8s-forge` does not install Linkerd and does not run `linkerd inject`. It only
prepares the generated raw and Helm Deployment manifests with the annotations
needed for Linkerd injection when `mesh.enabled` and `mesh.inject` are true.

## Sidecar Model

Linkerd injects a `linkerd-proxy` sidecar container next to the application
container. After injection, pods commonly show `2/2` containers ready: one for
the application and one for the proxy. The proxy observes and secures network
traffic without changing the application code.

## Simple mTLS Explanation

With Linkerd installed, injected workloads can use automatic mutual TLS for
workload-to-workload traffic. Each side verifies the other through the Linkerd
control plane. `k8s-forge` does not configure advanced mTLS policy in v0.5.0;
it only prepares the workload for basic injection.

## Service vs Ingress vs Mesh

- Service: stable in-cluster entry point for pods.
- Ingress: HTTP routing from outside the cluster to a Service.
- Mesh: sidecar-based traffic management and observability between workloads.

## Configuration

```yaml
mesh:
  enabled: true
  provider: linkerd
  inject: true
  annotations:
    linkerd.io/inject: enabled
```

For v0.5.0, only `provider: linkerd` is supported. The annotation is added to
the Deployment pod template, not to the Namespace. This is intentional: it
avoids injecting every workload in the namespace by surprise.

## Manual Prerequisites

Install and validate Linkerd manually when needed:

```bash
linkerd install --crds | kubectl apply -f -
linkerd install | kubectl apply -f -
linkerd check
```

Optional Viz extension:

```bash
linkerd viz install | kubectl apply -f -
linkerd viz check
```

## Raw Workflow

```bash
k8s-forge check app.yaml
k8s-forge render app.yaml --output generated/
k8s-forge dry-run app.yaml --output generated/
k8s-forge apply app.yaml --output generated/
kubectl -n <namespace> rollout restart deploy/<app-name>
kubectl -n <namespace> rollout status deploy/<app-name> --timeout=120s
kubectl -n <namespace> get pods
```

Expected signal after injection: pods show `2/2` containers ready.

## Helm Workflow

```bash
k8s-forge helm render app.yaml --output charts-generated-mesh
helm upgrade --install <release> charts-generated-mesh/<chart> \
  -n <namespace> \
  --create-namespace
kubectl -n <namespace> rollout restart deploy/<app-name>
kubectl -n <namespace> rollout status deploy/<app-name> --timeout=120s
kubectl -n <namespace> get pods
```

## Validation Commands

```bash
linkerd check
kubectl -n <namespace> get pods
kubectl -n <namespace> describe pod <pod>
linkerd stat deploy -n <namespace>
```

With `weatherapi-platform`, the future terrain validation can use:

```bash
k8s-forge helm render k8s-forge-app-mesh.yaml --output charts-generated-mesh
helm upgrade --install weatherapi charts-generated-mesh/weatherapi \
  -n weather-helm \
  --create-namespace
kubectl -n weather-helm rollout restart deploy/weatherapi
kubectl -n weather-helm rollout status deploy/weatherapi --timeout=120s
kubectl -n weather-helm get pods
linkerd stat deploy -n weather-helm
curl -k --resolve weather.local:8443:127.0.0.1 https://weather.local:8443/weather
curl -k --resolve weather.local:8443:127.0.0.1 https://weather.local:8443/healthz
curl -k --resolve weather.local:8443:127.0.0.1 https://weather.local:8443/readyz
```

## Diagnostics

`k8s-forge doctor` checks whether the Linkerd CLI, the `linkerd` namespace, the
Linkerd control plane deployments, and the optional `linkerd-viz` namespace are
visible. These checks are non-blocking. Absence of Linkerd is normal unless mesh
injection is expected.

## Limits in v0.5.0

- No automatic Linkerd installation.
- No automatic `linkerd inject` command.
- No Namespace-level injection annotation.
- No advanced Linkerd policy.
- Viz is optional and not required by `k8s-forge`.
- No Gateway API, NetworkPolicy, Kyverno, ArgoCD, Terraform, or Ansible.
