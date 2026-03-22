#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/logs}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
CONSOLE_LOG="$LOG_DIR/console_${TIMESTAMP}.log"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python3}"

mkdir -p "$LOG_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  echo "Please ensure the project virtualenv is ready." >&2
  exit 1
fi

echo "Starting Web UI with live console logs..."
echo "Repo: $REPO_ROOT"
echo "URL:  http://${HOST}:${PORT}"
echo "Log:  $CONSOLE_LOG"
echo "Python: $PYTHON_BIN"

PYTHONUNBUFFERED=1 \
WEBUI_AUTO_BUILD="${WEBUI_AUTO_BUILD:-false}" \
"$PYTHON_BIN" main.py --webui-only --host "$HOST" --port "$PORT" "$@" 2>&1 | tee -a "$CONSOLE_LOG"
