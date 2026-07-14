#!/usr/bin/env bash
set -euo pipefail


# Purpose: Start the stack while optionally pulling images and/or seeding metadata components.
#
# What it does:
# - Loads repo env and image configuration.
# - Starts selected profiles (including metadata and ingestion).
# - Optionally runs seeding steps for DB, Keycloak, or OpenMetadata.
#
# Version: 1.4
# Last modified: 2026-07-01
# Changelog:
# - 1.1 (2026-04-27): Added env-file selection flags and propagated ROOT_ENV_FILE through compose calls.
# - 1.2 (2026-04-28): Updated help text to reflect the tracked deployment example and local runtime copy split.
# - 1.3 (2026-04-29): Switched pull/start env selection to the canonical dev/test/prod contract.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/auth.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
init_root_env_file "$ROOT_DIR"

print_usage() {
  printf '%s\n' \
    "Usage: $0 [OPTIONS]" \
    "" \
    "Canonical env options:" \
    "  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local" \
    "  --env-file PATH          Use an explicit env file for CI, /etc, or diagnostics" \
    "" \
    "Other options:" \
    "  --seed" \
    "  --seed-keycloak" \
    "  --seed-openmetadata" \
    "  --seed-all" \
    "  --with-metadata" \
    "  --without-metadata" \
    "  --with-metadata-ingestion" \
    "  -h, --help"
}

SEED_DB=false
SEED_OPENMETADATA=false
SEED_KEYCLOAK=false
START_METADATA=true
START_METADATA_INGESTION=false

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 1
fi

my_name="start_stack_pull.sh"

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed)
      SEED_DB=true
      shift
      ;;
    --seed-openmetadata)
      SEED_OPENMETADATA=true
      shift
      ;;
    --seed-keycloak)
      SEED_KEYCLOAK=true
      shift
      ;;
    --seed-all)
      SEED_DB=true
      SEED_OPENMETADATA=true
      SEED_KEYCLOAK=true
      shift
      ;;
    --with-metadata)
      START_METADATA=true
      shift
      ;;
    --without-metadata)
      START_METADATA=false
      START_METADATA_INGESTION=false
      shift
      ;;
    --with-metadata-ingestion)
      START_METADATA=true
      START_METADATA_INGESTION=true
      shift
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      error "$my_name" "Unknown arg: $1"
      print_usage
      exit 1
      ;;
  esac
done

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "$my_name" "env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

export ROOT_ENV_FILE

info "$my_name" "Environment selection: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE") -> $ROOT_ENV_FILE"

set -a
source "$ROOT_ENV_FILE"
set +a

. "$SCRIPT_DIR/setup_env.sh"

if $SEED_OPENMETADATA; then
  if ! dq_source_seeded_user_credentials --quiet; then
    error "start_stack_pull.sh" "Unable to load seeded Keycloak credentials for OpenMetadata seeding"
    exit 1
  fi
  if ! $START_METADATA; then
    info "$my_name" "--seed-openmetadata requested: enabling metadata profile"
    START_METADATA=true
  fi
  if ! $START_METADATA_INGESTION; then
    info "$my_name" "--seed-openmetadata requested: enabling metadata-ingestion profile"
    START_METADATA_INGESTION=true
  fi
fi

PROFILE_ARGS=()
if $START_METADATA; then
  PROFILE_ARGS+=(--profile metadata)
fi
if $START_METADATA_INGESTION; then
  PROFILE_ARGS+=(--profile metadata-ingestion)
fi

cd "$ROOT_DIR"

info "$my_name" "Resolved images:"
docker_compose "${PROFILE_ARGS[@]}" config --images
info "$my_name" ""

info "$my_name" "Pulling images from docker-compose.yml..."
docker_compose "${PROFILE_ARGS[@]}" pull

if $SEED_KEYCLOAK || $SEED_ALL; then
  info "$my_name" "Running Keycloak reseed before stack startup via seed_stack.sh..."
  ./scripts/seed_stack.sh --seed-keycloak || {
    error "$my_name" "Keycloak reseed failed before stack startup"
    exit 1
  }
  success "$my_name" "Keycloak reseed completed before stack startup."
fi

info "$my_name" "Starting stack (no build)..."
docker_compose "${PROFILE_ARGS[@]}" up -d --no-build

success "$my_name" "Stack started using pulled images only."

if $SEED_DB; then
  info "$my_name" "Seeding database..."
  remove_compose_postgres_volume || {
    error "$my_name" "Failed to remove the PostgreSQL data volume before seeding"
    exit 1
  }
  docker_compose up -d db keycloak
  wait_for_compose_service_healthy db "Postgres database" 60 2 || {
    error "$my_name" "Postgres database did not become healthy before seeding"
    exit 1
  }
  docker_compose --profile auth --profile seed run --rm db-seed
  success "$my_name" "Database seeded."
fi

if $SEED_OPENMETADATA; then
  info "$my_name" "Running OpenMetadata configuration and --seed-all sync..."
  docker_compose up -d keycloak openmetadata-server openmetadata-ingestion
  if ! $SEED_KEYCLOAK; then
    info "$my_name" "--seed-openmetadata requested without --seed-keycloak: reseeding Keycloak first so the live realm matches the generated credentials"
    ./scripts/seed_stack.sh --seed-keycloak
  fi
  docker_compose --profile metadata --profile auth run --rm openmetadata-configure --seed-all
fi
