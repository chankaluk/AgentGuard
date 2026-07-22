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
  echo "Python 3 was not found. Run ./setup_env.sh first." >&2
  exit 1
fi

"$PYTHON_BIN" scripts/generate_demo_data.py
"$PYTHON_BIN" scripts/evaluate_baselines.py
"$PYTHON_BIN" scripts/train.py
"$PYTHON_BIN" scripts/evaluate.py
if [[ "${VERIFY_REFERENCES:-0}" == "1" ]]; then
  "$PYTHON_BIN" scripts/verify_references.py
fi
"$PYTHON_BIN" -m unittest discover -s tests -v
"$PYTHON_BIN" scripts/generate_submission_docs.py
"$PYTHON_BIN" scripts/verify_project.py
"$PYTHON_BIN" scripts/package_project.py

echo "AgentGuard pipeline completed. Outputs: artifacts/ and submission/."
