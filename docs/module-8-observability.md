# Module 8 - Observability Readiness

## Goal

Module 8 prepares observability with Prometheus Operator `ServiceMonitor` resources and a local Grafana dashboard JSON example. `k8s-forge` generates files and explains prerequisites, but it does not install Prometheus, Grafana, Loki, kube-prometheus-stack, create secrets, call Grafana APIs, run `kubectl apply`, or run `helm install`.

## What Observability Adds

Observability helps operators understand application and cluster behavior.

- Metrics are numeric time series, commonly scraped by Prometheus.
- Logs are event records. Loki is not included in v0.11.0.
- Traces follow requests across services. Tracing is future work.

In v0.11.0, `k8s-forge` focuses on metrics readiness and dashboard review.

## Configuration

```yaml
observability:
  enabled: true
  provider: prometheus
  metrics:
    enabled: true
    path: /metrics
    portName: http
    interval: 30s
  serviceMonitor:
    enabled: true
    namespace: weather-helm
    labels: {}
  grafana:
    enabled: true
    dashboard:
      enabled: true
      title: weatherapi
  alerts:
    enabled: false
```

## Generate Files

```bash
k8s-forge observability render app.yaml --output generated-observability/
```

Output:

```text
generated-observability/
  README.md
  prometheus/
    servicemonitor.yaml
  grafana/
    dashboard.json
```

## ServiceMonitor

A `ServiceMonitor` is a Prometheus Operator custom resource. It tells Prometheus how to scrape a Kubernetes Service. The target Service must expose a named port, so `k8s-forge` names the generated Service port `http`.

The `ServiceMonitor` is only accepted by Kubernetes when `monitoring.coreos.com` CRDs are installed manually, usually through a monitoring stack such as kube-prometheus-stack.

## Grafana Dashboard JSON

The generated dashboard is a local JSON model. It is not imported automatically and it contains no datasource credentials. Import it manually after Grafana and Prometheus are installed and configured.

The application must expose a real `/metrics` endpoint before application-specific panels become useful.

## Doctor

`k8s-forge doctor` checks observability readiness non-destructively:

```bash
kubectl get crd servicemonitors.monitoring.coreos.com
kubectl get crd prometheusrules.monitoring.coreos.com
kubectl get ns monitoring
kubectl -n monitoring get deploy
kubectl -n monitoring get svc
```

Missing CRDs or monitoring namespace are reported as non-blocking readiness gaps.

## Validation Flow

```bash
k8s-forge check k8s-forge-app-observability.yaml
k8s-forge render k8s-forge-app-observability.yaml --output generated-k8s-forge-observability/
k8s-forge observability render k8s-forge-app-observability.yaml --output generated-observability/
find generated-observability -maxdepth 4 -type f -print
cat generated-observability/README.md
cat generated-observability/prometheus/servicemonitor.yaml
cat generated-observability/grafana/dashboard.json
k8s-forge doctor
```

## Limits v0.11.0

- no Prometheus installation;
- no Grafana installation;
- no Loki, Promtail, or OpenTelemetry Collector;
- no Grafana datasource or API call;
- no dashboard import automation;
- no credentials or secrets;
- no `kubectl apply`;
- no `helm install`;
- no alert rendering yet, even when `alerts.enabled` is true.
