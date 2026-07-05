#!/usr/bin/env bash
set -euo pipefail

# Purpose: Enforce the 1000-line rule for Python files.
# What it does:
#   - Delegates to validate_python_file_sizes.py
#   - Enforces new/created files must be under 1000 lines
#   - Reports existing files that already exceed the threshold
#   - Shows extreme values (largest files)
# Usage:
#   ./scripts/validation/validate_python_file_sizes.sh [OPTIONS]
# Options:
#   --threshold N     Max lines (default: 1000)
#   --new-only        Only check new files
#   --extreme N       Top N largest files (default: 10)
#   --json            JSON output
#   --quiet           Suppress verbose output
#   --allow-list F    Path to allow-list file
#   -h, --help        Show help
# validate: groups=repo
# validate: include=true
# Version: 1.0
# Last modified: 2026-07-05

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$ROOT_DIR/scripts/validation/validate_python_file_sizes.py" \
    --allow-list "$ROOT_DIR/scripts/validation/python-file-allow-list.txt" \
    "$@"
