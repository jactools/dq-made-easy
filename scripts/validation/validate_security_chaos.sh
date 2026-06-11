#!/usr/bin/env bash
set -euo pipefail

# Purpose: Run security chaos-engineering regression tests for fail-fast auth paths.
#
# What it does:
# - Executes the auth endpoint failure-injection tests that simulate OIDC discovery outages.
# - Verifies the API fails closed with explicit 503 responses instead of degrading silently.
# - Provides a repo validation gate for the LLM-1.30 security chaos engineering milestone.
#
# validate: groups=repo
#
# Version: 1.0
# Last modified: 2026-06-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_security_chaos.sh"
PYTHON_CMD=("$ROOT_DIR/scripts/python_arm64.sh" --python-bin "$ROOT_DIR/venv/bin/python")

main() {
  info "$my_name" "Running security chaos-engineering regression tests..."

  cd "$ROOT_DIR/dq-api/fastapi"
  PYTHONPATH="$ROOT_DIR/dq-utils/src:$ROOT_DIR/dq-domain-validation/src" \
    "${PYTHON_CMD[@]}" -m pytest tests/api/test_auth_endpoints.py -k 'fails_fast_when_oidc_discovery_raises' -q --no-cov

  success "$my_name" "Security chaos-engineering regression tests passed."
}

main "$@"
