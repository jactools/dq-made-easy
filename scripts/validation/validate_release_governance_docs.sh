#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate release governance docs baseline.
#
# What it does:
# - Ensures required release documentation files/sections exist.
#
# validate: groups=repo,governance

# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_release_governance_docs.sh"
IMPL_CHECKLIST="${ROOT_DIR}/docs/technical/LOGGING_AND_MONITORING_POLICY_IMPLEMENTATION_CHECKLIST.md"
RELEASE_CHECKLIST="${ROOT_DIR}/docs/releases/RELEASE_READINESS_CHECKLIST.md"

if [[ ! -f "${IMPL_CHECKLIST}" ]]; then
  error "$my_name" "Missing ${IMPL_CHECKLIST}"
  exit 1
fi

if [[ ! -f "${RELEASE_CHECKLIST}" ]]; then
  error "$my_name" "Missing ${RELEASE_CHECKLIST}"
  exit 1
fi

require_in_file() {
  local needle="$1"
  local file="$2"
  if ! grep -Fq -- "$needle" "$file"; then
    error "$my_name" "Missing '${needle}' in ${file}"
    exit 1
  fi
}

require_in_file '- [x] Add release checklist item: policy compliance reviewed.' "${IMPL_CHECKLIST}"
require_in_file '- [ ] Logging and Monitoring Policy compliance reviewed (DQ-SEC-LOGMON-001).' "${RELEASE_CHECKLIST}"

success "$my_name" "release governance documentation checks passed"