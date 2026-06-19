# Agent Instructions

These instructions apply to future Codex agents working on this repository.

- Keep changes small and focused.
- Do not hardcode any application name.
- Example documentation may use `demo-app`, but implementation logic must stay generic.
- Never run a real `kubectl apply` in tests.
- Never let tests depend on a real Kubernetes cluster.
- Never put real secrets in examples, tests, or generated fixtures.
- Prefer typed, testable functions with minimal side effects.
- Keep Kubernetes command execution behind a narrow wrapper.
- Mock external command execution in tests.
- Run tests and quality checks after modifying code when tooling is available:
  - `ruff format --check .`
  - `ruff check .`
  - `mypy src`
  - `bandit -r src`
  - `pip-audit --skip-editable`
  - `pytest -q`
