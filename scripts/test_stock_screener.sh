#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
FRONTEND_DIR="${ROOT_DIR}/apps/dsa-web"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[ERROR] Python virtualenv not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] npm is required but not found in PATH" >&2
  exit 1
fi

run_step() {
  local title="$1"
  shift
  echo
  echo "==> ${title}"
  "$@"
}

run_frontend_step() {
  local title="$1"
  shift
  echo
  echo "==> ${title}"
  (
    cd "${FRONTEND_DIR}"
    if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
      # shellcheck disable=SC1090
      source "${HOME}/.nvm/nvm.sh"
      nvm use 20.17.0 >/dev/null || true
    fi
    "$@"
  )
}

cd "${ROOT_DIR}"

run_step \
  "backend: py_compile screener files" \
  "${PYTHON_BIN}" -m py_compile \
  api/v1/endpoints/stock_screener.py \
  api/v1/router.py \
  api/v1/schemas/stocks.py \
  api/v1/schemas/__init__.py \
  src/services/stock_formula_engine.py \
  src/services/stock_screener_service.py \
  src/services/stock_screener_task_queue.py \
  tests/test_stock_screener_api.py \
  tests/test_stock_screener_service.py \
  tests/test_stock_formula_engine.py

run_step \
  "backend: screener unittest" \
  "${PYTHON_BIN}" -m unittest \
  tests.test_stock_screener_api \
  tests.test_stock_screener_service \
  tests.test_stock_formula_engine

run_frontend_step "frontend: vitest" npm test
run_frontend_step "frontend: eslint" npm run lint
run_frontend_step "frontend: build" npm run build

echo
echo "[OK] stock screener checks passed"
