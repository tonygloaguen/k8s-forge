# Module 11 - Terraform Readiness

Module 11 prepares Infrastructure as Code examples with Terraform. `k8s-forge` generates local files and explains the concepts, but it does not provision infrastructure, contact a cloud provider, contact the cluster, create access material, generate cluster config files, or run Terraform.

## What Infrastructure As Code Adds

Infrastructure as Code keeps infrastructure intent in versioned text files. Terraform models infrastructure through providers, variables, resources, outputs, and state. In this module the files are deliberately educational: they show how a Kubernetes application could be represented, but they are not an automated provisioning workflow.

## Configuration

```yaml
terraform:
  enabled: true
  projectName: weatherapi
  backend:
    type: local
  providers:
    kubernetes:
      enabled: true
    helm:
      enabled: true
    cloud:
      enabled: false
  modules:
    enabled: true
  examples:
    enabled: true
```

Only the `local` backend model is supported in v0.14.0. Kubernetes and Helm provider examples can be rendered. The cloud provider switch is accepted by the model but no real cloud provider is generated.

## Render Terraform Readiness Files

```bash
k8s-forge terraform render app.yaml --output generated-terraform/
```

Generated files:

```text
generated-terraform/
  README.md
  versions.tf
  providers.tf
  variables.tf
  main.tf
  outputs.tf
```

## Generated File Roles

- `versions.tf`: Terraform and provider version requirements with a local backend model.
- `providers.tf`: Kubernetes and Helm provider examples when enabled.
- `variables.tf`: inputs for project, app, namespace, chart path, and an optional existing local cluster config path.
- `main.tf`: small namespace and Helm release examples controlled by variables and disabled by default.
- `outputs.tf`: readable values for review.

## State And Backends

Terraform stores state to remember known resources. v0.14.0 uses a local backend model only. Remote backends are intentionally excluded because they need organization-specific storage, access rules, and sensitive configuration.

## Safety Boundaries

`k8s-forge` does not run Terraform commands that create, modify, or delete resources. It does not create cloud provider configuration, access keys, kubeconfig files, cluster resources, ArgoCD changes, or deployment workflows.

The generated files are local examples to read and adapt. Any real Terraform workflow remains manual and must be reviewed separately.

## Doctor

`k8s-forge doctor` checks whether Terraform is available by running a version command only. Missing Terraform is non-blocking for readiness file generation.

## Validation Flow

```bash
k8s-forge check k8s-forge-app-terraform.yaml
k8s-forge render k8s-forge-app-terraform.yaml --output generated-k8s-forge-terraform/
k8s-forge terraform render k8s-forge-app-terraform.yaml --output generated-terraform/ --force
find generated-terraform -maxdepth 3 -type f -print
cat generated-terraform/README.md
cat generated-terraform/versions.tf
cat generated-terraform/providers.tf
cat generated-terraform/variables.tf
cat generated-terraform/main.tf
cat generated-terraform/outputs.tf
k8s-forge doctor
```

## Limits v0.14.0

- no real provisioning;
- no remote backend;
- no real cloud provider;
- no cloud access material;
- no generated kubeconfig file;
- no cluster creation;
- no Kubernetes apply workflow;
- no Helm install workflow;
- no Ansible;
- no automatic GitOps integration.

Ansible remains a future, separate readiness layer.
