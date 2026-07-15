#!/usr/bin/env bash
set -euo pipefail

# Purpose: Run Bandit static analysis on the FastAPI core runtime surface.
#
# What it does:
# - Executes Bandit on the backend core/resolver/entity paths that are part of
#   the security-critical runtime surface.
# - Fails the validation run on CRITICAL/HIGH findings.
#
# validate: groups=security
#
# Version: 1.0
# Last modified: 2026-07-14

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_bandit_scan.sh"
PYTHON_CMD=("$ROOT_DIR/scripts/python_arm64.sh" --python-bin "$ROOT_DIR/venv/bin/python")

require_cmd bandit

main() {
  info "$my_name" "Running Bandit static analysis on FastAPI runtime surface..."

  local output_file="$ROOT_DIR/tmp/security/bandit-results.json"
  mkdir -p "$ROOT_DIR/tmp/security"

  local exit_code=0
  "${PYTHON_CMD[@]}" -m bandit \
    -r "$ROOT_DIR/dq-api/fastapi/app/core" \
    "$ROOT_DIR/dq-api/fastapi/app/application/resolvers" \
    "$ROOT_DIR/dq-api/fastapi/app/domain/entities" \
    -f json \
    -o "$output_file" \
    -q || exit_code=$?

  # Bandit exit codes: 0=OK, 1=error, 2=CRITICAL found, 3=HIGH found, 4=MEDIUM, 5=LOW, 6=other
  case "$exit_code" in
    0)
      success "$my_name" "Bandit scan passed (no findings)"
      ;;
    2|3)
      error "$my_name" "Bandit found CRITICAL/HIGH findings (exit code $exit_code)"
      info "$my_name" "Results written to $output_file"
      exit 1
      ;;
    *)
      success "$my_name" "Bandit scan completed (exit code $exit_code)"
      info "$my_name" "Results written to $output_file"
      ;;
  esac
}

main "$@"
