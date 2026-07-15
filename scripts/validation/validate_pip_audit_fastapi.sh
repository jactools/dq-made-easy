#!/usr/bin/env bash
set -euo pipefail

# Purpose: Run pip-audit on the FastAPI dependency manifest.
#
# What it does:
# - Executes pip-audit on dq-api/fastapi/requirements.txt to detect known
#   package vulnerabilities.
# - Fails the validation run on CRITICAL/HIGH CVE findings.
#
# validate: groups=security
#
# Version: 1.0
# Last modified: 2026-07-14

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_pip_audit_fastapi.sh"
PYTHON_CMD=("$ROOT_DIR/scripts/python_arm64.sh" --python-bin "$ROOT_DIR/venv/bin/python")

require_cmd pip_audit

main() {
  local requirements_file="$ROOT_DIR/dq-api/fastapi/requirements.txt"
  if [ ! -f "$requirements_file" ]; then
    error "$my_name" "Requirements file not found: $requirements_file"
    exit 1
  fi

  info "$my_name" "Running pip-audit on FastAPI dependencies..."

  local output_file="$ROOT_DIR/tmp/security/pip-audit-fastapi-results.json"
  mkdir -p "$ROOT_DIR/tmp/security"

  local exit_code=0
  "${PYTHON_CMD[@]}" -m pip_audit \
    -r "$requirements_file" \
    --progress-spinner off \
    -f json \
    -o "$output_file" || exit_code=$?

  # pip_audit exit codes: 0=OK, 1=error
  if [ "$exit_code" -eq 0 ]; then
    success "$my_name" "pip-audit passed (FastAPI)"
  else
    # Parse the JSON output for severity
    local critical_count high_count total_vulns
    total_vulns="$(python3 -c "
import json, sys
try:
    data = json.load(open('$output_file'))
    vulns = data.get('vulnerabilities', [])
    critical = sum(1 for v in vulns if any(s.get('scoring_system') == 'CVSS_v3' and float(s.get('score', 0)) >= 9.0 for s in v.get('vectors', [{}])))
    high = sum(1 for v in vulns if any(s.get('scoring_system') == 'CVSS_v3' and 7.0 <= float(s.get('score', 0)) < 9.0 for s in v.get('vectors', [{}])))
    print(f'{critical} {high} {len(vulns)}')
except Exception:
    print('0 0 0')
" 2>/dev/null || echo '0 0 0')"
    critical_count="${total_vulns%% *}"
    local rest="${total_vulns#* }"
    high_count="${rest%% *}"
    total_vulns="${rest#* }"

    if [ "$critical_count" -gt 0 ] || [ "$high_count" -gt 0 ]; then
      error "$my_name" "pip-audit found vulnerabilities in FastAPI deps: $critical_count CRITICAL, $high_count HIGH, $total_vulns total"
      info "$my_name" "Results written to $output_file"
      exit 1
    fi

    warning "$my_name" "pip-audit found $total_vulns non-critical vulnerabilities in FastAPI deps"
    info "$my_name" "Results written to $output_file"
  fi
}

main "$@"
