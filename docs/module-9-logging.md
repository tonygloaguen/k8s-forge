# Module 9 - Logging Readiness

Module 9 prepares Kubernetes logging with Loki, LogQL, a collector model, and a Grafana dashboard JSON example. `k8s-forge` generates local files and explains prerequisites, but it does not install Loki, Grafana, Promtail, Alloy, create secrets, configure datasources, call Grafana APIs, run `kubectl apply`, or run Helm install commands.

## What Logging Adds

Metrics show numeric signals such as CPU, memory, and request rates. Logs show timestamped application and platform events. Traces follow a request across services. This module focuses on logs written by application containers to stdout and stderr.

## Configuration

```yaml
logging:
  enabled: true
  provider: loki
  applicationLogs:
    enabled: true
    source: stdout
  loki:
    namespace: monitoring
    datasourceName: Loki
  collector:
    enabled: true
    type: promtail
  grafana:
    enabled: true
    dashboard:
      enabled: true
      title: weatherapi logs
  queries:
    enabled: true
```

Only `loki` and `promtail` are supported in v0.12.0. Alloy is documented as a future option, not generated.

## Render Logging Readiness Files

```bash
k8s-forge logging render app.yaml --output generated-logging/
```

Generated files:

```text
generated-logging/
  README.md
  loki/
    logql-queries.md
  grafana/
    logs-dashboard.json
  collector/
    collector-notes.md
```

## LogQL Examples

The generated queries include examples such as:

```logql
{namespace="weather"}
{namespace="weather"} |= "ERROR"
{namespace="weather", app="weatherapi"}
count_over_time({namespace="weather"}[5m])
rate({namespace="weather"}[5m])
```

Loki labels depend on the collector configuration. If a query returns no data, inspect labels in Grafana Explore and adapt selectors.

## Grafana Dashboard

The dashboard JSON is a local model. Import it manually only after Grafana and a Loki datasource exist. `k8s-forge` does not create the datasource and does not call the Grafana API.

## Collector Notes

Promtail is used as the pedagogical collector model. A real logging stack must be installed and configured manually. The collector reads Kubernetes container logs from stdout and stderr, adds labels, and sends logs to Loki.

## Doctor

`k8s-forge doctor` checks logging readiness non-destructively. It looks for Loki, Grafana, Promtail, and Alloy in cluster pod listings, but missing components are non-blocking.

## Validation Flow

```bash
k8s-forge check k8s-forge-app-logging.yaml
k8s-forge render k8s-forge-app-logging.yaml --output generated-k8s-forge-logging/
k8s-forge logging render k8s-forge-app-logging.yaml --output generated-logging/
find generated-logging -maxdepth 4 -type f -print
cat generated-logging/README.md
cat generated-logging/loki/logql-queries.md
cat generated-logging/grafana/logs-dashboard.json
cat generated-logging/collector/collector-notes.md
k8s-forge doctor
```

## Limits v0.12.0

- no Loki installation;
- no Promtail or Alloy installation;
- no Grafana datasource creation;
- no dashboard import;
- no secrets or credentials;
- no cluster apply commands;
- no tracing or OpenTelemetry Collector;
- no GitOps integration for logging files.
