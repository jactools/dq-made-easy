#!/usr/bin/env bash
# Purpose: Start the core stack, Airflow, and optionally observability plus local UI.
#
# What it does:
# - Calls start-containers.sh with a standard baseline of profiles, including Airflow.
# - Optionally includes observability components.
# - Restarts the local Vite UI processes.
#
# Version: 1.8
# Last modified: 2026-06-30
# Changelog:
# - 1.2 (2026-04-26): Added env-file selection flags and propagated ROOT_ENV_FILE through the common startup chain.
# - 1.3 (2026-04-29): Switched startup env selection to the canonical dev/test/prod contract.
# - 1.4 (2026-05-10): Start the edge compose profile alongside the core stack.
# - 1.5 (2026-05-30): Build the precompiled dq-airflow-sdk wheel during --force-build so Airflow image builds consume the current repo artifact.
# - 1.6 (2026-05-30): Include the Airflow profile in the default common startup chain.
# - 1.7 (2026-06-02): Allow the distributed Spark cluster profile to be opt-in via --with-spark.
# - 1.8 (2026-06-30): Avoid Bash nounset failures when --env consumes all CLI arguments.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR"

START_OBSERVABILITY=false
START_SPARK=false
FORCE_BUILD=false

source "$ROOT_DIR/scripts/supporting/logging.sh"
set_log_level INFO
my_name="common_startup.sh"

cd "$ROOT_DIR"

print_usage() {
  printf '%s\n' \
    "Usage: ./scripts/common_startup.sh [OPTIONS]" \
    "" \
    "Canonical env options:" \
    "  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local" \
    "  --env-file PATH          Use an explicit env file for CI, /etc, or diagnostics" \
    "" \
    "Other options:" \
    "  --with-observability" \
    "  --with-spark" \
    "  --force-build" \
    "  -h, --help"
}

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-observability) START_OBSERVABILITY=true; shift ;;
    --with-spark) START_SPARK=true; shift ;;
    --force-build) FORCE_BUILD=true; shift ;;
    -h|--help) print_usage; exit 0 ;;
    *) error "Unknown arg: $1"; print_usage; exit 1 ;;
  esac
done

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

export ROOT_ENV_FILE
info "$my_name" "Environment selection: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE") -> $ROOT_ENV_FILE"
info "$my_name" "Starting container stack orchestration..."

START_ARGS=(--with-core --with-auth --with-edge --with-gateway --with-engine --with-workers --with-airflow --seed-all --init-db)
if [ "$START_SPARK" = true ]; then
  START_ARGS+=(--with-spark)
fi
if [ "$START_OBSERVABILITY" = true ]; then
  START_ARGS+=(--with-observability)
fi
if [ "$FORCE_BUILD" = true ]; then
  START_ARGS+=(--force-build)
fi

# Disable deliveries seeding for local startup
START_ARGS+=(--no-seed-deliveries)

./scripts/start-containers.sh "${START_ARGS[@]}" || {
  error "Failed to start containers. Aborting startup."
  exit 2
}

info "$my_name" "Container stack startup completed; refreshing local UI..."

# Stop and restart the UI
./dq-ui/scripts/stop_local.sh

./dq-ui/scripts/start_local.sh || {
  error "Failed to start UI. Aborting startup."
  exit 3
}
