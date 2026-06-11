#!/usr/bin/env bash
set -euo pipefail


# Purpose: Update VERSION_MANIFEST.json using determine_versions.js.
#
# What it does:
# - Runs scripts/determine_versions.js --write.
# - Updates VERSION_MANIFEST.json in-place.
# - Prompts the operator to review/commit changes.
#
# Version: 1.0
# Last modified: 2026-04-07

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
echo "Running determine_versions.js --write to update VERSION_MANIFEST.json"
node scripts/determine_versions.js --write
echo "Updated VERSION_MANIFEST.json. Review changes and commit when ready."
