#!/usr/bin/env bash
set -euo pipefail

# Run the external_id patch generator inside a docker container (real run).
# Requires: KEYCLOAK_CLIENT_SECRET env var.
# Example:
# KEYCLOAK_CLIENT_SECRET='hW9je...' bash scripts/patches/run_generate_external_id_patch.sh

KEYCLOAK_NETWORK="${KEYCLOAK_NETWORK:-dq-rulebuilder_default}"
KEYCLOAK_HOST="${KEYCLOAK_HOST:-keycloak:8080}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-jaccloud}"
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-dq-rules-ui}"
KEYCLOAK_CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-}"

if [ -z "$KEYCLOAK_CLIENT_SECRET" ]; then
  echo "ERROR: please set KEYCLOAK_CLIENT_SECRET before running this script" >&2
  exit 2
fi

PWD_DIR="$(pwd)"

echo "Running generator (will write SQL) against $KEYCLOAK_HOST in network $KEYCLOAK_NETWORK"

docker run --rm --network "$KEYCLOAK_NETWORK" \
  -e KEYCLOAK_INTERNAL_URL="http://$KEYCLOAK_HOST" \
  -e KEYCLOAK_REALM="$KEYCLOAK_REALM" \
  -e KEYCLOAK_TOKEN_REALM="${KEYCLOAK_TOKEN_REALM:-$KEYCLOAK_REALM}" \
  -e KEYCLOAK_CLIENT_ID="$KEYCLOAK_CLIENT_ID" \
  -e KEYCLOAK_CLIENT_SECRET="$KEYCLOAK_CLIENT_SECRET" \
  -v "$PWD_DIR":/work -w /work python:3.11 \
  python3 scripts/generate_external_id_patch.py

# If the generator wrote the patch, attempt to create an Alembic revision and apply it.
PATCH_FILE="${PWD_DIR}/tmp/patches/ensure_external_ids.sql"
if [ -f "$PATCH_FILE" ]; then
  echo "Generator produced patch: $PATCH_FILE"

  REPO_ROOT="$PWD_DIR"
  FASTAPI_MIGRATIONS_DIR="$REPO_ROOT/dq-api/fastapi/migrations/versions"
  PYTHON_RUNNER="$REPO_ROOT/scripts/python_arm64.sh"
  PY_CMD="$REPO_ROOT/venv/bin/python"

  REV_TS=$(date -u +"%Y%m%d_%H%M%S")
  REV_ID="${REV_TS}_update_external_ids_from_csv"
  REV_FILE="$FASTAPI_MIGRATIONS_DIR/${REV_ID}.py"

  DOWN_REV=""
  if [ -x "$PY_CMD" ]; then
    CUR_OUT=$($PY_CMD -m alembic -c "$REPO_ROOT/dq-api/fastapi/alembic.ini" current 2>/dev/null || true)
    DOWN_REV=$(echo "$CUR_OUT" | awk '{print $NF}' | tr -d '(),') || true
    if [ -z "$DOWN_REV" ] || echo "$DOWN_REV" | grep -qi "head\|none" >/dev/null 2>&1; then
      DOWN_REV="None"
    fi
  else
    echo "Python venv not found at $PY_CMD; skipping automatic Alembic revision/apply."
  fi

  mkdir -p "$FASTAPI_MIGRATIONS_DIR"

  if [ -n "$PY_CMD" ] && [ -x "$PY_CMD" ]; then
    # Prepare Python-compatible down_revision literal: either None or quoted string
    if [ -z "$DOWN_REV" ] || [ "$DOWN_REV" = "None" ]; then
      PY_DOWN_REV="None"
    else
      PY_DOWN_REV="'${DOWN_REV}'"
    fi

    # Read and escape the SQL for safe embedding inside a Python triple-quoted string
    ESCAPED_SQL=$(sed -e 's/\\\\/\\\\\\\\/g' -e 's/"""/\"\"\"/g' "$PATCH_FILE" | sed -e ':a' -e 'N' -e 's/\n/\n/g' -e 'ta')

    cat > "$REV_FILE" <<EOF
"""Auto-generated migration to apply ensure_external_ids.sql

Revision ID: $REV_ID
Revises: $DOWN_REV
Create Date: $(date -u +"%Y-%m-%d %H:%M:%SZ")
"""

from alembic import op
import sqlalchemy as sa

revision = "$REV_ID"
down_revision = $PY_DOWN_REV
branch_labels = None
depends_on = None

def upgrade():
    sql = """$ESCAPED_SQL"""
    op.execute(sql)

def downgrade():
    # This data migration is not trivially reversible.
    pass
EOF


    echo "Created Alembic revision: $REV_FILE"

    # If an API container is available, copy the revision into its migrations directory
    if command -v docker >/dev/null 2>&1; then
      API_CID=$(docker compose ps -q api 2>/dev/null || true)
      if [ -n "$API_CID" ]; then
        TARGET_NAME=$(basename "$REV_FILE")
        CONTAINER_PATH="/app/migrations/versions/$TARGET_NAME"
        echo "Copying revision into api container at $CONTAINER_PATH"
        if docker cp "$REV_FILE" "$API_CID":"$CONTAINER_PATH"; then
          echo "Copied revision into api container"
        else
          echo "docker cp failed; attempting to create file inside container via cat" >&2
          if docker compose exec -T api bash -lc "cat > '$CONTAINER_PATH'" < "$REV_FILE"; then
            echo "Wrote revision into api container via exec cat"
          else
            echo "Failed to place revision into api container; alembic inside container may not see it" >&2
          fi
        fi
      else
        echo "API container not running; cannot copy revision into container" >&2
      fi
    fi

    APPLIED=false
    if command -v docker >/dev/null 2>&1; then
      API_CID=$(docker compose ps -q api 2>/dev/null || true)
      if [ -n "$API_CID" ]; then
        echo "Applying Alembic migrations inside api container via docker compose exec"
        if docker compose exec -T api bash -lc "export DQ_DB_INTERNAL_URL='postgresql://postgres:postgres@db:5432/dq' && alembic -c /app/alembic.ini upgrade head"; then
          APPLIED=true
        else
          echo "Container-based alembic upgrade failed; will try venv fallback" >&2
        fi
      else
        echo "API container not running; will try venv fallback"
      fi
    else
      echo "Docker not available; skipping container-based alembic and trying venv" >&2
    fi

    if [ "$APPLIED" = false ] && [ -x "$PY_CMD" ]; then
      echo "Applying Alembic migrations (upgrade head) using $PY_CMD (venv)"
      (
        cd "$REPO_ROOT/dq-api/fastapi"
        DQ_DB_LOCAL_URL="postgresql://postgres:postgres@dq-db.local:5432/dq" "$PY_CMD" -m alembic -c "$REPO_ROOT/dq-api/fastapi/alembic.ini" upgrade head
      ) && APPLIED=true || echo "Venv-based alembic upgrade failed; will attempt direct SQL apply" >&2
    fi

    if [ "$APPLIED" = false ]; then
      if command -v docker >/dev/null 2>&1; then
        DB_CID=$(docker compose ps -q db 2>/dev/null || true)
        if [ -n "$DB_CID" ]; then
          echo "Applying patch directly to Postgres container $DB_CID via psql"
          docker cp "$PATCH_FILE" "$DB_CID":/tmp/ensure_external_ids.sql || echo "docker cp failed"
          docker compose exec -T db psql -U postgres -d dq -f /tmp/ensure_external_ids.sql || echo "psql apply failed"
          APPLIED=true
        else
          echo "DB container not found; cannot apply SQL directly" >&2
        fi
      else
        echo "Docker not available; cannot attempt DB apply fallback" >&2
      fi
    fi

    if [ "$APPLIED" = true ]; then
      echo "Migration applied (or SQL executed) via one of the fallbacks. Migration file: $REV_FILE"
    else
      echo "All migration apply attempts failed; migration file created at $REV_FILE" >&2
    fi
  else
    echo "No python environment available; migration file not created."
  fi
else
  echo "No patch file found at $PATCH_FILE; nothing to apply."
fi
