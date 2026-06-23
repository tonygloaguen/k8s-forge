# Module 3 Ingress-NGINX And cert-manager Readiness

## Why Ingress After Service

A Kubernetes `Service` gives stable networking inside the cluster. With the
Module 2 setup, the application is reachable through a ClusterIP Service and can
be tested with `kubectl port-forward`.

An `Ingress` adds HTTP routing at the edge of the cluster. It maps a hostname
such as `weather.local` and a path such as `/` to the Service that fronts the
application Pods.

## Ingress-NGINX Role

Kubernetes stores Ingress objects, but it does not route traffic by itself. A
controller such as ingress-nginx must watch Ingress resources and configure the
actual HTTP proxy.

`k8s-forge` can generate Ingress YAML, but it does not install ingress-nginx.
Install and validate it manually when the lab reaches Module 3.

## cert-manager Role

cert-manager automates certificate objects and can react to annotations such as:

```yaml
cert-manager.io/cluster-issuer: selfsigned-dev
```

A `ClusterIssuer` is cluster-scoped and must exist before cert-manager can issue
or prepare a certificate. `k8s-forge` does not create ClusterIssuers.

## app.yaml Example

```yaml
ingress:
  enabled: true
  host: weather.local
  className: nginx
  path: /
  pathType: Prefix
  tls:
    enabled: true
    secretName: weather-tls
  certManager:
    enabled: true
    clusterIssuer: selfsigned-dev
  annotations: {}
```

## Generate Raw Manifests

```bash
k8s-forge check k8s-forge-app.yaml
k8s-forge render k8s-forge-app.yaml --output generated-k8s-forge/
```

When Ingress is enabled, raw rendering includes:

```text
generated-k8s-forge/60-ingress.yaml
```

## Generate Helm Chart

```bash
k8s-forge helm render k8s-forge-app.yaml --output charts/
helm lint charts/weatherapi
helm template weatherapi charts/weatherapi -n weather
```

The Helm chart includes `templates/ingress.yaml`, but Helm does not install
Ingress-NGINX or cert-manager.

## kind Ports 80 And 443

For direct local Ingress access on kind, the cluster must expose host ports 80
and 443 to the ingress-nginx controller. If the cluster was created without
those mappings, use port-forwarding or recreate the lab cluster with kind
`extraPortMappings`.

## /etc/hosts For weather.local

Local hostnames such as `weather.local` do not resolve automatically. Add a local
hosts entry manually when using direct local access:

```text
127.0.0.1 weather.local
```

`k8s-forge` never modifies `/etc/hosts`.

## Manual ingress-nginx Setup

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.2/deploy/static/provider/kind/deploy.yaml

kubectl -n ingress-nginx wait --for=condition=ready pod   -l app.kubernetes.io/component=controller   --timeout=120s
```

## Manual cert-manager Setup

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update

helm install cert-manager jetstack/cert-manager   -n cert-manager   --create-namespace   --set crds.enabled=true
```

Create a local self-signed ClusterIssuer manually for the lab:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-dev
spec:
  selfSigned: {}
```

## Validation Commands

```bash
kubectl -n weather get ingress
kubectl -n ingress-nginx get deploy ingress-nginx-controller
kubectl -n cert-manager get deploy cert-manager
curl -H "Host: weather.local" http://127.0.0.1/weather
curl -k https://weather.local/weather
```

If ports 80/443 are not exposed on kind, use port-forwarding:

```bash
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8082:80
curl -H "Host: weather.local" http://127.0.0.1:8082/weather
```

## Limits In v0.4.0

- No automatic ingress-nginx installation.
- No automatic cert-manager installation.
- No automatic ClusterIssuer creation.
- No `/etc/hosts` modification.
- No DNS management.
- No production TLS workflow.
- No Linkerd, NetworkPolicy, Kyverno, ArgoCD, Terraform, or Ansible.
