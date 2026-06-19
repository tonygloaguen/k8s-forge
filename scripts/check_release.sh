#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="${PYTHON}"
elif [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi
DIST_DIR="${ROOT_DIR}/dist"
VENV_DIR="/tmp/k8s-forge-release-venv"
APP_FILE="/tmp/k8s-forge-wheel-app.yaml"
GENERATED_DIR="/tmp/k8s-forge-wheel-generated"

echo "==> Cleaning previous release check artifacts"
rm -rf "${DIST_DIR}" "${VENV_DIR}" "${APP_FILE}" "${GENERATED_DIR}"

echo "==> Building wheel and sdist with ${PYTHON_BIN}"
cd "${ROOT_DIR}"
"${PYTHON_BIN}" -m build

WHEEL_PATH="$(find "${DIST_DIR}" -maxdepth 1 -name 'k8s_forge-*.whl' | sort | tail -n 1)"
if [[ -z "${WHEEL_PATH}" ]]; then
  echo "No wheel artifact found in ${DIST_DIR}" >&2
  exit 1
fi

echo "==> Creating temporary virtualenv: ${VENV_DIR}"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip

echo "==> Installing wheel: ${WHEEL_PATH}"
"${VENV_DIR}/bin/python" -m pip install "${WHEEL_PATH}"

echo "==> Checking installed console command"
"${VENV_DIR}/bin/k8s-forge" --help >/tmp/k8s-forge-wheel-help.txt

echo "==> Generating and validating app.yaml from installed wheel"
"${VENV_DIR}/bin/k8s-forge" init demo-app --output "${APP_FILE}" --force
"${VENV_DIR}/bin/k8s-forge" check "${APP_FILE}"

echo "==> Rendering manifests from installed wheel"
"${VENV_DIR}/bin/k8s-forge" render "${APP_FILE}" --output "${GENERATED_DIR}"

for manifest in   00-namespace.yaml   10-configmap.yaml   20-secret.yaml   30-deployment.yaml   40-service.yaml; do
  if [[ ! -f "${GENERATED_DIR}/${manifest}" ]]; then
    echo "Missing generated manifest: ${manifest}" >&2
    exit 1
  fi
done

echo "==> Release check passed"
echo "Wheel: ${WHEEL_PATH}"
echo "Generated manifests: ${GENERATED_DIR}"
