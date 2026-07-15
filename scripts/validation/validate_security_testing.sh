#!/usr/bin/env bash
set -euo pipefail

# DEPRECATED: This script has been split into focused security scans.
# Use validate_bandit_scan.sh and validate_pip_audit_fastapi.sh instead.
#
# This file remains as a compatibility shim that delegates to the new scripts.
# Remove once all callers have migrated.
#
# validate: groups=repo
# validate: include=false
#
# Version: 2.0
# Last modified: 2026-07-14

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_security_testing.sh"

main() {
  warning "$my_name" "DEPRECATED — this script is now split into:"
  warning "$my_name" "  - scripts/validation/validate_bandit_scan.sh"
  warning "$my_name" "  - scripts/validation/validate_pip_audit_fastapi.sh"
  warning "$my_name" "Run: ./scripts/validate.sh security"

  # Delegate to the new scripts
  "$ROOT_DIR/scripts/validation/validate_bandit_scan.sh"
  "$ROOT_DIR/scripts/validation/validate_pip_audit_fastapi.sh"

  success "$my_name" "Automated security scans passed (via delegates)."
}

main "$@"
