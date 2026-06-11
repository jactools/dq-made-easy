#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate the ITSM support request response contract.
#
# What it does:
# - Runs the focused presenter regression test for numeric ITSM identifiers.
# - Runs the support request endpoint regression test that exercises the live response path.
# - Fails fast if the response contract regresses.
#
# validate: groups=api,regression
#
# Version: 1.0.0
# Last modified: 2026-05-10

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_support_request_itsm_response.sh"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/venv/bin/python}"
FASTAPI_DIR="$ROOT_DIR/dq-api/fastapi"

if [ ! -x "$PYTHON_BIN" ]; then
  error "$my_name" "Python executable not found: $PYTHON_BIN"
  exit 1
fi

info "$my_name" "Running focused ITSM support request regression tests..."

cd "$FASTAPI_DIR"
"$ROOT_DIR/scripts/python_arm64.sh" --python-bin "$PYTHON_BIN" -m pytest \
  tests/api/test_support_presenters.py::test_build_itsm_response_entity_normalizes_numeric_identifier_fields \
  tests/api/test_support_requests_endpoint.py::test_support_request_itsm_accepts_numeric_ticket_identifiers \
  -q --no-cov

success "$my_name" "ITSM support request response validation passed"