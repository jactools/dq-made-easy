#!/usr/bin/env bash
set -euo pipefail

# Purpose: Enforce snake_case in API payloads and schemas.
# What it does:
# - Delegates to scripts/validate_snake_case.py
# - Keeps the repo validation group aligned with the top-level wrapper
# - Runs from the repo root for consistent local and pre-commit behavior
# validate: groups=repo
# validate: include=true
# Version: 1.0
# Last modified: 2026-08-04

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec "$ROOT_DIR/venv/bin/python" "$ROOT_DIR/scripts/validate_snake_case.py"
