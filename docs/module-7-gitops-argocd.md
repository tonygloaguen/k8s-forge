# Module 7 - ArgoCD GitOps Readiness

## Goal

Module 7 prepares GitOps with ArgoCD. `k8s-forge` generates local ArgoCD manifest examples from `app.yaml`, but it does not install ArgoCD, push Git commits, create credentials, apply manifests, or synchronize applications.

## What GitOps Adds

Kubernetes raw manifests and Helm charts describe application resources. CI validates code and artifacts. GitOps adds a delivery control loop: a Git repository becomes the desired state, and ArgoCD compares that desired state with the cluster.

In v0.10.0, `k8s-forge` generates an ArgoCD `Application` pointing to a Helm chart path in Git.

## Configuration

```yaml
gitops:
  enabled: true
  provider: argocd
  application:
    name: weatherapi
    namespace: argocd
    project: default
  destination:
    server: https://kubernetes.default.svc
    namespace: weather-helm
  source:
    repoURL: https://github.com/tonygloaguen/weatherapi-platform.git
    targetRevision: main
    path: charts-generated/weatherapi
    type: helm
  syncPolicy:
    automated: false
    prune: false
    selfHeal: false
```

## Generate Files

```bash
k8s-forge gitops render app.yaml --output generated-gitops/
```

Output:

```text
generated-gitops/
  README.md
  argocd/
    application.yaml
```

## ArgoCD Application

The generated `Application` contains:

- `source.repoURL`: Git repository containing the desired state;
- `source.targetRevision`: branch, tag, or commit;
- `source.path`: path to the Helm chart inside the repo;
- `destination.server`: Kubernetes API target from ArgoCD's point of view;
- `destination.namespace`: namespace where the app should be deployed;
- `syncPolicy`: manual by default.

## Manual Sync By Default

`syncPolicy.automated` is false by default. This keeps the lab explicit: ArgoCD can show drift and pending changes, but it does not sync automatically unless the user chooses to enable it.

`prune` can delete resources that disappear from Git. `selfHeal` can revert manual cluster changes. Both are disabled by default in v0.10.0.

## Credentials

Private repository credentials must be configured manually in ArgoCD. `k8s-forge` does not generate GitHub secrets, ArgoCD repository credentials, tokens, passwords, or SSH keys.

## Doctor

`k8s-forge doctor` checks ArgoCD readiness non-destructively:

```bash
argocd version --client
kubectl get ns argocd
kubectl -n argocd get deploy
kubectl get crd applications.argoproj.io
```

Missing ArgoCD is not an error for file generation. It only means the generated Application cannot be accepted by the cluster until ArgoCD CRDs are installed manually.

## Validation Flow

```bash
k8s-forge check k8s-forge-app-gitops.yaml
k8s-forge render k8s-forge-app-gitops.yaml --output generated-k8s-forge-gitops/
k8s-forge gitops render k8s-forge-app-gitops.yaml --output generated-gitops/
find generated-gitops -maxdepth 4 -type f -print
cat generated-gitops/README.md
cat generated-gitops/argocd/application.yaml
k8s-forge doctor
```

## Limits v0.10.0

- no ArgoCD installation;
- no ArgoCD login;
- no `argocd app sync`;
- no `kubectl apply`;
- no Git push;
- no credentials;
- no `AppProject`;
- no Flux;
- no raw GitOps source;
- no Terraform, Ansible, or observability.
