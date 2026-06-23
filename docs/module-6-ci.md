# Module 6 - GitHub Actions CI Readiness

## Goal

Module 6 adds a pedagogical CI layer. `k8s-forge` generates GitHub Actions workflow files from the same `app.yaml` used for Kubernetes, Helm, Ingress, NetworkPolicy, Kyverno, and Supply Chain readiness.

The generated workflows automate checks that were previously run manually:

- Python formatting and linting;
- type checking;
- tests;
- Python security audits;
- package build;
- local Docker image build inside CI;
- Trivy image scan;
- Syft SBOM generation;
- CI artifact upload.

`k8s-forge` does not push code, publish images, deploy Kubernetes resources, create GitHub secrets, or install GitOps tooling.

## Configuration

```yaml
ci:
  enabled: true
  provider: github-actions
  python:
    enabled: true
    version: "3.12"
    quality:
      ruff: true
      mypy: true
      bandit: true
      pipAudit: true
      pytest: true
      build: true
  container:
    enabled: true
    image: weatherapi:0.1.0
    dockerfile: Dockerfile
    context: .
    scan:
      enabled: true
      tool: trivy
      severity:
        - HIGH
        - CRITICAL
    sbom:
      enabled: true
      tool: syft
      format: cyclonedx-json
  artifacts:
    enabled: true
```

If `ci.container.image` is empty, `k8s-forge` uses `supplyChain.image` when set, then falls back to `app.image`.

## Generate Workflows

Generate into a review directory first:

```bash
k8s-forge ci render app.yaml --output generated-ci/
```

Output:

```text
generated-ci/
  README.md
  .github/
    workflows/
      ci.yml
      security.yml
```

Review the files, then copy the workflows into `.github/workflows/` when ready. Existing files are not overwritten unless `--force` is used.

## ci.yml

`ci.yml` focuses on Python project quality:

```bash
python -m pip install -e ".[dev]"
python -m ruff format --check .
python -m ruff check .
python -m mypy src
python -m pytest -q
python -m bandit -r src
python -m pip_audit --skip-editable
python -m build
```

Enabled checks come from `ci.python.quality`.

## security.yml

`security.yml` focuses on the application image and supply chain:

```bash
docker build -t weatherapi:0.1.0 -f Dockerfile .
trivy image --severity HIGH,CRITICAL weatherapi:0.1.0
trivy image --severity HIGH,CRITICAL --format json --output reports/trivy-image.json weatherapi:0.1.0
syft weatherapi:0.1.0 -o cyclonedx-json=reports/sbom.cdx.json
```

The image is built locally inside the GitHub Actions runner. It is not pushed to a registry.

## Artifacts

When `ci.artifacts.enabled` is true, the workflows upload useful outputs:

- Python package files from `dist/`;
- Trivy and Syft files from `reports/`.

## Why No Deployment Yet

v0.9.0 is CI readiness, not GitOps. The workflows validate code and artifacts, but they do not apply Kubernetes manifests and do not run Helm releases. Deployment automation belongs to a later module.

## Secrets

The generated workflows do not reference `secrets.*`. Registry credentials, Cosign keys, cloud credentials, and GitOps tokens are intentionally outside this version.

## Validation With weatherapi-platform

```bash
k8s-forge check k8s-forge-app-ci.yaml
k8s-forge render k8s-forge-app-ci.yaml --output generated-k8s-forge-ci/
k8s-forge ci render k8s-forge-app-ci.yaml --output generated-ci/
find generated-ci -maxdepth 4 -type f -print
cat generated-ci/README.md
cat generated-ci/.github/workflows/ci.yml
cat generated-ci/.github/workflows/security.yml
k8s-forge doctor
```

Expected result:

- `render` remains Kubernetes-only;
- `ci render` generates CI-only files;
- workflows are readable;
- no secrets are generated;
- no registry push is configured;
- no Kubernetes deployment is configured.

## Limits v0.9.0

- no ArgoCD;
- no GitOps;
- no `kubectl apply` from CI;
- no image push;
- no Cosign signing requirement;
- no PyPI or OCI publication;
- no Terraform or Ansible.
