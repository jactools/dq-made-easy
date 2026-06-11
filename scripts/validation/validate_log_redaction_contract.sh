#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate the log redaction contract.
#
# What it does:
# - Runs a Python contract test that emits sensitive fields.
# - Asserts they are redacted/obscured in JSON logs.
#
# validate: groups=repo,governance,api

# Version: 1.0
# Last modified: 2026-04-07

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

"${ROOT_DIR}/scripts/python_arm64.sh" "${SCRIPT_DIR}/validate_log_redaction_contract.py"
