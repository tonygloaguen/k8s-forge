# Release Checklist v1.0.0

This checklist prepares `k8s-forge` for the final v1.0.0 release hardening phase. It is local and review-oriented: it does not deploy to a cluster, contact a cloud provider, create secrets, push Git changes, or create a tag automatically.

## 1. Prerequisites

- Python 3.11 or newer is available.
- A local virtual environment exists with development dependencies installed.
- The repository contains no real secrets, tokens, credentials, kubeconfig material, private keys, or production inventory.
- The reviewer understands the difference between generated readiness files and runtime validation on an installed platform.

## 2. Git State

Review the repository before release work:

```bash
git status
git log --oneline --max-count=5
git tag --list "v*"
```

Success criteria:

- the working tree is clean before final bump/tag work;
- the latest commits match the intended release content;
- the previous tag is present;
- no unexpected generated output is staged.

## 3. Version Consistency

Before the final release commit, verify the current version locations:

```bash
rg -n "version = |__version__" pyproject.toml src/k8s_forge/__init__.py
k8s-forge --version
```

For post-v1.0.0 development, keep the current package version unchanged until an explicit release bump is requested. Version changes and tags must be separate, deliberate steps.

## 4. Python Quality Gate

Run the full local quality gate:

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src
.venv/bin/python -m pytest -q
.venv/bin/python -m bandit -r src
.venv/bin/python -m pip_audit --skip-editable
```

All commands must complete successfully.

## 5. Package Build

Build the wheel and source distribution:

```bash
.venv/bin/python -m build
```

Success criteria:

- `dist/` contains a wheel;
- `dist/` contains a source distribution;
- package data includes every renderer template directory.

## 6. Release Smoke Test

Run the release script:

```bash
scripts/check_release.sh
```

The script must validate quality gates, build artifacts, install the wheel into a temporary virtual environment, and exercise local CLI flows. It must not run deployment commands, provision infrastructure, execute Ansible playbooks, or contact a cluster.

## 7. CLI Smoke Tests

Review local command help:

```bash
k8s-forge --version
k8s-forge --help
k8s-forge init --help
k8s-forge check --help
k8s-forge render --help
k8s-forge helm render --help
k8s-forge security render --help
k8s-forge capstone render --help
```

Success criteria:

- help output is readable;
- specialized renderers remain separate from raw Kubernetes `render`;
- `--output` and `--force` behavior is documented where relevant.

## 8. Example Validation

Validate the checked-in examples:

```bash
k8s-forge check examples/demo-app.yaml
k8s-forge check examples/admin-api.yaml
```

Success criteria:

- both examples load successfully;
- readiness sections are present and disabled or configured intentionally;
- no example contains real secrets, tokens, credentials, private keys, or production host data.

## 9. Documentation Review

Review:

- `README.md`;
- `CHANGELOG.md`;
- `docs/release-v1.md`;
- `docs/release-checklist.md`;
- `docs/config-reference.md`;
- all `docs/module-*.md`;
- `docs/real-app-weatherapi.md`.

Success criteria:

- module order is correct through Module 14 Capstone;
- Security Audit readiness is Module 13;
- Capstone readiness is Module 14;
- readiness is not described as runtime validation;
- no obsolete `v0.1.0` release text remains in release docs.

## 10. Terrain Validation Plan

Terrain validation stays manual. The release process may document commands to review generated files, but it must not run platform installation or deployment commands automatically.

Recommended manual review:

- render raw Kubernetes manifests locally;
- render each enabled readiness module into a separate output directory;
- inspect generated Markdown, YAML, JSON, and scripts;
- run `k8s-forge doctor` for non-blocking diagnostics.

## 11. Final Bump

Only after all checks pass, perform the explicit release bump in a dedicated commit:

```bash
# update pyproject.toml and src/k8s_forge/__init__.py to 1.0.0
git diff
git status
```

Do not combine the final bump with unrelated refactors.

## 12. Final Tag

After the final bump commit and release checks pass:

```bash
git tag -a v1.0.0 -m "Release v1.0.0"
```

Pushing the branch and tag is a manual maintainer action.

## 13. Success Criteria

The v1.0.0 release is ready when:

- local quality checks pass;
- package build succeeds;
- wheel install smoke test succeeds;
- examples load successfully;
- docs and changelog are current;
- generated templates are packaged;
- no release step performs deployment or runtime mutation;
- final bump and tag are deliberate maintainer actions.
