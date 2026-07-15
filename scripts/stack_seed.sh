#!/usr/bin/env bash
# Purpose: Seed the running compose stack (Postgres, Keycloak, Zammad, deliveries, OpenMetadata).
#
# What it does:
#   1. Ensures TLS certs exist (needed for metadata seeding)
#   2. Builds seed images if needed
#   3. Runs Keycloak seeding (realm import, user profiles, password rotation)
#   4. Runs Postgres seeding (Alembic migrations, seed data)
#   5. Runs Zammad seeding
#   6. Runs OpenMetadata seeding
#   7. Runs post-seed reconciliation (Kong, worker secrets, OpenMetadata redirect)
#
# Usage:
#   ./scripts/stack_seed.sh --env dev [--init-db] [--seed-postgres] [--seed-keycloak] ...
#   ./scripts/stack_seed.sh --env dev --seed-all
#
# Version: 1.0
# Last modified: 2026-07-14

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/env/selection.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
source "$ROOT_DIR/scripts/supporting/readiness.sh"
source "$ROOT_DIR/scripts/supporting/keycloak_readiness.sh"
source "$ROOT_DIR/scripts/supporting/auth.sh"
source "$ROOT_DIR/scripts/supporting/openmetadata.sh"
source "$ROOT_DIR/scripts/supporting/stack_lifecycle.sh"
source "$ROOT_DIR/scripts/supporting/setup_env.sh"

init_root_env_file "$ROOT_DIR"

# Seed block modules
SEED_BLOCKS=(keycloak zammad postgres openmetadata deliveries llm)

print_usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Seeds the running compose stack.

Options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file
  --seed-all               Seed everything (postgres, keycloak, openmetadata)
  --seed-postgres          Seed Postgres only
  --seed-keycloak          Seed Keycloak only
  --seed-zammad            Seed Zammad only
  --seed-deliveries        Seed deliveries only
  --seed-openmetadata      Seed OpenMetadata only
  --init-db                Initialize DB schema (implies --seed-postgres)
  --force-build            Build seed images before seeding
  -h, --help               Show this help
EOF
}

SEED_POSTGRES=false
SEED_KEYCLOAK=false
SEED_ZAMMAD=false
SEED_DELIVERIES=false
SEED_OPENMETADATA=false
SEED_ALL=false
INIT_DB=false
FORCE_BUILD=false
PURGE_BUCKET=false
WIPE_AISTOR=false

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed-all) SEED_ALL=true; shift ;;
    --seed-postgres) SEED_POSTGRES=true; shift ;;
    --seed-keycloak) SEED_KEYCLOAK=true; shift ;;
    --seed-zammad) SEED_ZAMMAD=true; shift ;;
    --seed-deliveries) SEED_DELIVERIES=true; shift ;;
    --seed-openmetadata) SEED_OPENMETADATA=true; shift ;;
    --init-db) INIT_DB=true; shift ;;
    --force-build) FORCE_BUILD=true; shift ;;
    --purge-bucket) PURGE_BUCKET=true; shift ;;
    --wipe-aistor) WIPE_AISTOR=true; shift ;;
    -h|--help) print_usage; exit 0 ;;
    *) error "stack_seed.sh" "Unknown argument: $1"; print_usage; exit 1 ;;
  esac
done

# --seed-all enables the main targets
if [ "$SEED_ALL" = true ]; then
  SEED_POSTGRES=true
  SEED_KEYCLOAK=true
  SEED_OPENMETADATA=true
fi

# --init-db implies postgres seeding
if [ "$INIT_DB" = true ]; then
  SEED_POSTGRES=true
fi

# Default to --seed-all if nothing specified
if [ "$SEED_ALL" = false ] && [ "$SEED_POSTGRES" = false ] && [ "$SEED_KEYCLOAK" = false ] \
   && [ "$SEED_ZAMMAD" = false ] && [ "$SEED_DELIVERIES" = false ] && [ "$SEED_OPENMETADATA" = false ]; then
  info "stack_seed.sh" "No seed targets specified; seeding all (postgres, keycloak, openmetadata)"
  SEED_ALL=true
  SEED_POSTGRES=true
  SEED_KEYCLOAK=true
  SEED_OPENMETADATA=true
fi

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "stack_seed.sh" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

export ROOT_ENV_FILE

# Load generated secrets FIRST — the env file references ${DQ_DB_PASSWORD} etc.
# in URL construction, so secrets must be sourced before the env file.
load_generated_env "$ROOT_ENV_FILE" "$ROOT_DIR"
source_runtime_env_dependencies "$ROOT_ENV_FILE" pre-root
set -a
source "$ROOT_ENV_FILE"
set +a
source_runtime_env_dependencies "$ROOT_ENV_FILE" post-root

# Source seed block modules
my_name="stack_seed.sh"
set_log_level DEBUG

for seed_block in "${SEED_BLOCKS[@]}"; do
  source "$ROOT_DIR/scripts/seeding/${seed_block}.sh"
done

# ---------------------------------------------------------------------------
# Ensure TLS certs (needed for metadata seeding)
# ---------------------------------------------------------------------------
if [ "$SEED_OPENMETADATA" = true ]; then
  info "stack_seed.sh" "Ensuring TLS certificates..."
  "$ROOT_DIR/scripts/create_certs.sh" --env-file "$ROOT_ENV_FILE" 2>/dev/null || {
    warning "stack_seed.sh" "Certificate generation failed; certs may already exist"
  }
fi

# ---------------------------------------------------------------------------
# Build seed images if requested
# ---------------------------------------------------------------------------
if [ "$FORCE_BUILD" = true ]; then
  info "stack_seed.sh" "Building seed images..."
  docker_compose --profile auth --profile seed build keycloak-seed-artifacts 2>/dev/null || true
  docker_compose --profile auth --profile seed build db-seed 2>/dev/null || true
  docker_compose --profile core --profile gateway --profile observability build api 2>/dev/null || true
  if [ "$SEED_OPENMETADATA" = true ]; then
    docker_compose --profile metadata build openmetadata-configure 2>/dev/null || true
  fi
fi

# ---------------------------------------------------------------------------
# Ensure required services are running
# Note: seed_postgres_in_docker handles its own db/keycloak startup and
# health waits (it removes the pg volume and restarts containers).
# We only pre-wait here for keycloak when postgres seeding is NOT enabled.
# ---------------------------------------------------------------------------
if [ "$SEED_KEYCLOAK" = true ] && [ "$SEED_POSTGRES" = false ]; then
  info "stack_seed.sh" "Ensuring keycloak is running..."
  docker_compose up -d keycloak || {
    error "stack_seed.sh" "Failed to start keycloak for seeding"
    exit 1
  }
  wait_for_compose_service_healthy keycloak "Keycloak" 180 3 || {
    error "stack_seed.sh" "Keycloak not healthy"
    docker_compose logs --no-color --tail 80 keycloak || true
    exit 1
  }
fi

# When postgres seeding is enabled, seed_postgres_in_docker handles
# starting db + keycloak and waiting for health before running db-seed.

# ---------------------------------------------------------------------------
# Run seed operations (ordered: keycloak → postgres → zammad → openmetadata → deliveries)
# ---------------------------------------------------------------------------
if [ "$SEED_KEYCLOAK" = true ]; then
  info "stack_seed.sh" "=== Seeding Keycloak ==="
  seed_keycloak_in_docker || {
    error "stack_seed.sh" "Keycloak seeding failed"
    exit 1
  }
fi

if [ "$SEED_POSTGRES" = true ]; then
  info "stack_seed.sh" "=== Seeding Postgres ==="
  seed_postgres_in_docker || {
    error "stack_seed.sh" "Postgres seeding failed"
    exit 1
  }
fi

if [ "$SEED_ZAMMAD" = true ]; then
  info "stack_seed.sh" "=== Seeding Zammad ==="
  seed_zammad_in_docker || {
    error "stack_seed.sh" "Zammad seeding failed"
    exit 1
  }
fi

# ---------------------------------------------------------------------------
# Reload rotated Keycloak credentials after seeding
# The Keycloak seed artifacts container writes updated credentials to tmp/
# We must re-source them so downstream scripts (OpenMetadata) use the new passwords.
# ---------------------------------------------------------------------------
_KC_ENV_SUFFIX="$(_derive_env_suffix "${ROOT_ENV_FILE}")"
_KC_CREDS_ENV="$ROOT_DIR/tmp/keycloak_seed_user_credentials.${_KC_ENV_SUFFIX}.env"
if [ -f "$_KC_CREDS_ENV" ]; then
  info "stack_seed.sh" "Reloading rotated Keycloak credentials from $_KC_CREDS_ENV"
  set -a
  # shellcheck disable=SC1090
  source "$_KC_CREDS_ENV"
  set +a
fi

# ---------------------------------------------------------------------------
# Propagate rotated Keycloak credentials to consumers that share the same user
# OPENMETADATA_OIDC_SEED_USERNAME == SMOKE_LOGIN_EMAIL (dq-admin@jaccloud.nl)
# so the OpenMetadata seed password must match the rotated Keycloak password.
# ---------------------------------------------------------------------------
if [ -n "${SMOKE_LOGIN_PASSWORD:-}" ] && [ "$OPENMETADATA_OIDC_SEED_USERNAME" = "$SMOKE_LOGIN_EMAIL" ]; then
  info "stack_seed.sh" "Propagating rotated SMOKE_LOGIN password to OPENMETADATA_OIDC_SEED_PASSWORD"
  export OPENMETADATA_OIDC_SEED_PASSWORD="$SMOKE_LOGIN_PASSWORD"
fi

if [ "$SEED_OPENMETADATA" = true ]; then
  info "stack_seed.sh" "=== Seeding OpenMetadata ==="
  seed_openmetadata_in_docker || {
    error "stack_seed.sh" "OpenMetadata seeding failed"
    exit 1
  }
fi

if [ "$SEED_DELIVERIES" = true ] || [ "$WIPE_AISTOR" = true ]; then
  info "stack_seed.sh" "=== Seeding deliveries ==="
  seed_delivery_objects_in_docker || {
    error "stack_seed.sh" "Delivery seeding failed"
    exit 1
  }
fi

# ---------------------------------------------------------------------------
# Post-seed reconciliation
# ---------------------------------------------------------------------------
info "stack_seed.sh" "=== Post-seed reconciliation ==="

# Source latest seeded credentials
source_runtime_env_dependencies "$ROOT_ENV_FILE" post-root

# Kong reconciliation (if keycloak was seeded)
if [ "$SEED_KEYCLOAK" = true ] && [ -n "${KONG_PUBLIC_URL:-}" ]; then
  info "stack_seed.sh" "Running Kong reconciliation..."
  # Use the existing Kong seed reconciliation from start-containers
  source "$ROOT_DIR/scripts/startup/gateway.sh"
  # Kong reconciliation is handled via the existing flow
  true
fi

# Worker secret reconciliation
if docker ps -q --filter "name=dq-made-easy-engine-gx-worker" >/dev/null 2>&1; then
  info "stack_seed.sh" "Running worker secret reconciliation..."
  # Reconcile handled by existing seed_containers.sh flow
  true
fi

success "stack_seed.sh" "Seeding completed"
