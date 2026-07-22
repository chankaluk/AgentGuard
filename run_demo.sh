#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -n "${PYTHON_EXECUTABLE:-}" ]]; then
  PYTHON_BIN="$PYTHON_EXECUTABLE"
elif [[ -x .venv/bin/python ]]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python 3 was not found. Install Python 3.11 or newer and retry." >&2
  exit 1
fi

if [[ ! -f artifacts/agentguard.pt ]]; then
  echo "Model not found; running the full pipeline first."
  PYTHON_EXECUTABLE="$PYTHON_BIN" "$ROOT/run_all.sh"
fi
"$PYTHON_BIN" scripts/serve.py "$@"
