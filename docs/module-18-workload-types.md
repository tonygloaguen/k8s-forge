# Module 18 - Workload Types

`k8s-forge` supports multiple Kubernetes workload shapes. This matters because not every repository is a web API. Some projects are workers, CLI tools, one-shot jobs, or scheduled jobs.

This module is still readiness-oriented. It generates local Kubernetes manifests from reviewed configuration. It does not build images, run commands, deploy workloads, or prove runtime compatibility.

## YAML model

```yaml
workload:
  type: deployment
  command: []
  args: []
  restartPolicy: Always
  schedule: ""
```

Supported values:

| Type | Kubernetes object | Service | Typical use |
| --- | --- | --- | --- |
| `deployment` | `apps/v1 Deployment` | optional | Web/API workload with a listening port |
| `worker` | `apps/v1 Deployment` | disabled | Long-running background process without HTTP exposure |
| `job` | `batch/v1 Job` | disabled | One-shot CLI or batch task |
| `cronjob` | `batch/v1 CronJob` | disabled | Scheduled CLI or batch task |

## Deployment

Use `deployment` for web applications and APIs. A Service can be generated when `service.enabled=true`, and Ingress remains available only when Service is enabled.

## Worker

Use `worker` for long-running processes that do not expose an HTTP port. Studio and the renderer keep Service disabled for this shape.

## Job

Use `job` for one-shot tasks. `restartPolicy` must be `Never` or `OnFailure`. Service and Ingress are not applicable.

## CronJob

Use `cronjob` for scheduled tasks. `schedule` is required and `restartPolicy` must be `Never` or `OnFailure`. Service and Ingress are not applicable.

## Discovery and Studio

Repository discovery no longer assumes every project is a web application. If a Python CLI entrypoint is plausible but no web framework or port is detected, discovery may suggest `workload.type=job`. If the repository is ambiguous, Studio can create an assisted scaffold after user review.

## Guardrails

- `worker`, `job`, and `cronjob` require `service.enabled=false`.
- `job` and `cronjob` do not render Service or Ingress.
- `cronjob` requires a schedule.
- `job` and `cronjob` reject `restartPolicy=Always`.
- Generated YAML remains a starter configuration and must be reviewed before any manual deployment workflow.
