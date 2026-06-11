#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FASTAPI_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
DQ_API_DIR="$(cd "$FASTAPI_DIR/.." && pwd)"
PYTHON_RUNNER="$DQ_API_DIR/../scripts/python_arm64.sh"
PYTHON_BIN="${PYTHON_BIN:-$FASTAPI_DIR/../../venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

source "$DQ_API_DIR/scripts/testing/ensure_arm64_python_env.sh"
ensure_arm64_python_env "$PYTHON_BIN"

run_py() {
  "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" "$@"
}

if [[ "${1:-}" != "--run" ]]; then
  cat <<'USAGE'
Usage:
  ./scripts/testing/run_openmetadata_contract_cache_integration.sh --run [pytest args]

Description:
  Runs the opt-in OpenMetadata contract cache integration test using the
  pytest flag --run-openmetadata-contract-cache-integration.
USAGE
  exit 2
fi

shift
cd "$FASTAPI_DIR"

run_py -m pytest -q -o addopts='' \
  tests/infrastructure/integration/test_openmetadata_contract_cache_integration.py \
  --run-openmetadata-contract-cache-integration \
  "$@"
