#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -n "${PYTHON_EXECUTABLE:-}" ]]; then
  BASE_PYTHON="$PYTHON_EXECUTABLE"
elif command -v python3 >/dev/null 2>&1; then
  BASE_PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  BASE_PYTHON="python"
else
  echo "Python 3 was not found. Install Python 3.11 or newer and retry." >&2
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating the project-local .venv ..."
  "$BASE_PYTHON" -m venv .venv
fi

echo "Installing AgentGuard dependencies ..."
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt

echo "Verifying core dependencies ..."
.venv/bin/python -c "import torch,numpy,docx,pptx,matplotlib,psutil,requests; print('AgentGuard dependency check: OK')"
echo "Project environment is ready: $ROOT/.venv/bin/python"
