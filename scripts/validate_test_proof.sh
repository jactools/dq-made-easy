#!/usr/bin/env bash
set -euo pipefail

# validate: groups=repo
# Purpose: Validate committed test proof JSON against the canonical schema.
# What it does:
# - Fails if any proof artifact under test-results/test-proof/ is not JSON
# - Validates each proof JSON file against docs/contracts/test-proof/v1/schema.json
# - Fails fast when a proof file is missing required fields or has invalid values
# Version: 1.0
# Last modified: 2026-05-27

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$script_dir/validation/validate_test_proof.sh" "$@"