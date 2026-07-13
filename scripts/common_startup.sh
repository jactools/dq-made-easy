#!/usr/bin/env bash
# Purpose: Start the core stack, Airflow, and optionally observability plus local UI.
#
# What it does:
# - Calls start-containers.sh with a standard baseline of profiles, including Airflow.
# - Optionally includes observability components.
# - Restarts the local Vite UI processes.
#
# Version: 2.1
# Last modified: 2026-07-12
# Changelog:
# - 1.2 (2026-04-26): Added env-file selection flags and propagated ROOT_ENV_FILE through the common startup chain.
# - 1.3 (2026-04-29): Switched startup env selection to the canonical dev/test/prod contract.
# - 1.4 (2026-05-10): Start the edge compose profile alongside the core stack.
# - 1.5 (2026-05-30): Build the precompiled dq-airflow-sdk wheel during --force-build so Airflow image builds consume the current repo artifact.
# - 1.6 (2026-05-30): Include the Airflow profile in the default common startup chain.
# - 1.7 (2026-06-02): Allow the distributed Spark cluster profile to be opt-in via --with-spark.
# - 1.8 (2026-06-30): Avoid Bash nounset failures when --env consumes all CLI arguments.
# - 1.9 (2026-07-12): Move startup progress monitoring into a dedicated helper.
# - 2.0 (2026-07-12): Check monitor abort flag after wait() so error-triggered
#   aborts propagate even when the child process tree survives kill.
# - 2.1 (2026-07-12): Rotate env-file passwords on each startup; store result in
#   tmp/env_passwords/<env>.env and source before starting containers.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR"

START_OBSERVABILITY=false
START_SPARK=false
FORCE_BUILD=false

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/startup_monitor.sh"
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
    "Profile options:" \
    "  --with-spark" \
    "" \
    "Seeding options:" \
    "  --seed-postgres" \
    "  --seed-keycloak" \
    "  --seed-zammad" \
    "  --seed-deliveries" \
    "  --seed-all" \
    "  --init-db" \
    "  --no-seed-deliveries" \
    "" \
    "Other options:" \
    "  --force-build" \
    "  -h, --help"
}

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

CONTAINER_ARGS=()
SEED_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-spark) START_SPARK=true; shift ;;
    --force-build) FORCE_BUILD=true; shift ;;
    # Pass through profile flags to start-containers.sh
    --with-*|--all) CONTAINER_ARGS+=("$1"); shift ;;
    # Pass through seeding flags to seed_containers.sh
    --seed-*|--no-seed-*|--init-db|--purge-bucket|--wipe-aistor) SEED_ARGS+=("$1"); shift ;;
    -h|--help) print_usage; exit 0 ;;
    *) error "Unknown arg: $1"; print_usage; exit 1 ;;
  esac
done

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

info "$my_name" "Validating selected env file before startup..."
validate_selected_root_env_file "$ROOT_DIR" full

export ROOT_ENV_FILE
info "$my_name" "Environment selection: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE") -> $ROOT_ENV_FILE"

# Generate runtime secrets (DB passwords, encryption keys, tokens)
info "$my_name" "Generating runtime secrets..."
$ROOT_DIR/scripts/generate_secrets.sh --env-file "$ROOT_ENV_FILE" || {
  error "$my_name" "Failed to generate runtime secrets"
  exit 1
}

# Source the generated secrets
if [ -f "$SECRETS_ENV_FILE" ]; then
  info "$my_name" "Sourcing generated secrets from $SECRETS_ENV_FILE"
  set -a
  source "$SECRETS_ENV_FILE"
  set +a
else
  error "$my_name" "Secrets file not found after generation"
  exit 1
fi

# Rotate env-file passwords and store in tmp/env_passwords/<env>.env
info "$my_name" "Rotating env-file passwords..."
ENV_PASSWORD_ROTATION_OUTPUT=$($ROOT_DIR/scripts/python_arm64.sh "$ROOT_DIR/scripts/supporting/seed_password_rotation.py" \
    --env-file "$ROOT_ENV_FILE" \
    --output-dir "$ROOT_DIR/tmp/env_passwords")
if [ $? -ne 0 ]; then
  error "$my_name" "Failed to rotate env-file passwords"
  error "$my_name" "$ENV_PASSWORD_ROTATION_OUTPUT"
  exit 1
fi
info "$my_name" "$ENV_PASSWORD_ROTATION_OUTPUT"

# Derive env name from ROOT_ENV_FILE for the rotated file path
_env_name="$ROOT_ENV_FILE"
_env_name="${_env_name##*/}"            # strip directory
_env_name="${_env_name%.local}"        # strip .local suffix
_env_name="${_env_name#.env.}"         # strip .env. prefix
[ -z "$_env_name" ] && _env_name="local"
ENV_PASSWORDS_FILE="$ROOT_DIR/tmp/env_passwords/${_env_name}.env"
if [ -f "$ENV_PASSWORDS_FILE" ]; then
  info "$my_name" "Sourcing rotated passwords from $ENV_PASSWORDS_FILE"
  set -a  # export all subsequent assignments
  source "$ENV_PASSWORDS_FILE"
  set +a
else
  error "$my_name" "Rotated env file not found: $ENV_PASSWORDS_FILE"
  exit 1
fi

info "$my_name" "Starting container stack orchestration..."

# Build container startup args (profiles + force-build)
CONTAINER_START_ARGS=(--with-core --with-auth --with-edge --with-gateway --with-engine --with-workers --with-airflow --with-observability)
if [ "$START_SPARK" = true ]; then
  CONTAINER_START_ARGS+=(--with-spark)
fi
if [ "$FORCE_BUILD" = true ]; then
  CONTAINER_START_ARGS+=(--force-build)
fi
# Append any additional profile flags from CLI
CONTAINER_START_ARGS+=("${CONTAINER_ARGS[@]}")

# Build seeding args (default: seed all and init db if no seeding flags provided)
if [ ${#SEED_ARGS[@]} -eq 0 ]; then
  SEED_ARGS=(--seed-all --init-db --no-seed-deliveries)
fi

# Suppress the docker compose spinner so output is readable alongside the monitor.
export COMPOSE_PROGRESS=plain

# Start containers
info "$my_name" "Starting containers with args: ${CONTAINER_START_ARGS[*]}"
./scripts/start-containers.sh "${CONTAINER_START_ARGS[@]}" || {
  error "$my_name" "Failed to start containers. Aborting startup."
  exit 2
}

# Run seeding
info "$my_name" "Running seeding with args: ${SEED_ARGS[*]}"
./scripts/seed_containers.sh "${SEED_ARGS[@]}" || {
  error "$my_name" "Failed to seed containers. Aborting startup."
  exit 2
}

# startup_pid=$!
# info "$my_name" "Startup process PID: $startup_pid"

# Launch the background monitor that tails the log and prints the grid.
# info "$my_name" "Launching startup monitor..."
# startup_monitor_start "$startup_pid"

# # Wait for startup to complete
# info "$my_name" "Waiting for startup to complete..."
# wait "$startup_pid"
# startup_exit_code=$?

# Stop monitoring
# info "$my_name" "Stopping startup monitor..."
# startup_monitor_cleanup

# Check if the monitor triggered an abort (e.g. error state, timeout)
# This catches cases where kill/wait doesn't propagate cleanly.
# abort_file="${ROOT_DIR}/tmp/startup_monitor.abort"
# if [ -f "$abort_file" ]; then
#   abort_reason="$(cat "$abort_file" 2>/dev/null || echo 'unknown')"
#   error "$my_name" "Startup monitor aborted: $abort_reason"
#   rm -f "$abort_file"
#   exit 2
# fi

# if [ "$startup_exit_code" -ne 0 ]; then
#   error "$my_name" "Failed to start containers (exit $startup_exit_code). Aborting startup."
#   exit 2
# fi

info "$my_name" "Container stack startup completed; refreshing local UI..."

# Stop and restart the UI
info "$my_name" "Stopping local UI..."
./dq-ui/scripts/stop_local.sh

info "$my_name" "Starting local UI..."
./dq-ui/scripts/start_local.sh || {
  error "$my_name" "Failed to start UI. Aborting startup."
  exit 3
}
