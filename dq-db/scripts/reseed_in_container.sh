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

# Seed data uses COPY statements (no CREATE TABLE).
# Tables must already exist from Alembic (dq-job-api-migrate).
# This script is a no-op; the caller (run_db_seed_container.sh) handles
# generating seed SQL from CSVs and applying it via psql.
echo "Seeding data into existing tables (Alembic must have run first via dq-job-api-migrate)."
