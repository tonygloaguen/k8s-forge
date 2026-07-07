# k8s-forge

`k8s-forge` is a pedagogical DevSecOps Cloud-Native CLI. It generates local readiness assets from a user-owned `app.yaml` so learners can review how an application moves through Kubernetes manifests, Helm, ingress, service mesh readiness, policy, supply chain, CI, GitOps, observability, logging, tracing, Infrastructure as Code, automation, security review, and final Capstone reporting.

Status: v1.4.0 workload types development on top of the stable v1.2.0 baseline. The package version remains unchanged during this implementation. The project is designed for local learning, review, and controlled diagnostics. It is not a deployment platform and does not replace Kubernetes, Helm, ArgoCD, Terraform, Ansible, scanners, or runtime platform validation.

The project is intentionally application-agnostic. Application-specific values must come from `app.yaml`; implementation logic must not hardcode an application name.

## What k8s-forge Does

`k8s-forge` can:

- create a starter `app.yaml` with `init`;
- statically inspect an existing repository with `discover` and generate a starter readiness scaffold for review;
- validate configuration with typed Pydantic models;
- explain an app.yaml file in read-only mode with `explain`;
- run a local browser workflow with `studio` when the optional Studio extra is installed;
- render raw Kubernetes YAML locally;
- generate a local Helm chart;
- generate readiness files for ingress, Linkerd, NetworkPolicy, Kyverno, Supply Chain, CI, GitOps, observability, logging, tracing, Terraform, Ansible, Security Audit, and Capstone review;
- run explicit, guarded cluster-oriented commands such as `dry-run`, `diff`, `apply`, `status`, `cluster`, and `image` when the user chooses them;
- run non-blocking diagnostics with `doctor`;
- keep generated files inspectable before any manual runtime workflow.

## What k8s-forge Does Not Do

`k8s-forge` does not:

- install ingress-nginx, cert-manager, Linkerd, Kyverno, ArgoCD, Prometheus, Grafana, Loki, Tempo, OpenTelemetry Collector, Terraform, Ansible, Trivy, Syft, or Cosign;
- deploy automatically;
- push Git commits or create tags;
- create real secrets, tokens, credentials, private keys, kubeconfig files, or cloud access material;
- run Terraform workflows that create, modify, or delete resources;
- run Ansible playbooks or open remote sessions;
- run runtime scans automatically;
- prove cluster health, compliance, or production readiness.

Readiness files are local educational examples. Runtime validation remains a separate manual workflow.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

k8s-forge --help
k8s-forge init demo-app
k8s-forge discover . --output generated-discovery/
k8s-forge explain generated-discovery/k8s-forge-app.yaml
k8s-forge studio
k8s-forge check app.yaml
k8s-forge render app.yaml --output generated/
```

`demo-app` is only a documentation example. Real values should come from the user configuration.

## Main Commands

```bash
k8s-forge init demo-app
k8s-forge discover . --output generated-discovery/
k8s-forge explain generated-discovery/k8s-forge-app.yaml
k8s-forge studio
k8s-forge check app.yaml
k8s-forge render app.yaml --output generated/
k8s-forge dry-run app.yaml --output generated/
k8s-forge diff app.yaml --output generated/
k8s-forge apply app.yaml --output generated/
k8s-forge status demo-app -n demo-app
k8s-forge doctor
k8s-forge cluster create --name devsecops
k8s-forge image load demo-app:latest --cluster devsecops
```

Specialized renderers stay separate from raw Kubernetes rendering:

```bash
k8s-forge helm render app.yaml --output charts/
k8s-forge supply-chain render app.yaml --output generated-supply-chain/
k8s-forge ci render app.yaml --output generated-ci/
k8s-forge gitops render app.yaml --output generated-gitops/
k8s-forge observability render app.yaml --output generated-observability/
k8s-forge logging render app.yaml --output generated-logging/
k8s-forge tracing render app.yaml --output generated-tracing/
k8s-forge terraform render app.yaml --output generated-terraform/
k8s-forge ansible render app.yaml --output generated-ansible/
k8s-forge security render app.yaml --output generated-security-audit/
k8s-forge capstone render app.yaml --output generated-capstone/
```

## Modules

| Module | Scope | Output | Runtime dependency |
| --- | --- | --- | --- |
| Kubernetes raw | Namespace, ConfigMap, Secret placeholder, Deployment, Service, HPA, Ingress, NetworkPolicy, Kyverno Policy | `generated/` | Kubernetes cluster for runtime use |
| Helm | Local chart from `app.yaml` | `charts/<app>/` | Helm for manual chart validation/use |
| Ingress / TLS | Ingress readiness and cert-manager annotations | raw/Helm manifests | ingress-nginx, cert-manager, DNS/TLS setup |
| Linkerd | Pod template injection annotations | raw/Helm manifests | Linkerd installed manually |
| NetworkPolicy | Ingress-only network policy | raw/Helm manifests | CNI with NetworkPolicy support |
| Kyverno | Namespace Policy in Audit mode | raw/Helm manifests | Kyverno installed manually |
| Supply Chain | Trivy, Syft, optional Cosign helper scripts | `generated-supply-chain/` | Tools installed and run manually |
| CI | GitHub Actions workflows | `generated-ci/` | GitHub Actions after manual repository integration |
| GitOps | ArgoCD Application manifest | `generated-gitops/` | ArgoCD installed and configured manually |
| Observability | ServiceMonitor and Grafana dashboard example | `generated-observability/` | Prometheus Operator and Grafana |
| Logging | LogQL examples, collector notes, Grafana logs dashboard | `generated-logging/` | Loki and collector installed manually |
| Tracing | OTEL notes, TraceQL examples, Grafana traces dashboard | `generated-tracing/` | Instrumentation, collector, Tempo/Grafana |
| Terraform | Local IaC examples | `generated-terraform/` | Terraform run manually if desired |
| Ansible | Local automation examples | `generated-ansible/` | Ansible run manually if desired |
| Security Audit | Local security review and checklist | `generated-security-audit/` | Manual review, no live scan |
| Capstone | Final lab synthesis and v1 readiness notes | `generated-capstone/` | Manual review |
| Repository discovery | Static repository analysis and starter app.yaml scaffold | `generated-discovery/` | Manual review, no runtime proof |
| Explain | Read-only app.yaml explanation and warnings | console output | Local validation only |
| Studio | Local browser workflow for discovery, review, render, and dry-run | `.k8s-forge-studio/` | Optional `[studio]` extra, local lab only |
| Workload types | Native Deployment, Worker, Job, and CronJob rendering | Kubernetes manifests | Review workload shape before deployment |

## Generated Kubernetes Objects

For a complete raw Kubernetes configuration, `render` may write:

```text
generated/00-namespace.yaml
generated/10-configmap.yaml
generated/20-secret.yaml
generated/30-deployment.yaml
generated/40-service.yaml
generated/50-hpa.yaml
generated/60-ingress.yaml
generated/70-networkpolicy.yaml
generated/80-kyverno-policy.yaml
```

Optional resources are generated only when enabled by `app.yaml`. Known generated files are overwritten on each raw render; unrelated files in the output directory are left untouched.

## Examples

- `examples/demo-app.yaml` is a compact generic example.
- `examples/admin-api.yaml` is a second application shape with different ports and options.
- `docs/real-app-weatherapi.md` documents a terrain-style FastAPI scenario.

Validate examples locally:

```bash
k8s-forge check examples/demo-app.yaml
k8s-forge check examples/admin-api.yaml
```

## Guardrails

- `check` validates configuration before rendering.
- `render` writes local Kubernetes YAML only.
- Specialized readiness renderers write local review files only.
- `dry-run`, `diff`, `apply`, `status`, `cluster`, and `image` are explicit user commands.
- `apply` asks for confirmation unless `--yes` is passed.
- External command execution stays behind narrow wrappers.
- Tests mock external commands and do not depend on a real Kubernetes cluster.

## Secrets Warning

Do not commit real secrets. Example values such as `change-me` are placeholders. Kubernetes Secret manifests are generated for readability in a lab context and must not be treated as real secret management. Use an external secret manager, Sealed Secrets, External Secrets, Vault, or another approved workflow for real environments.

## Documentation

- [Getting started](docs/getting-started.md)
- [Debian/Ubuntu installation](docs/debian-install.md)
- [Configuration reference](docs/config-reference.md)
- [Operational workflow](docs/operations.md)
- [Module 2 Kubernetes raw workflow](docs/module-2-kubernetes.md)
- [Module 2 Helm workflow](docs/module-2-helm.md)
- [Module 3 Ingress workflow](docs/module-3-ingress.md)
- [Module 3 Linkerd service mesh workflow](docs/module-3-linkerd.md)
- [Module 4 NetworkPolicy workflow](docs/module-4-networkpolicy.md)
- [Module 4 Kyverno workflow](docs/module-4-kyverno.md)
- [Module 5 Supply Chain workflow](docs/module-5-supply-chain.md)
- [Module 6 CI readiness workflow](docs/module-6-ci.md)
- [Module 7 ArgoCD GitOps readiness workflow](docs/module-7-gitops-argocd.md)
- [Module 8 Observability readiness workflow](docs/module-8-observability.md)
- [Module 9 Logging readiness workflow](docs/module-9-logging.md)
- [Module 10 Tracing readiness workflow](docs/module-10-tracing.md)
- [Module 11 Terraform readiness workflow](docs/module-11-terraform.md)
- [Module 12 Ansible readiness workflow](docs/module-12-ansible.md)
- [Module 13 Security Audit readiness workflow](docs/module-13-security-audit.md)
- [Module 14 Capstone readiness workflow](docs/module-14-capstone.md)
- [Module 15 Repository Discovery workflow](docs/module-15-repository-discovery.md)
- [Module 16 Explain app configuration](docs/module-16-explain.md)
- [Module 17 Studio local GUI](docs/module-17-studio.md)
- [Module 18 Workload Types](docs/module-18-workload-types.md)
- [v1.0.0 release hardening](docs/release-v1.md)
- [Release checklist](docs/release-checklist.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Real app case study: weatherapi-platform](docs/real-app-weatherapi.md)
- [Design notes](docs/design.md)

## Release Hardening

Run the local release gate before a final v1.0.0 bump/tag:

```bash
scripts/check_release.sh
```

The release gate checks Python quality, package build, wheel installation, CLI smoke tests, and local manifest rendering. It does not deploy, install platform components, contact a cloud provider, or require a Kubernetes cluster.

## Development Checks

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src
.venv/bin/python -m pytest -q
.venv/bin/python -m bandit -r src
.venv/bin/python -m pip_audit --skip-editable
.venv/bin/python -m build
```
