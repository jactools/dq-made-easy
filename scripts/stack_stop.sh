#!/usr/bin/env bash
# Purpose: Stop the compose stack (containers only). Keeps volumes, secrets, and all artifacts.
#
# What it does:
#   1. Stops all compose containers
#   2. Runs docker compose down --remove-orphans (no -v, keeps volumes)
#
# Usage:
#   ./scripts/stack_stop.sh --env dev
#   ./scripts/stack_stop.sh --env test
#   ./scripts/stack_stop.sh --env prod
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

Stops the compose stack. Keeps volumes, secrets, and all generated artifacts.

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
    *) error "stack_stop.sh" "Unknown argument: $arg"; exit 1 ;;
  esac
done

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "stack_stop.sh" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

export ROOT_ENV_FILE

info "stack_stop.sh" "Stopping stack (env: $ROOT_ENV_FILE)..."

# 1. Stop all running containers
info "stack_stop.sh" "Stopping all containers..."
if docker_compose stop 2>/dev/null; then
  info "stack_stop.sh" "Containers stopped"
else
  info "stack_stop.sh" "No running containers to stop (or already stopped)"
fi

# 2. Remove containers and networks, but keep volumes
info "stack_stop.sh" "Removing containers and networks (keeping volumes)..."
docker_compose down --remove-orphans 2>/dev/null || {
  info "stack_stop.sh" "compose down completed (some resources may not have existed)"
}

success "stack_stop.sh" "Stack stopped (volumes and artifacts preserved)"
