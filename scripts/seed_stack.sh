#!/usr/bin/env bash

# Purpose: Seed stack components after containers are running.
#
# What it does:
# - Optionally seeds Postgres and/or Keycloak (or both).
# - Waits for required services to become ready before seeding.
# - Supports an init-db path for fresh schema setup.
# - Can seed the Zammad first-run auto wizard, create required organizations, import generated users, and provision the support API token when support is enabled.
# - Can optionally generate AIStor delivery objects for note-backed mock deliveries.
# - Can purge target delivery buckets before seeding or wipe AIStor entirely for prototype resets.
#
# Version: 1.19
# Last modified: 2026-06-30
# Changelog:
# - 1.10 (2026-04-22): Replaced the delivery argument guard with a macOS Bash 3.2-safe array length check.
# - 1.11 (2026-04-26): Made seeding source and docker compose calls honor ROOT_ENV_FILE.
# - 1.12 (2026-04-27): Added direct env-file selection for non-default seeding targets.
# - 1.14 (2026-04-27): Uses bind-mounted seed sources so containerized Postgres seeding picks up workspace changes without rebuilding.
# - 1.15 (2026-04-29): Switched seed env selection to the canonical dev/test/prod contract.
# - 1.16 (2026-05-07): Kept Keycloak seeding on the existing running stack without restarting Keycloak or deleting volumes.
# - 1.17 (2026-05-09): Split seed actions into dedicated block modules sourced by seed_stack.sh.
# - 1.18 (2026-05-26): Added --force-build propagation for one-shot delivery seed image rebuilds.
# - 1.19 (2026-06-30): Avoid Bash nounset failures when --env consumes all CLI arguments.

set -euo pipefail


ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR"

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  exit 1
fi

REMAINING_ARGS=(${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"})

if [ ! -f "$ROOT_ENV_FILE" ]; then
  echo "Env file not found: $ROOT_ENV_FILE" >&2
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/auth.sh"
source "$ROOT_DIR/scripts/supporting/openmetadata.sh"
source "$ROOT_DIR/scripts/supporting/readiness.sh"
source "$ROOT_DIR/scripts/supporting/keycloak_readiness.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
set_log_level DEBUG
my_name="seed_stack.sh"

info "$my_name" "Environment selection: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE") -> $ROOT_ENV_FILE"

# Export repo env values so child processes such as the Python generators see them.
set -a
source "$ROOT_ENV_FILE"
set +a

source "$ROOT_DIR/scripts/supporting/setup_env.sh"

SEED_BLOCKS=(keycloak zammad postgres openmetadata deliveries llm)
for seed_block in "${SEED_BLOCKS[@]}"; do
  # shellcheck disable=SC1090
  source "$ROOT_DIR/scripts/seeding/${seed_block}.sh"
done

set -- "${REMAINING_ARGS[@]}"

info "$my_name" "started."

ZAMMAD_SUPPORT_TOKEN_NAME="${ZAMMAD_SUPPORT_TOKEN_NAME:-dq-made-easy support integration}"
ZAMMAD_SUPPORT_TOKEN_PERMISSION="${ZAMMAD_SUPPORT_TOKEN_PERMISSION:-ticket.agent}"

SEED_POSTGRES="${SEED_POSTGRES:-false}"
SEED_KEYCLOAK="${SEED_KEYCLOAK:-false}"
SEED_ZAMMAD="${SEED_ZAMMAD:-false}"
SEED_DELIVERIES="${SEED_DELIVERIES:-false}"
SEED_OPENMETADATA="${SEED_OPENMETADATA:-false}"
PURGE_BUCKET="${PURGE_BUCKET:-false}"
WIPE_AISTOR="${WIPE_AISTOR:-false}"
START_LLM="${START_LLM:-false}"
SEED_ALL="${SEED_ALL:-false}"
INIT_DB="${INIT_DB:-false}"
FORCE_BUILD="${FORCE_BUILD:-false}"

print_usage() {
  printf '%s\n' \
    "Usage: ./scripts/seed_stack.sh [OPTIONS]" \
    "" \
    "Canonical env options:" \
    "  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local" \
    "  --env-file PATH          Use an explicit env file for CI, /etc, or diagnostics" \
    "" \
    "Seed options:" \
    "  --seed-postgres" \
    "  --seed-keycloak" \
    "  --seed-zammad" \
    "  --seed-deliveries" \
    "  --seed-openmetadata" \
    "  --purge-bucket" \
    "  --wipe-aistor" \
    "  --with-llm" \
    "  --seed-all" \
    "  --init-db" \
    "  --force-build" \
    "  -h, --help"
}

#
# main logic
#
# Parse seeding-related flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed-postgres) SEED_POSTGRES=true; shift ;;
    --seed-keycloak) SEED_KEYCLOAK=true; shift ;;
    --seed-zammad) SEED_ZAMMAD=true; shift ;;
    --seed-deliveries) SEED_DELIVERIES=true; shift ;;
    --seed-openmetadata) SEED_OPENMETADATA=true; shift ;;
    --purge-bucket) PURGE_BUCKET=true; shift ;;
    --wipe-aistor) WIPE_AISTOR=true; shift ;;
    --with-llm) START_LLM=true; shift ;;
    --seed-all) SEED_ALL=true; shift ;;
    --init-db) INIT_DB=true; shift ;; 
    --force-build) FORCE_BUILD=true; shift ;;
    -h|--help) print_usage; exit 0 ;;
    *) error "$my_name" "Unknown arg: $1"; print_usage; exit 1 ;;
  esac
done

if [ "$SEED_ALL" = "true" ]; then
  info "$my_name" "--seed-all requested: enabling all seeding operations"
  SEED_POSTGRES=true
  SEED_KEYCLOAK=true
  SEED_OPENMETADATA=true
fi

if [ "$INIT_DB" = "true" ]; then
  info "$my_name" "Init-db requested: enabling Postgres seeding to initialize schema"
  SEED_POSTGRES=true
fi

if [ "$PURGE_BUCKET" = "true" ] && [ "$SEED_DELIVERIES" = "false" ] && [ "$WIPE_AISTOR" = "false" ]; then
  error "$my_name" "--purge-bucket must be used with --seed-deliveries or --wipe-aistor"
  exit 1
fi

# If no seeding flags provided, exit without doing anything to avoid unintended consequences.
if [ "$SEED_POSTGRES" = "false" ] && [ "$SEED_KEYCLOAK" = "false" ] && [ "$SEED_ZAMMAD" = "false" ] && [ "$SEED_DELIVERIES" = "false" ] && [ "$SEED_OPENMETADATA" = "false" ] && [ "$WIPE_AISTOR" = "false" ] && [ "$START_LLM" = "false" ]; then
  info "$my_name" "No seeding flags provided; exiting without doing anything. Use --seed-postgres, --seed-keycloak, --seed-zammad, --seed-deliveries, --seed-openmetadata, --wipe-aistor, --seed-all, or --with-llm to specify what to do."
    exit 0
fi

if [ "$SEED_KEYCLOAK" = "true" ]; then
  info "$my_name" "Starting Keycloak seeding..."
  seed_keycloak_in_docker
fi

if [ "$SEED_ZAMMAD" = "true" ]; then
  info "$my_name" "Starting Zammad seeding..."
  seed_zammad_in_docker
fi

if [ "$SEED_POSTGRES" = "true" ]; then
  info "$my_name" "Starting Postgres seeding..."
  seed_postgres_in_docker
fi

if [ "$SEED_OPENMETADATA" = "true" ]; then
  info "$my_name" "Starting OpenMetadata seeding..."
  seed_openmetadata_in_docker
fi

if [ "$SEED_DELIVERIES" = "true" ] || [ "$WIPE_AISTOR" = "true" ]; then
  info "$my_name" "Starting delivery objects seeding..."
  seed_delivery_objects_in_docker
fi

if [ "$START_LLM" = "true" ]; then
  info "$my_name" "Starting LLM..."
  start_llm_in_docker
fi

info "$my_name" "All requested seeding operations completed successfully."
exit 0
