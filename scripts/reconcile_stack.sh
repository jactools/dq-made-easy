#!/usr/bin/env bash
set -euo pipefail

# Purpose: Run explicit post-start reconciliation actions for the stack.
# What it does:
# - Reconciles Kong, Keycloak, and OpenMetadata as separate explicit actions.
# - Uses canonical env selection and shared compose/logging helpers.
# - Fails fast when a selected reconciliation target is unavailable.
# Version: 1.1
# Last modified: 2026-07-01

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
my_name="reconcile_stack.sh"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/env/selection.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
source "$ROOT_DIR/scripts/supporting/auth.sh"
source "$ROOT_DIR/scripts/supporting/readiness.sh"
source "$ROOT_DIR/scripts/startup/gateway.sh"
init_root_env_file "$ROOT_DIR"

ACTION_GATEWAY=false
ACTION_KEYCLOAK=false
ACTION_METADATA=false

fail() {
  error "$1"
  exit 1
}

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --all              Reconcile Kong, Keycloak, and OpenMetadata
  --gateway          Reconcile Kong bootstrap and gateway checks
  --keycloak         Reconcile Keycloak client state
  --metadata         Reconcile OpenMetadata configuration
  --env dev|test|prod
  --env-file PATH
  -h, --help
EOF
}

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  usage
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      ACTION_GATEWAY=true
      ACTION_KEYCLOAK=true
      ACTION_METADATA=true
      shift
      ;;
    --gateway)
      ACTION_GATEWAY=true
      shift
      ;;
    --keycloak)
      ACTION_KEYCLOAK=true
      shift
      ;;
    --metadata)
      ACTION_METADATA=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "reconcile_stack.sh" "Unknown arg: $1"
      usage
      exit 1
      ;;
  esac
done

if [ "$ACTION_GATEWAY" = false ] && [ "$ACTION_KEYCLOAK" = false ] && [ "$ACTION_METADATA" = false ]; then
  fail "Select --all, --gateway, --keycloak, or --metadata for reconcile"
fi

if [ ! -f "$ROOT_ENV_FILE" ]; then
  fail "Env file not found: $ROOT_ENV_FILE"
fi

validate_selected_root_env_file "$ROOT_DIR" full

set -a
# shellcheck disable=SC1090
source "$ROOT_ENV_FILE"
set +a

source "$ROOT_DIR/scripts/supporting/setup_env.sh"

KONG_HEALTHCHECK_URL="${KONG_LOCAL_PROBE_BASE_URL:-${KONG_PUBLIC_URL%/}}/system/v1/health"

if [ "$ACTION_KEYCLOAK" = true ]; then
  info "reconcile_stack.sh" "Running Keycloak reconciliation"
  "$ROOT_DIR/scripts/keycloak_post_seed_tasks.sh"
fi

if [ "$ACTION_GATEWAY" = true ]; then
  info "reconcile_stack.sh" "Running Kong reconciliation"
  START_PHASE=post
  START_GATEWAY=true
  start_stack_block_gateway
fi

if [ "$ACTION_METADATA" = true ]; then
  info "reconcile_stack.sh" "Running OpenMetadata reconciliation"
  if ! dq_source_seeded_user_credentials --quiet; then
    fail "Unable to load seeded credentials for OpenMetadata reconciliation"
  fi
  docker_compose --profile metadata run --rm openmetadata-configure
fi

success "reconcile_stack.sh" "Reconciliation completed successfully"