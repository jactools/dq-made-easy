#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${DB_NAME:-dq}"
DB_USER="${DB_USER:-postgres}"
SEED_ROOT="${SEED_ROOT:-/opt/dq-db/init}"

echo "== Reseed in running container =="
echo "Database: ${DB_NAME}"

if [ ! -d "$SEED_ROOT" ]; then
  echo "ERROR: seed root not found: $SEED_ROOT"
  exit 1
fi

# Reset public schema for a clean reseed run.
# NOTE: Alembic is invoked by the db-seed orchestration immediately after this
# reset and before any seed SQL is applied. This helper only clears the schema.
psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"

echo "Schema reset complete. Waiting for Alembic to create tables..."
# The caller orchestrates: reset -> alembic upgrade head -> seed SQL.

echo "Reseed complete (schema reset only — caller will apply Alembic + seeds)"
