#!/usr/bin/env bash
set -euo pipefail

# ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
# cd "$ROOT_DIR"
# PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"

# source "$ROOT_DIR/scripts/supporting/logging.sh"
# set_log_level DEBUG
# source "$ROOT_DIR/.env"
# source "$ROOT_DIR/scripts/supporting/setup_env.sh"

my_name="generate_initial_alembic_migration.sh"

CONTAINER=$(docker ps --filter "name=-db" --format "{{.Names}}")

# Set the PYTHONPATH to include the fastapi directory
export PYTHONPATH="$ROOT_DIR/dq-api/fastapi"

# 2. Navigate to the Alembic directory
cd "$ROOT_DIR/dq-api/fastapi"

# 3. (Optional) Remove old migration files for a clean baseline
info "$my_name" "Cleaning old migration files in migrations/versions/..."
rm -f migrations/versions/*.py

# info "$my_name" "Connecting to database at $DQ_DB_LOCAL_URL to drop alembic_version table..."
# info "$my_name" "Running: docker exec $CONTAINER psql -U postgres -d ${DATABASE_SCHEMA} -c 'DROP TABLE IF EXISTS alembic_version CASCADE;'"
# docker exec "$CONTAINER" psql -U postgres -d "$DATABASE_SCHEMA" -c "DROP TABLE IF EXISTS alembic_version CASCADE;" || {
#     error "$my_name" "Failed to drop alembic_version table";
# }

# 4. Generate a new Alembic migration file for all models
export DQ_DB_LOCAL_URL="${DQ_DB_LOCAL_URL}"

info "$my_name" "Generating new Alembic migration file using $DQ_DB_LOCAL_URL..."
${PYTHON_RUNNER} -m alembic revision --autogenerate -m "Initial schema"

# 5. Show the generated migration file
info "$my_name" "Generated migration files:"
ls -lh migrations/versions/

# 6. (Optional) Apply the migration to the database
# info "$my_name" "Applying migration to the database..."
# ${PYTHON_RUNNER} -m alembic upgrade head

docker compose exec db psql -U postgres -d "${DATABASE_SCHEMA}" -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public';" || {
    error "$my_name" "Failed to verify database schema reset"; exit 34;
}

info "$my_name" "Done."
