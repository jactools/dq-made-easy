#!/usr/bin/env bash
set -euo pipefail

# Purpose: Run automated security scans in the repo validation pipeline.
#
# What it does:
# - Executes Bandit on the backend core/resolver/entity paths that are part of the security-critical runtime surface.
# - Executes pip-audit on the FastAPI dependency manifest to detect known package vulnerabilities.
# - Fails the validation run on scan findings so CI/CD catches regressions early.
#
# validate: groups=repo
#
# Version: 1.0
# Last modified: 2026-06-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_security_testing.sh"
PYTHON_CMD=("$ROOT_DIR/scripts/python_arm64.sh" --python-bin "$ROOT_DIR/venv/bin/python")

main() {
  info "$my_name" "Running automated security scans for the backend runtime surface..."

  "${PYTHON_CMD[@]}" -m bandit \
    -r "$ROOT_DIR/dq-api/fastapi/app/core" \
    "$ROOT_DIR/dq-api/fastapi/app/application/resolvers" \
    "$ROOT_DIR/dq-api/fastapi/app/domain/entities" \
    -q

  "${PYTHON_CMD[@]}" -m pip_audit \
    -r "$ROOT_DIR/dq-api/fastapi/requirements.txt" \
    --progress-spinner off

  success "$my_name" "Automated security scans passed."
}

main "$@"
