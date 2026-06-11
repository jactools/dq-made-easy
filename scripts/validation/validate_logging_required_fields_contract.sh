#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate the structured logging required-fields contract.
#
# What it does:
# - Runs a small Python contract test using the FastAPI JSON formatter.
# - Ensures required keys (event/component/correlationId/ts/level + ids) exist.
#
# validate: groups=repo,governance,api

# Version: 1.0
# Last modified: 2026-04-07

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

"${ROOT_DIR}/scripts/python_arm64.sh" "${SCRIPT_DIR}/validate_logging_required_fields_contract.py"
