# Troubleshooting

This page records real issues observed while installing and using `k8s-forge`
on a Debian VM with a local kind cluster.

| Observed error or output | Probable cause | Solution | Verification command |
| --- | --- | --- | --- |
| `bash: cd: /home/gloaguen/projets: No such file or directory` | The `~/projets` directory does not exist on the VM. | Create it with `mkdir -p ~/projets`, then retry `cd ~/projets`. | `test -d ~/projets && pwd` |
| Repository cloned into `~` instead of `~/projets` | The target directory was missing, so cloning happened from the home directory. | Move it with `mkdir -p ~/projets && mv ~/k8s-forge ~/projets/`, or clone again from `~/projets`. | `test -d ~/projets/k8s-forge` |
| `ensurepip is not available` | Debian/Ubuntu virtual environment support is not installed. | Run `sudo apt update` and `sudo apt install -y python3-venv python3-pip`. For version-specific Python, install `python3.13-venv python3-pip` or the matching package. | `python3 -m venv .venv` |
| `.venv/bin/activate: No such file or directory` | The virtual environment was not created successfully. | Run `rm -rf .venv`, then `python3 -m venv .venv`, then `source .venv/bin/activate`. | `test -f .venv/bin/activate` |
| `bash: python: command not found` | Debian may provide `python3` without a global `python` alias. | Outside a venv, use `python3`. Inside the activated venv, use `python`. | `python3 --version` and, after activation, `python --version` |
| `k8s-forge: command not found` | The package is not installed in the active virtual environment, or the venv is not active. | Activate the venv and run `python -m pip install -e ".[dev]"`. | `k8s-forge --help` |
| `NotReady` immediately after `cluster create` | The kind node was created only a few seconds ago and is still starting, or the Ready wait timed out. | Recent `k8s-forge` versions wait for nodes after creation. If the wait fails, run `kubectl get nodes` and `kubectl get pods -A` to inspect startup. | `kubectl get nodes` |
| `kind cluster devsecops already exists; skipping create.` | The requested kind cluster already exists. | No action is required. `cluster create` is idempotent and does not recreate an existing cluster. | `kind get clusters` |
| `namespace/weather created (server dry run)` followed by `namespaces "weather" not found` during `dry-run` | Server-side dry-run simulates namespace creation but does not persist it before validating namespaced resources. | `k8s-forge` now warns before dry-run when the namespace is missing. Create the namespace once with `kubectl create namespace weather`, then rerun `k8s-forge dry-run k8s-forge-app.yaml --output generated-k8s-forge/`. | `kubectl get namespace weather` |
| `missing the kubectl.kubernetes.io/last-applied-configuration annotation` | The namespace was created manually instead of through `kubectl apply`, so it lacks the last-applied annotation. | This warning is non-blocking. `kubectl apply` will patch the annotation automatically. | Rerun `k8s-forge apply ...` and inspect the output. |
| `<unknown>` in HPA `TARGETS` | metrics-server is absent, not ready, or cannot scrape metrics. | Check metrics-server and install it manually for kind if HPA CPU metrics are required. | `kubectl -n kube-system get deploy metrics-server` |
| Only one Pod appears when Module 2 expects multiple Pods | `app.replicas` is still `1`, or HPA min replicas is not configured. | Set `app.replicas: 2` and, if HPA is enabled, `autoscaling.minReplicas: 2`. | `kubectl -n <namespace> get deploy,pods,hpa` |
| `weather.local` does not resolve | Local DNS does not know the lab hostname. | Add `127.0.0.1 weather.local` to `/etc/hosts` manually. | `getent hosts weather.local` |
| Ingress returns connection refused on kind | kind was created without ports 80/443 mapped, or ingress-nginx is not ready. | Use port-forwarding or recreate kind with extraPortMappings. | `kubectl -n ingress-nginx get deploy,pods,svc` |
| TLS certificate is not ready | cert-manager or the referenced ClusterIssuer is missing or not ready. | Install cert-manager and create the ClusterIssuer manually. | `kubectl get clusterissuer && kubectl -n <namespace> describe certificate` |
| Pods stay `1/1` after enabling mesh | Linkerd is not installed, the workload was not restarted, or injection is disabled. | Run `linkerd check`, verify `mesh.enabled` and `mesh.inject`, then restart the Deployment. | `kubectl -n <namespace> get pods` |
| `linkerd` command not found | Linkerd CLI is not installed or not in `PATH`. | Install the Linkerd CLI manually. | `linkerd version --client` |
| Linkerd metrics missing | Linkerd control plane or Viz is absent/not ready. | Validate Linkerd manually; install Viz only if mesh metrics are needed. | `linkerd check && linkerd viz check` |
| NetworkPolicy object exists but traffic is not restricted | The CNI may not enforce NetworkPolicy. | Use a NetworkPolicy-capable CNI such as Calico or Cilium for enforcement. | `kubectl -n kube-system get pods` |
| Application unreachable after NetworkPolicy | The allowed namespace or pod port is wrong. | Check ingress-nginx namespace and use the application container port, not Service port. | `kubectl -n <namespace> describe networkpolicy <app>-ingress-only` |

## General Debugging Commands

```bash
k8s-forge doctor
kubectl config current-context
kubectl get nodes
kind get clusters
```

For application runtime issues, inspect Kubernetes resources directly:

```bash
kubectl -n <namespace> get deploy,po,svc
kubectl -n <namespace> describe pod <pod-name>
kubectl -n <namespace> logs <pod-name>
```

| `Kyverno does not appear to be installed in this cluster.` | Kyverno namespace, deployments, or CRDs are missing. | Install and validate Kyverno manually before expecting PolicyReports. | `kubectl -n kyverno get pods` |
| No PolicyReports are visible | Kyverno is absent, not ready, or no reports have been created yet. | Check Kyverno pods and CRDs, then re-apply or wait for background scans. | `kubectl get policyreport -A` |

| `Trivy is not installed.` | Trivy is missing from PATH. | Install Trivy manually before running generated scan scripts. | `trivy --version` |
| `Syft is not installed.` | Syft is missing from PATH. | Install Syft manually before generating SBOMs. | `syft version` |
| `Cosign is not installed.` | Cosign is missing from PATH. | Install Cosign manually before signing or verifying images. | `cosign version` |
| Cosign fails on a local image | The image is not registry-backed. | Push the image to a registry or keep signing disabled for local labs. | `cosign verify IMAGE` |
