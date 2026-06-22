# Module 2 Kubernetes Raw Workflow

This page documents the `k8s-forge` v0.2.0-oriented workflow for the raw
Kubernetes part of the DevSecOps Cloud-Native practical work. It stays strictly
in Kubernetes manifests and `kubectl`; it does not use Helm, Ingress, Linkerd,
NetworkPolicy, Kyverno, ArgoCD, Terraform, or Ansible.

## What Module 2 Demonstrates

- A Deployment with multiple replicas, for example `replicas: 2`.
- A stable Service in front of changing Pods.
- Kubernetes reconciliation after deleting a Pod.
- A declared HorizontalPodAutoscaler.
- The behavior of HPA when `metrics-server` is missing or not ready.

`app.replicas` is the initial Deployment replica count. When autoscaling is
enabled, `autoscaling.minReplicas` and `autoscaling.maxReplicas` define the HPA
range. The Service continues routing to matching Pods through labels even when
Pods are replaced by the Deployment controller.

## Autoscaling Configuration

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 6
  targetCPUUtilizationPercentage: 70
```

This renders `generated-k8s-forge/50-hpa.yaml`. The scaling decision depends on
Kubernetes metrics. On kind, HPA CPU `TARGETS` may stay `<unknown>` until
`metrics-server` is installed and working.

`k8s-forge doctor` checks for `metrics-server` with:

```bash
kubectl -n kube-system get deploy metrics-server
```

It reports a warning when metrics-server is absent, but it does not install it.

## Full weatherapi-platform Flow

```bash
cd ~/projects/weatherapi-platform

make build
k8s-forge image load weatherapi:0.1.0 --cluster devsecops

k8s-forge init weatherapi \
  --image weatherapi:0.1.0 \
  --namespace weather \
  --port 8000 \
  --replicas 2 \
  --hpa \
  --hpa-min 2 \
  --hpa-max 6 \
  --hpa-cpu 70 \
  --output k8s-forge-app.yaml \
  --force

k8s-forge check k8s-forge-app.yaml
k8s-forge render k8s-forge-app.yaml --output generated-k8s-forge/
kubectl create namespace weather --dry-run=client -o yaml | kubectl apply -f -
k8s-forge dry-run k8s-forge-app.yaml --output generated-k8s-forge/
k8s-forge apply k8s-forge-app.yaml --output generated-k8s-forge/
k8s-forge status weatherapi -n weather

kubectl -n weather get deploy,rs,pods,svc,hpa
kubectl -n weather rollout status deploy/weatherapi
```

## Reconciliation Test

Delete one Pod and watch the Deployment recreate a replacement:

```bash
POD=$(kubectl -n weather get pod -l app=weatherapi -o jsonpath='{.items[0].metadata.name}')
kubectl -n weather delete pod "$POD"
kubectl -n weather get pods -w
```

Expected behavior: the deleted Pod terminates, and Kubernetes creates a new Pod
to return to the desired replica count. The Service remains stable because it
selects Pods by label.

## HTTP Test

```bash
kubectl -n weather port-forward svc/weatherapi 8080:80
curl http://localhost:8080/weather
curl http://localhost:8080/healthz
curl http://localhost:8080/readyz
```

## Optional metrics-server Setup For kind

Run these commands manually only when you want HPA CPU metrics in a local kind
cluster:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

kubectl -n kube-system patch deploy metrics-server --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
```

Then verify:

```bash
kubectl -n kube-system get deploy metrics-server
kubectl -n weather get hpa
```

If metrics are not ready yet, HPA may show `<unknown>`. That is a Kubernetes
metrics availability issue, not a manifest rendering failure.
