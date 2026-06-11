#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FASTAPI_DIR="$(cd "$SCRIPT_DIR/../../fastapi" && pwd)"
PYTHON_RUNNER="$(cd "$SCRIPT_DIR/../../../scripts" && pwd)/python_arm64.sh"

source "$SCRIPT_DIR/ensure_arm64_python_env.sh"

cd "$FASTAPI_DIR"

PYTHON_BIN="${PYTHON_BIN:-../../venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

ensure_arm64_python_env "$PYTHON_BIN"

exec "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m pytest "$@"
