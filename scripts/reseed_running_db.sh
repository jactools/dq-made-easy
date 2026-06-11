#!/usr/bin/env bash

# Purpose: Reseed the database via the dedicated Docker seed container.
#
# What it does:
# - Ensures db and keycloak are running.
# - Runs the compose-native `db-seed` one-shot service.
#
# Version: 1.0
# Last modified: 2026-04-22

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="reseed_running_db.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
init_root_env_file "$ROOT_DIR"

if [ ! -f "$ROOT_ENV_FILE" ]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

info "$my_name" "Ensuring db and keycloak services are running before reseed..."
docker_compose up -d db keycloak >/dev/null

wait_for_compose_service_healthy db "Postgres database" 60 2

info "$my_name" "Running db-seed one-shot container..."
docker_compose --profile auth --profile seed run --rm db-seed || {
  error "$my_name" "db-seed container failed"
  exit 1
}

info "$my_name" "PASS: db reseed completed via db-seed container"
