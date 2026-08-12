#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate Python module size and SRP boundaries.
# What it does:
# - Delegates to scripts/validate_module_rules.py
# - Allows pre-commit to pass staged Python files as positional arguments
# - Keeps the repo validation group aligned with the top-level wrapper
# validate: groups=repo
# validate: include=true
# Version: 1.0
# Last modified: 2026-08-04

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec "$ROOT_DIR/venv/bin/python" "$ROOT_DIR/scripts/validate_module_rules.py" "$@"
