# Module 2 Helm Workflow

## Why Helm After Raw Kubernetes

The raw Kubernetes workflow teaches what each object does: ConfigMap, Secret,
Deployment, Service, and HPA. Helm is the next step because it packages those
objects into a reusable chart with configurable values.

`k8s-forge helm render` keeps the same `app.yaml` source of truth and generates a
local Helm chart. It does not contact the cluster, does not run `helm`, and does
not install a release.

## Raw YAML vs Helm Chart

Raw YAML is direct Kubernetes input. It is useful for learning and for inspecting
the exact objects sent to the API server.

A Helm chart separates reusable templates from environment-specific values:

- `Chart.yaml` describes the chart package.
- `values.yaml` stores the defaults generated from `app.yaml`.
- `templates/` contains Kubernetes templates rendered by Helm.

For v0.3.0, the generated chart covers ConfigMap, Secret, Deployment, Service,
and HPA. It intentionally does not generate a Namespace manifest. Use Helm's
namespace flags instead.

## Generate The Chart

```bash
k8s-forge helm render app.yaml --output charts/
```

By default this creates:

```text
charts/<app.name>/
  Chart.yaml
  values.yaml
  templates/
    _helpers.tpl
    configmap.yaml
    secret.yaml
    deployment.yaml
    service.yaml
    hpa.yaml
```

Use `--chart-name` when the chart directory should differ from `app.name`:

```bash
k8s-forge helm render app.yaml --output charts/ --chart-name weatherapi
```

## Validate With Helm

Run these commands manually after reviewing the generated files:

```bash
helm lint charts/weatherapi
helm template weatherapi charts/weatherapi -n weather
```

Install only when the rendered chart is correct:

```bash
helm upgrade --install weatherapi charts/weatherapi -n weather --create-namespace
helm history weatherapi -n weather
```

## Migration From Raw k8s-forge Manifests

If raw Kubernetes resources already exist from `k8s-forge apply`, Helm may refuse
to install because ownership metadata does not match Helm's release metadata. A
common symptom is an error mentioning existing resources or
`app.kubernetes.io/managed-by: k8s-forge`.

For a clean lab migration, delete the raw generated resources first:

```bash
kubectl delete -f generated-k8s-forge/
helm upgrade --install weatherapi charts/weatherapi -n weather --create-namespace
```

To restart the namespace from scratch in a lab:

```bash
kubectl delete namespace weather
helm upgrade --install weatherapi charts/weatherapi -n weather --create-namespace
```

## Secrets Warning

The generated chart uses Kubernetes `Secret` with `stringData` for readability.
This is pedagogical. It is not production secret management and real secrets
should not be committed to Git. For production, use SOPS, External Secrets,
Sealed Secrets, or a comparable workflow.

## Limits In v0.3.0

- No automatic `helm install` or `helm upgrade`.
- No Helm command wrapper.
- No Namespace template in the chart.
- No Ingress.
- No Linkerd.
- No NetworkPolicy.
- No Kyverno.
- No ArgoCD.
- No Terraform or Ansible.
- No chart OCI publishing.
- No production secret management.
