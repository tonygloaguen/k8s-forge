# Module 5 - Supply Chain Readiness

This module prepares image supply-chain validation for a containerized application. It generates local helper scripts and explanatory documentation, but it does not install tools or sign images automatically.

## What Supply Chain Means Here

For this project, supply chain readiness covers three practical checks:

- vulnerability scanning with Trivy;
- Software Bill of Materials generation with Syft;
- optional image signing and verification with Cosign.

These checks happen around the container image referenced by `app.yaml`. They complement Kubernetes manifests, Helm, Ingress, service mesh readiness, NetworkPolicy, and Kyverno.

## Configuration

```yaml
supplyChain:
  enabled: true
  image: weatherapi:0.1.0
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
  signing:
    enabled: false
    tool: cosign
    keyless: true
```

If `supplyChain.image` is empty, `k8s-forge` uses `app.image`.

## Generated Files

```bash
k8s-forge supply-chain render app.yaml --output generated-supply-chain/
```

The command can generate:

```text
generated-supply-chain/
  README.md
  scan-image.sh
  generate-sbom.sh
  reports/
```

When signing is enabled, it also generates:

```text
  sign-image.sh
  verify-image.sh
```

## Trivy

Trivy scans the image for known vulnerabilities.

Example generated command:

```bash
trivy image --severity HIGH,CRITICAL weatherapi:0.1.0
```

A JSON report is also generated under `reports/trivy-image.json`.

## Syft

Syft generates an SBOM so image contents and dependencies are traceable.

For `cyclonedx-json`, the generated output is:

```text
reports/sbom.cdx.json
```

Other supported formats are `spdx-json` and `syft-json`.

## Cosign

Cosign can sign and verify images. In v0.8.0, signing is disabled by default.

Cosign signing usually requires a registry-backed image reference. Local-only images can be scanned and inspected, but may not be suitable for signing and verification.

`k8s-forge` never generates signing keys, tokens, passwords, or secrets.

## Local Image vs Registry Image

An image such as `weatherapi:0.1.0` can be scanned locally and can be used in a kind cluster after `k8s-forge image load`.

For signing and verification, prefer an image pushed to a registry, for example:

```text
ghcr.io/example/weatherapi:0.1.0
```

## Latest Tag Warning

The `latest` tag is convenient in local labs but weak for traceability. Prefer explicit version tags or immutable digests for supply-chain validation.

## Doctor

Use:

```bash
k8s-forge doctor
```

It checks whether `trivy`, `syft`, and `cosign` are available. Missing tools are reported as non-blocking readiness gaps.

## weatherapi-platform Validation

```bash
cp k8s-forge-app-kyverno.yaml k8s-forge-app-supplychain.yaml
```

Add the `supplyChain` section, then run:

```bash
k8s-forge check k8s-forge-app-supplychain.yaml

k8s-forge render k8s-forge-app-supplychain.yaml   --output generated-k8s-forge-supplychain/

k8s-forge supply-chain render k8s-forge-app-supplychain.yaml   --output generated-supply-chain/

ls -lah generated-supply-chain/
cat generated-supply-chain/README.md
cat generated-supply-chain/scan-image.sh
cat generated-supply-chain/generate-sbom.sh

k8s-forge doctor
```

## Limits in v0.8.0

- No automatic Trivy installation.
- No automatic Syft installation.
- No automatic Cosign installation.
- No automatic registry push.
- No automatic image signature.
- No generated keys or secrets.
- No SLSA attestations.
- No GitHub Actions, ArgoCD, Terraform, or Ansible integration.
