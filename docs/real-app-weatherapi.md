# Real Application Case Study: weatherapi-platform

This page documents a real validation of the `k8s-forge` MVP on a Debian VM
with an existing FastAPI application named `weatherapi-platform`.

This is a field report, not a new feature. The implementation remains generic:
`weatherapi-platform` and `weatherapi` are real-world example values used only
in this document.

## Pedagogical CLI Output

When replaying this workflow, expect `k8s-forge` to print explanatory messages
before validation, rendering, dry-run, apply, status, and metrics-server checks.
They are intended to make the Kubernetes control loop, Service stability, and
HPA behavior easier to inspect during the TP.

## Validated Environment

Application details:

- repository: `~/projects/weatherapi-platform`
- Dockerfile: `docker/Dockerfile`
- image: `weatherapi:0.1.0`
- Kubernetes namespace: `weather`
- application port: `8000`
- Module 2 replicas: `2`
- HPA range: `2` to `6` Pods at `70%` CPU target
- Kubernetes Service port: `80`
- tested endpoint: `/weather`

Cluster details:

- kind cluster: `devsecops`
- kubectl context: `kind-devsecops`
- final node state: `Ready`

Validated HTTP response:

```json
{"city":"Magny-les-Hameaux","temp_c":4.4,"condition":"pluie","version":"0.1.0"}
```

## Important Boundaries

When an existing application already exists, do not create or use a temporary
`/tmp/demo-app` application. Work from the real application repository.

Do not overwrite an existing `k8s/` directory, Helm chart, or manually managed
Kubernetes manifests that may already be present in the application. Generate
`k8s-forge` output into a separate directory such as `generated-k8s-forge/` and
use a separate config file such as `k8s-forge-app.yaml`.

For Module 2 Helm, `k8s-forge` can generate a separate local chart from
`k8s-forge-app.yaml`. Keep that generated chart separate from any existing Helm
assets unless you intentionally migrate them.

## Real Flow

Start from the existing application repository:

```bash
cd ~/projects/weatherapi-platform
```

Find the Dockerfile:

```bash
find . -maxdepth 3 -iname "Dockerfile" -print
```

Inspect application and container hints:

```bash
grep -RInE "EXPOSE|uvicorn|gunicorn|fastapi|ports:|docker build|IMAGE|PORT" \
  Dockerfile docker compose app Makefile README.md 2>/dev/null | head -80
```

Build the application image:

```bash
make build
```

Load the local image into the kind cluster:

```bash
k8s-forge image load weatherapi:0.1.0 --cluster devsecops
```

Create a dedicated `k8s-forge` configuration file:

```bash
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
```

Validate the generated configuration:

```bash
k8s-forge check k8s-forge-app.yaml
```

Render manifests into a dedicated output directory:

```bash
k8s-forge render k8s-forge-app.yaml \
  --output generated-k8s-forge/
```

Create the namespace before server-side dry-run:

```bash
kubectl create namespace weather
```

Run server-side validation:

```bash
k8s-forge dry-run k8s-forge-app.yaml \
  --output generated-k8s-forge/
```

Apply after reviewing the generated files and dry-run output:

```bash
k8s-forge apply k8s-forge-app.yaml \
  --output generated-k8s-forge/
```

Check Kubernetes resources:

```bash
k8s-forge status weatherapi -n weather
```

Forward the Service locally:

```bash
kubectl -n weather port-forward svc/weatherapi 8080:80
```

Test the FastAPI endpoint:

```bash
curl http://localhost:8080/weather
```

Expected response observed during the test:

```json
{"city":"Magny-les-Hameaux","temp_c":4.4,"condition":"pluie","version":"0.1.0"}
```

## Notes From The Test

`k8s-forge cluster create --name devsecops` can report a node as `NotReady`
immediately after creation. This is expected while kind finishes starting the
node. Wait briefly and rerun:

```bash
k8s-forge cluster status --name devsecops
kubectl get nodes
```

If the cluster already exists, `cluster create` reports:

```text
kind cluster devsecops already exists; skipping create.
```

This is expected. The command is idempotent and does not recreate an existing
cluster.

Server-side dry-run can fail for namespaced resources when the Namespace exists
only in the same dry-run batch. The observed output was:

```text
namespace/weather created (server dry run)
namespaces "weather" not found
```

Create the namespace once, then rerun dry-run:

```bash
kubectl create namespace weather
k8s-forge dry-run k8s-forge-app.yaml --output generated-k8s-forge/
```

After manually creating the namespace, `kubectl apply` may warn about a missing
`kubectl.kubernetes.io/last-applied-configuration` annotation. This warning is
not blocking; `kubectl apply` patches the annotation automatically.


## Module 2 Validation

For the Module 2 Kubernetes raw validation, use two replicas and HPA enabled:

```bash
k8s-forge check k8s-forge-app.yaml
k8s-forge render k8s-forge-app.yaml --output generated-k8s-forge/
kubectl create namespace weather --dry-run=client -o yaml | kubectl apply -f -
k8s-forge dry-run k8s-forge-app.yaml --output generated-k8s-forge/
k8s-forge apply k8s-forge-app.yaml --output generated-k8s-forge/
k8s-forge status weatherapi -n weather

kubectl -n weather get deploy,rs,pods,svc,hpa
kubectl -n weather rollout status deploy/weatherapi
```

Test Kubernetes reconciliation by deleting one Pod:

```bash
POD=$(kubectl -n weather get pod -l app=weatherapi -o jsonpath='{.items[0].metadata.name}')
kubectl -n weather delete pod "$POD"
kubectl -n weather get pods -w
```

The Service should remain stable while the Deployment creates a replacement Pod.

HPA CPU metrics require metrics-server. Without it, `kubectl -n weather get hpa`
may show `<unknown>`, even though the HPA manifest was rendered and applied.


## Helm Follow-Up

After the raw Kubernetes validation succeeds, generate a Helm chart from the same
configuration:

```bash
k8s-forge helm render k8s-forge-app.yaml --output charts/
helm lint charts/weatherapi
helm template weatherapi charts/weatherapi -n weather
```

If the raw resources still exist from `k8s-forge apply`, Helm may refuse to take
ownership of them. For the lab, delete the raw generated resources first or use a
fresh namespace.

## Ingress Follow-Up

For Module 3, enable Ingress in `k8s-forge-app.yaml` with `host: weather.local`. Install ingress-nginx and cert-manager manually, add `127.0.0.1 weather.local` to `/etc/hosts` for direct local testing, then validate with:

```bash
k8s-forge check k8s-forge-app.yaml
k8s-forge render k8s-forge-app.yaml --output generated-k8s-forge/
kubectl -n weather get ingress
curl -H "Host: weather.local" http://127.0.0.1/weather
```

If kind does not expose ports 80/443, use:

```bash
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8082:80
curl -H "Host: weather.local" http://127.0.0.1:8082/weather
```

## Linkerd Follow-Up

After the Ingress validation, create a mesh-specific copy of the app config and enable Linkerd readiness annotations:

```bash
cp k8s-forge-app-ingress.yaml k8s-forge-app-mesh.yaml
```

Add:

```yaml
mesh:
  enabled: true
  provider: linkerd
  inject: true
  annotations:
    linkerd.io/inject: enabled
```

Validate Linkerd manually, then render and upgrade the Helm release:

```bash
linkerd check
k8s-forge helm render k8s-forge-app-mesh.yaml --output charts-generated-mesh
helm upgrade --install weatherapi charts-generated-mesh/weatherapi \
  -n weather-helm \
  --create-namespace
kubectl -n weather-helm rollout restart deploy/weatherapi
kubectl -n weather-helm rollout status deploy/weatherapi --timeout=120s
kubectl -n weather-helm get pods
linkerd stat deploy -n weather-helm
```

Expected signal: the `weatherapi` pod shows `2/2` containers, meaning the application container and the `linkerd-proxy` sidecar are both ready.

## NetworkPolicy Follow-Up

After the Linkerd readiness step, create a NetworkPolicy-specific config:

```bash
cp k8s-forge-app-mesh.yaml k8s-forge-app-netpol.yaml
```

Add:

```yaml
networkPolicy:
  enabled: true
  profile: ingress-only
  ingress:
    enabled: true
    fromNamespaces:
      - ingress-nginx
    ports:
      - 8000
  egress:
    enabled: false
```

Render and upgrade the Helm release:

```bash
k8s-forge helm render k8s-forge-app-netpol.yaml --output charts-generated-netpol
helm upgrade --install weatherapi charts-generated-netpol/weatherapi \
  -n weather-helm \
  --create-namespace
kubectl -n weather-helm get networkpolicy
kubectl -n weather-helm describe networkpolicy weatherapi-ingress-only
```

Then verify the Ingress path still works:

```bash
curl -k --resolve weather.local:8443:127.0.0.1 https://weather.local:8443/weather
curl -k --resolve weather.local:8443:127.0.0.1 https://weather.local:8443/healthz
curl -k --resolve weather.local:8443:127.0.0.1 https://weather.local:8443/readyz
```

If the CNI does not support NetworkPolicy, the object can exist without enforcement.


## Kyverno readiness follow-up

After the NetworkPolicy lab, copy the config and enable the baseline Kyverno policy in Audit mode:

```bash
cp k8s-forge-app-netpol.yaml k8s-forge-app-kyverno.yaml
```

Add `policy.enabled: true`, render raw and Helm output, then validate locally:

```bash
k8s-forge check k8s-forge-app-kyverno.yaml
k8s-forge render k8s-forge-app-kyverno.yaml --output generated-k8s-forge-kyverno/
k8s-forge helm render k8s-forge-app-kyverno.yaml --output charts-generated-kyverno
helm lint charts-generated-kyverno/weatherapi
helm template weatherapi charts-generated-kyverno/weatherapi -n weather-helm
k8s-forge doctor
```

Without Kyverno installed, the policy can be reviewed but the cluster will not create PolicyReports.

## Supply Chain readiness follow-up

After Kyverno readiness, copy the config and enable Supply Chain readiness for the weatherapi image:

```bash
cp k8s-forge-app-kyverno.yaml k8s-forge-app-supplychain.yaml
```

Render the Kubernetes manifests separately from the Supply Chain helper scripts:

```bash
k8s-forge check k8s-forge-app-supplychain.yaml
k8s-forge render k8s-forge-app-supplychain.yaml --output generated-k8s-forge-supplychain/
k8s-forge supply-chain render k8s-forge-app-supplychain.yaml --output generated-supply-chain/
ls -lah generated-supply-chain/
cat generated-supply-chain/README.md
k8s-forge doctor
```

The generated scripts do not contain secrets and do not install Trivy, Syft, or Cosign.
