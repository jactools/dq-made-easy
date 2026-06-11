#!/usr/bin/env bash
set -euo pipefail


# Purpose: Apply the generated external_id SQL patch to the database.
#
# What it does:
# - Loads repo env and database connection settings.
# - Verifies the patch file exists.
# - Applies the patch via psql against the configured DQ_DB_LOCAL_URL.
#
# Version: 1.0
# Last modified: 2026-04-07

PATCH_FILE="tmp/patches/ensure_external_ids.sql"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

# Source logging function
source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="apply_external_id_patch.sh"

. .env
. ./scripts/supporting/setup_env.sh

DQ_DB_LOCAL_URL="${DQ_DB_LOCAL_URL:?DQ_DB_LOCAL_URL is required}"

if [[ ! -f "$PATCH_FILE" ]]; then
  error "$my_name" "Patch file $PATCH_FILE not found. Run scripts/generate_external_id_patch.py first."
  exit 2
fi

info "$my_name" "Applying patch $PATCH_FILE using DQ_DB_LOCAL_URL..."
psql "$DQ_DB_LOCAL_URL" -f "$PATCH_FILE"
success "$my_name" "Done."
