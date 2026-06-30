#!/usr/bin/env bash
set -euo pipefail


# Purpose: Stop the docker compose stack (optionally including volumes).
#
# What it does:
# - Brings down the full-stack compose profile.
# - Optionally removes volumes when requested.
#
# Version: 1.4
# Last modified: 2026-07-01
# Changelog:
# - 1.1 (2026-04-27): Added env-file selection so teardown follows the same deployment env as startup.
# - 1.2 (2026-04-29): Switched teardown env selection to the canonical dev/test/prod contract.
# - 1.3 (2026-05-09): Delegated service teardown to stack_ctl.sh stop --all before removing compose resources.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

source "$ROOT/scripts/supporting/logging.sh"
source "$ROOT/scripts/supporting/root_env_file.sh"
source "$ROOT/scripts/supporting/compose/invocation.sh"
init_root_env_file "$ROOT"

my_name="stop_stack.sh"

print_usage() {
  printf '%s\n' \
    "Usage: $(basename "$0") [OPTIONS]" \
    "" \
    "Canonical env options:" \
    "  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local" \
    "  --env-file PATH          Use an explicit env file for CI, /etc, or diagnostics" \
    "" \
    "Other options:" \
    "  --remove-volumes, -v     Remove compose volumes as part of teardown" \
    "  -h, --help"
}

info "$my_name" "Stopping docker-compose stack..."

# Allow passing --remove-volumes or -v as a script argument; fall back to env var
REMOVE_VOLUMES_FLAG="${REMOVE_VOLUMES:-false}"
if ! consume_root_env_selection_args "$ROOT" "$@"; then
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    -v|--remove-volumes)
      REMOVE_VOLUMES_FLAG="true"
      shift
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      error "$my_name" "Unknown argument: $1"
      print_usage
      exit 1
      ;;
  esac
done

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "$my_name" "env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT" stop

export ROOT_ENV_FILE

info "$my_name" "Environment selection: $(describe_root_env_file_selection "$ROOT" "$ROOT_ENV_FILE") -> $ROOT_ENV_FILE"

set -a
source "$ROOT_ENV_FILE"
set +a

info "$my_name" "Stopping selected services through stack_ctl.sh stop --all..."
./scripts/stack_ctl.sh stop --all --env-file "$ROOT_ENV_FILE" || {
  error "$my_name" "Selective teardown failed"
  exit 1
}

if [ "${REMOVE_VOLUMES_FLAG}" = "true" ]; then
  info "$my_name" "Removing containers and volumes (remove requested)"
  docker_compose down --remove-orphans -v
else
  info "$my_name" "Removing containers only (to also remove volumes pass --remove-volumes)"
  docker_compose down --remove-orphans
fi

success "$my_name" "Done."
