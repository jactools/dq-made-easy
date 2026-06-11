#!/usr/bin/env bash
set -euo pipefail

# Purpose: Run explicit smoke validation checks for a prepared stack.
# What it does:
# - Runs selected stack smoke checks after lifecycle actions complete.
# - Keeps smoke validation separate from stack startup and seeding flows.
# - Fails fast when a requested smoke target is unavailable.
# Version: 1.0
# Last modified: 2026-05-09

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
my_name="smoke_stack.sh"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/env/selection.sh"
init_root_env_file "$ROOT_DIR"

RUN_AUTH_KONG=false
RUN_PROFILING=false
RUN_FASTAPI_SEEDED=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --all              Run every smoke check
  --auth-kong        Run the Kong auth smoke checks
  --profiling        Run the profiling worker lifecycle smoke checks
  --fastapi-seeded   Run the FastAPI seeded-list smoke checks
  --env dev|test|prod
  --env-file PATH
  -h, --help
EOF
}

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  usage
  exit 1
fi

set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"

if [ "$#" -eq 0 ]; then
  RUN_AUTH_KONG=true
  RUN_PROFILING=true
  RUN_FASTAPI_SEEDED=true
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      RUN_AUTH_KONG=true
      RUN_PROFILING=true
      RUN_FASTAPI_SEEDED=true
      shift
      ;;
    --auth-kong)
      RUN_AUTH_KONG=true
      shift
      ;;
    --profiling)
      RUN_PROFILING=true
      shift
      ;;
    --fastapi-seeded)
      RUN_FASTAPI_SEEDED=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "$my_name" "Unknown arg: $1"
      usage
      exit 1
      ;;
  esac
done

if [ ! -f "$ROOT_ENV_FILE" ]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

set -a
# shellcheck disable=SC1090
source "$ROOT_ENV_FILE"
set +a

info "$my_name" "Environment selection: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE") -> $ROOT_ENV_FILE"

if [ "$RUN_AUTH_KONG" = true ]; then
  info "$my_name" "Running Kong auth smoke checks"
  "$ROOT_DIR/scripts/smoke_test_auth_kong.sh"
fi

if [ "$RUN_PROFILING" = true ]; then
  info "$my_name" "Running profiling worker lifecycle smoke checks"
  "$ROOT_DIR/scripts/validate_profiling_worker_lifecycle.sh"
fi

if [ "$RUN_FASTAPI_SEEDED" = true ]; then
  info "$my_name" "Running FastAPI seeded-list smoke checks"
  "$ROOT_DIR/scripts/smoke_test_api.sh" --fastapi-tests --seed-headers
fi

success "$my_name" "Smoke validation completed successfully"