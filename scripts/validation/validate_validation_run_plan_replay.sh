#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate Postgres-backed replay of a grouped validation run plan.
# What it does:
# - Runs the live integration test that seeds a temporary plan in Postgres.
# - Replays the active plan through the real API helper path.
# - Verifies the dispatch is persisted back to Postgres.
# validate: groups=api,regression
# Version: 1.0.0
# Last modified: 2026-06-28

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FASTAPI_DIR="${ROOT_DIR}/dq-api/fastapi"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
PYTHON_RUNNER="${ROOT_DIR}/scripts/python_arm64.sh"
MY_NAME="validate_validation_run_plan_replay.sh"

# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/supporting/logging.sh"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  error "${MY_NAME}" "Missing required Python interpreter: ${PYTHON_BIN}"
  exit 2
fi

if [[ ! -x "${PYTHON_RUNNER}" ]]; then
  error "${MY_NAME}" "Missing required Python launcher: ${PYTHON_RUNNER}"
  exit 2
fi

info "${MY_NAME}" "Running Postgres-backed validation run plan replay integration test"
cd "${FASTAPI_DIR}"
PYTHONPATH="${ROOT_DIR}/dq-utils/src:${ROOT_DIR}/dq-domain-validation/src" \
  "${PYTHON_RUNNER}" --python-bin "${PYTHON_BIN}" -m pytest tests/infrastructure/integration/test_validation_run_plan_replay.py -q

success "${MY_NAME}" "Validation run plan replay integration test passed"