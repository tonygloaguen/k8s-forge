# k8s-forge Design

## Goal

`k8s-forge` is a small, generic generator for Kubernetes manifests. Users
describe an application in `app.yaml`; the tool validates the configuration and
will render standard YAML manifests.

## Core Rules

- Application names are never hardcoded.
- Runtime values come from the user configuration.
- Rendering should be deterministic to make diffs useful.
- Kubernetes command execution should be explicit and controlled.
- Code should be typed, testable, and low side effect.

## Planned Components

- `cli.py`: Typer command surface.
- `models.py`: Pydantic models for user configuration.
- `config_loader.py`: YAML loading and validation entry points.
- `renderer.py`: future Jinja2-based rendering.
- `kubectl.py`: future safe wrapper around `kubectl`.
- `exceptions.py`: project-specific exceptions.

## MVP Resources

The planned MVP render target is:

- Namespace
- ConfigMap
- Secret
- Deployment
- Service

Ingress, HPA, NetworkPolicy, Helm, Kustomize, and direct Kubernetes API usage
are outside the initial MVP.
