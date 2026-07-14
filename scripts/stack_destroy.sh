#!/usr/bin/env bash
# Purpose: Destroy the full compose stack — containers, volumes, and all generated artifacts.
#
# What it does:
#   1. Stops all containers via docker compose stop
#   2. Runs docker compose down -v --remove-orphans (removes containers + volumes)
#   3. Removes generated secrets, rotated passwords, keycloak credentials, TLS certs
#
# Usage:
#   ./scripts/stack_destroy.sh --env dev
#   ./scripts/stack_destroy.sh --env test
#   ./scripts/stack_destroy.sh --env prod
#
# Version: 1.0
# Last modified: 2026-07-14

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/env/selection.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
source "$ROOT_DIR/scripts/supporting/stack_lifecycle.sh"

init_root_env_file "$ROOT_DIR"

print_usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Destroys the compose stack: containers, volumes, and generated artifacts.

Options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file
  -h, --help               Show this help
EOF
}

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}
for arg in "$@"; do
  case "$arg" in
    -h|--help) print_usage; exit 0 ;;
    *) error "stack_destroy.sh" "Unknown argument: $arg"; exit 1 ;;
  esac
done

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "stack_destroy.sh" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

export ROOT_ENV_FILE

info "stack_destroy.sh" "Destroying stack (env: $ROOT_ENV_FILE)..."

# 1. Stop containers first (graceful)
info "stack_destroy.sh" "Stopping all containers..."
if docker_compose stop >/dev/null 2>&1; then
  info "stack_destroy.sh" "Containers stopped"
else
  info "stack_destroy.sh" "No running containers to stop (or already stopped)"
fi

# 2. Remove containers, networks, volumes
info "stack_destroy.sh" "Removing containers, networks, and volumes..."
docker_compose down -v --remove-orphans 2>/dev/null || {
  info "stack_destroy.sh" "compose down completed (some resources may not have existed)"
}

# 3. Remove generated artifacts
info "stack_destroy.sh" "Removing generated artifacts..."
remove_generated_artifacts "$ROOT_ENV_FILE" "$ROOT_DIR"

success "stack_destroy.sh" "Stack destroyed"
