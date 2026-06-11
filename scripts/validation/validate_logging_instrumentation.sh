#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate that critical FastAPI endpoints emit structured log events.
#
# What it does:
# - Checks a set of endpoint modules for log_event(...) usage.
# - Fails if any critical endpoint file is missing or has no log_event calls.
#
# validate: groups=repo,governance,api

# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_logging_instrumentation.sh"

critical_files=(
  "${ROOT_DIR}/dq-api/fastapi/app/api/v1/endpoints/auth.py"
  "${ROOT_DIR}/dq-api/fastapi/app/api/v1/endpoints/approvals.py"
  "${ROOT_DIR}/dq-api/fastapi/app/api/v1/endpoints/admin.py"
  "${ROOT_DIR}/dq-api/fastapi/app/api/v1/endpoints/testing.py"
  "${ROOT_DIR}/dq-api/fastapi/app/api/v1/endpoints/execution_monitoring.py"
  "${ROOT_DIR}/dq-api/fastapi/app/api/v1/endpoints/rules.py"
)

for file in "${critical_files[@]}"; do
  if [[ ! -f "${file}" ]]; then
    error "$my_name" "Missing critical endpoint file ${file}"
    exit 1
  fi
done

require_in_file() {
  local needle="$1"
  local file="$2"
  if ! grep -Fq "$needle" "$file"; then
    error "$my_name" "Missing '${needle}' in ${file}"
    exit 1
  fi
}

for file in "${critical_files[@]}"; do
  require_in_file "from app.core.log_event import log_event" "${file}"
  if [[ "$(grep -Fc "log_event(" "${file}")" -lt 1 ]]; then
    error "$my_name" "Expected at least one log_event(...) call in ${file}"
    exit 1
  fi
done

success "$my_name" "logging instrumentation checks passed for critical endpoints"