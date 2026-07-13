#!/usr/bin/env bash
set -euo pipefail

# Purpose: Wrapper around seed_stack.sh that handles environment selection,
# pre-seeding image builds, and post-seeding reconciliation tasks.
#
# What it does:
# - Parses environment and seeding flags
# - Builds required seed images if --force-build is used
# - Delegates actual seeding to seed_stack.sh
# - Runs post-seeding reconciliation (Kong, worker secrets, OpenMetadata)
#
# Usage: ./scripts/seed_containers.sh [OPTIONS]
#
# Examples:
#   ./scripts/seed_containers.sh --env dev --seed-all
#   ./scripts/seed_containers.sh --env dev --seed-keycloak --seed-zammad
#   ./scripts/seed_containers.sh --env dev --force-build --seed-postgres

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/auth.sh"
source "$ROOT_DIR/scripts/supporting/env/selection.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
set_log_level INFO
my_name="seed_containers.sh"

SEED_ARGS=()
FORCE_BUILD=false

# Pass through all arguments to seed_stack.sh
# Environment selection (--env, --env-file) is handled by seed_stack.sh itself
SEED_ARGS=("$@")

# Check if --force-build is in args (for pre-build logic)
for arg in "${SEED_ARGS[@]}"; do
  if [ "$arg" = "--force-build" ]; then
    FORCE_BUILD=true
    break
  fi
done

# Ensure OpenMetadata TLS assets if metadata seeding is requested
for arg in "${SEED_ARGS[@]}"; do
  if [ "$arg" = "--seed-openmetadata" ] || [ "$arg" = "--seed-all" ]; then
    info "$my_name" "Ensuring OpenMetadata TLS assets are present..."
    "$ROOT_DIR/scripts/create_certs.sh" || exit 1
    break
  fi
done

# Build seed images if --force-build is used
if [ "$FORCE_BUILD" = true ]; then
  info "$my_name" "Building seed images before seeding (force-build mode)..."

  # Build images needed for seeding
  if docker_compose --profile auth --profile seed build keycloak-seed-artifacts 2>/dev/null; then
    info "$my_name" "Built keycloak-seed-artifacts image"
  fi

  if docker_compose --profile auth --profile seed build db-seed 2>/dev/null; then
    info "$my_name" "Built db-seed image"
  fi

  if docker_compose --profile core --profile gateway --profile observability build api 2>/dev/null; then
    info "$my_name" "Built api image"
  fi
fi

# Delegate to seed_stack.sh
info "$my_name" "Running seed_stack.sh with args: ${SEED_ARGS[*]}"
./scripts/seed_stack.sh "${SEED_ARGS[@]}" || {
  warning "$my_name" "seed_stack.sh failed"
  exit 1
}

# Post-seeding reconciliation tasks

# Kong seed reconciliation (if keycloak was seeded)
for arg in "${SEED_ARGS[@]}"; do
  if [ "$arg" = "--seed-keycloak" ] || [ "$arg" = "--seed-all" ]; then
    info "$my_name" "Running post-seeding reconciliation tasks..."
    ensure_kong_seed_reconciliation || exit 1
    enforce_keycloak_username_prompt_after_logout || true
    break
  fi
done

# Worker secret reconciliation (if workers are running)
if docker ps -q --filter "name=dq-made-easy-engine-gx-worker" >/dev/null 2>&1; then
  info "$my_name" "Running worker secret reconciliation..."
  ensure_keycloak_engine_worker_client_secret_matches_env || exit 1
fi

# OpenMetadata redirect reconciliation
if docker ps -q --filter "name=dq-made-easy-dev-openmetadata-server" >/dev/null 2>&1; then
  info "$my_name" "Running OpenMetadata redirect reconciliation..."
  ensure_keycloak_openmetadata_client_redirect_matches_env || exit 1
fi

info "$my_name" "✓ Seed containers completed successfully"
exit 0
