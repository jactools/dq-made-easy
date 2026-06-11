#!/usr/bin/env bash
set -euo pipefail

# Entrypoint for API image:
# - start uvicorn after the compose-level api-migrate one-shot service has
#   applied Alembic migrations.

ROOT_DIR="/app"

cd "$ROOT_DIR"

echo "Starting uvicorn"
uvicorn app.main:app --host 0.0.0.0 --port 4010
