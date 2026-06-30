# Module 10 - Tracing Readiness

Module 10 prepares application tracing with OpenTelemetry, OTLP, Tempo, TraceQL, and a Grafana dashboard JSON example. `k8s-forge` generates local files and explains prerequisites, but it does not install OpenTelemetry Collector, Tempo, Grafana, Jaeger, create secrets, configure datasources, call Grafana APIs, run `kubectl apply`, or run Helm install commands.

## What Tracing Adds

Metrics show numeric signals. Logs show timestamped events. Traces show how one request moves through code and across services. A trace is made of spans; a parent span can contain child spans for nested work such as HTTP handlers, database calls, or outbound requests.

## Configuration

```yaml
tracing:
  enabled: true
  provider: opentelemetry
  backend:
    type: tempo
    namespace: monitoring
    datasourceName: Tempo
  collector:
    enabled: true
    type: opentelemetry-collector
    endpoint: http://otel-collector.monitoring.svc.cluster.local:4318
    protocol: otlp-http
  instrumentation:
    enabled: true
    mode: env
    serviceName: weatherapi
  grafana:
    enabled: true
    dashboard:
      enabled: true
      title: weatherapi traces
  examples:
    enabled: true
```

Only `opentelemetry` with a `tempo` backend model is supported in v0.13.0. Jaeger is mentioned as a common alternative, but it is not a supported provider in this version.

## Render Tracing Readiness Files

```bash
k8s-forge tracing render app.yaml --output generated-tracing/
```

Generated files:

```text
generated-tracing/
  README.md
  opentelemetry/
    instrumentation-notes.md
    otel-env.md
  tempo/
    traceql-examples.md
  grafana/
    traces-dashboard.json
  collector/
    collector-notes.md
```

## OpenTelemetry And OTLP

OpenTelemetry is the vendor-neutral standard used for traces. OTLP is the export protocol. `otlp-http` commonly uses port `4318` with `http/protobuf`; `otlp-grpc` commonly uses port `4317` with `grpc`.

The generated `otel-env.md` is documentation only. It does not patch Kubernetes manifests and does not instrument application code.

## Instrumentation Notes

Real tracing depends on the application language and framework. Useful semantic conventions include:

- `service.name`
- `deployment.environment`
- `k8s.namespace.name`
- `k8s.pod.name`
- `http.route`
- `http.method`
- `http.status_code`

`k8s-forge` does not perform auto-instrumentation, sidecar injection, or mutation webhook setup.

## TraceQL Examples

Generated examples include:

```traceql
{ resource.service.name = "weatherapi" }
{ resource.service.name = "weatherapi" && resource.k8s.namespace.name = "weather" }
{ span.http.route = "/weather" }
{ span.http.method = "GET" }
{ span.http.status_code >= 500 }
```

TraceQL attributes depend on the instrumentation and SDK. If queries return no data, inspect real trace attributes in Grafana Explore and adapt them.

## Grafana Dashboard

The dashboard JSON is a local model. Import it manually only after Grafana and a Tempo datasource exist. `k8s-forge` does not create the datasource and does not call the Grafana API.

## Collector Notes

OpenTelemetry Collector is used as the pedagogical collector model. A real tracing stack must be installed and configured manually. The collector receives OTLP data from instrumented applications and exports it to a backend such as Tempo.

## Doctor

`k8s-forge doctor` checks tracing readiness non-destructively. It looks for Tempo, OpenTelemetry Collector, Grafana, and Jaeger in cluster pod listings, but missing components are non-blocking.

## Validation Flow

```bash
k8s-forge check k8s-forge-app-tracing.yaml
k8s-forge render k8s-forge-app-tracing.yaml --output generated-k8s-forge-tracing/
k8s-forge tracing render k8s-forge-app-tracing.yaml --output generated-tracing/ --force
find generated-tracing -maxdepth 4 -type f -print
cat generated-tracing/README.md
cat generated-tracing/opentelemetry/instrumentation-notes.md
cat generated-tracing/opentelemetry/otel-env.md
cat generated-tracing/tempo/traceql-examples.md
cat generated-tracing/grafana/traces-dashboard.json
cat generated-tracing/collector/collector-notes.md
k8s-forge doctor
```

## Limits v0.13.0

- no OpenTelemetry Collector installation;
- no Tempo installation;
- no Grafana installation or datasource creation;
- no Jaeger installation;
- no dashboard import;
- no secrets, credentials, or tokens;
- no cluster apply commands;
- no auto-instrumentation;
- no sidecar injection or mutation webhook;
- no GitOps integration for tracing files.
