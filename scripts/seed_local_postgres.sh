#!/usr/bin/env bash

# Purpose: Seed the Postgres database via the dedicated Docker seed container.
#
# What it does:
# - Starts the required db/keycloak services when needed.
# - Runs the one-shot `db-seed` compose service.
# - Avoids host Python/Alembic/mock-data tooling dependencies.
#
# Version: 1.0
# Last modified: 2026-04-22

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="seed_local_postgres.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
init_root_env_file "$ROOT_DIR"

if [ ! -f "$ROOT_ENV_FILE" ]; then
	error "$my_name" "Env file not found: $ROOT_ENV_FILE"
	exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

info "$my_name" "== Seed local Postgres via Docker seed container =="
info "$my_name" "Ensuring db and keycloak services are running..."
docker_compose up -d db keycloak >/dev/null

wait_for_compose_service_healthy db "Postgres database" 60 2

info "$my_name" "Running db-seed one-shot container..."
docker_compose --profile auth --profile seed run --rm db-seed

success "$my_name" "Postgres seeding completed via db-seed container"