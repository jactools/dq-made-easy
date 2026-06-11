#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate profiling worker lifecycle success+failure paths.
#
# What it does:
# - Runs validate_profiling_worker_success.sh
# - Runs validate_profiling_worker_failure.sh
#
# validate: groups=profiling

# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${ROOT_DIR}/../supporting/logging.sh"

my_name="validate_profiling_worker_lifecycle.sh"
SUCCESS_SCRIPT="${ROOT_DIR}/validate_profiling_worker_success.sh"
FAILURE_SCRIPT="${ROOT_DIR}/validate_profiling_worker_failure.sh"

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    error "$my_name" "Missing required script: ${path}"
    exit 1
  fi
}

print_usage() {
  cat <<'EOF'
Usage: validate_profiling_worker_lifecycle.sh

Runs both live profiling lifecycle validators in sequence:
  1. Success path -> request reaches completed
  2. Failure path -> request reaches failed with error_message

Environment overrides accepted by the child scripts are forwarded as-is.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  print_usage
  exit 0
fi

require_file "$SUCCESS_SCRIPT"
require_file "$FAILURE_SCRIPT"

info "$my_name" "=== Profiling Worker Lifecycle Validation ==="
info "$my_name" "[1/2] Validating success path..."
bash "$SUCCESS_SCRIPT"

info "$my_name" "[2/2] Validating failure path..."
bash "$FAILURE_SCRIPT"

success "$my_name" "Profiling worker success and failure lifecycle validations both passed."