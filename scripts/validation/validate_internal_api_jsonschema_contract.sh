#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate internal API JSON-body contract coverage.
#
# What it does:
# - Loads the live FastAPI OpenAPI document from the app.
# - Verifies every internal API operation with a JSON request body has a published JSON Schema contract.
# - Verifies request-schema property names and required keys are snake_case.
#
# validate: groups=repo,api
# Version: 1.0
# Last modified: 2026-04-20

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

export APP_CONFIG_ENCRYPTION_KEY="${APP_CONFIG_ENCRYPTION_KEY:-i0aU2BE0dzqEVAWxfEsvffw5zw93FjFZrr24RPVyo8c=}"

"${ROOT_DIR}/scripts/python_arm64.sh" --python-bin "$PYTHON_BIN" "${SCRIPT_DIR}/validate_internal_api_jsonschema_contract.py"