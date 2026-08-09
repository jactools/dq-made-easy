#!/usr/bin/env bash
set -euo pipefail

DQ_DB_INTERNAL_URL="${DQ_DB_INTERNAL_URL:?DQ_DB_INTERNAL_URL is required}"
SEED_ROOT="${SEED_ROOT:-/opt/dq-db/init}"

echo "== Reseed in running container =="
echo "Database: ${DQ_DB_INTERNAL_URL}"

if [ ! -d "$SEED_ROOT" ]; then
  echo "ERROR: seed root not found: $SEED_ROOT"
  exit 1
fi

# Alembic manages schema lifecycle — no manual drops.
# This script is a no-op; the caller (run_db_seed_container.sh) handles
# the full Alembic reset: stamp head -> downgrade base -> upgrade head.
echo "Alembic will manage schema reset (no manual drops)."
