# Module 4 NetworkPolicy Readiness

## Why NetworkPolicy Comes Here

Raw Kubernetes, Helm, Ingress, and service mesh readiness first make the
application deployable, reachable, and observable. NetworkPolicy adds a network
security layer by restricting which traffic can reach selected Pods.

By default, many Kubernetes clusters allow broad pod-to-pod communication. A
NetworkPolicy describes allowed traffic, but it only has an effect when the
cluster CNI plugin enforces NetworkPolicy.

`k8s-forge` does not install or replace the CNI. It generates the policy and
explains how to validate it.

## Service vs Ingress vs Mesh vs NetworkPolicy

- Service: stable in-cluster entry point for Pods.
- Ingress: HTTP routing from outside the cluster to a Service.
- Mesh: sidecar-based traffic observability and security between workloads.
- NetworkPolicy: Kubernetes-native allow rules for selected Pod traffic.

## Profile: ingress-only

The v0.6.0 profile is intentionally small:

```yaml
networkPolicy:
  enabled: true
  profile: ingress-only
  ingress:
    enabled: true
    fromNamespaces:
      - ingress-nginx
    ports:
      - 8000
  egress:
    enabled: false
```

It selects the application Pods and allows ingress traffic from the
`ingress-nginx` namespace to the application container port. It does not create
a global default-deny policy and does not render egress rules.

## Pod Port vs Service Port

NetworkPolicy ports target Pod traffic. If the Service exposes port `80` and
forwards to container port `8000`, the NetworkPolicy should allow `8000`, not
`80`.

## Namespace Selector

`k8s-forge` uses the standard namespace label:

```yaml
namespaceSelector:
  matchLabels:
    kubernetes.io/metadata.name: ingress-nginx
```

It does not label or modify the `ingress-nginx` namespace.

## CNI Enforcement

A NetworkPolicy object can exist without being enforced. Enforcement depends on
the CNI plugin. Calico and Cilium commonly enforce NetworkPolicy. Some local
kind clusters using kindnet or other simple CNIs may not enforce it by default.

`k8s-forge doctor` checks kube-system Pods and existing NetworkPolicy objects,
but this is only a heuristic. It cannot prove enforcement.

## Validation Commands

```bash
kubectl -n <namespace> get networkpolicy
kubectl -n <namespace> describe networkpolicy <app>-ingress-only
kubectl -n <namespace> get pods
```

For an Ingress-backed application:

```bash
curl -k --resolve weather.local:8443:127.0.0.1 https://weather.local:8443/weather
curl -k --resolve weather.local:8443:127.0.0.1 https://weather.local:8443/healthz
curl -k --resolve weather.local:8443:127.0.0.1 https://weather.local:8443/readyz
```

## weatherapi-platform Future Terrain Flow

```bash
cp k8s-forge-app-mesh.yaml k8s-forge-app-netpol.yaml
```

Add the `networkPolicy` section, then render and upgrade:

```bash
k8s-forge helm render k8s-forge-app-netpol.yaml --output charts-generated-netpol

helm upgrade --install weatherapi charts-generated-netpol/weatherapi \
  -n weather-helm \
  --create-namespace

kubectl -n weather-helm get networkpolicy
kubectl -n weather-helm describe networkpolicy weatherapi-ingress-only
```

Expected note when the CNI does not enforce policies:

```text
The NetworkPolicy object exists, but enforcement may not happen on this cluster.
```

## Limits in v0.6.0

- No automatic CNI installation.
- No Calico or Cilium installation.
- No CNI replacement.
- No global default-deny.
- No effective egress policy rendering.
- No Kyverno, PodSecurity, OPA, ArgoCD, Terraform, or Ansible.
