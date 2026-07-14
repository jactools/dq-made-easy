#!/usr/bin/env bash
# Purpose: Restart the compose stack. Reuses admin passwords, rotates service/user passwords.
#
# What it does:
#   1. Stops all containers (stack_stop.sh)
#   2. Regenerates secrets (--reuse-admin: admin passwords kept, service/user rotated)
#   3. Rotates env-file passwords (skipping admin)
#   4. Brings up containers
#   5. Waits for critical services
#
# Stateful volumes are KEPT (admin passwords in DB match the reused values).
#
# Usage:
#   ./scripts/stack_restart.sh --env dev
#   ./scripts/stack_restart.sh --env test
#   ./scripts/stack_restart.sh --env prod
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
source "$ROOT_DIR/scripts/supporting/stack_lifecycle.sh"
source "$ROOT_DIR/scripts/supporting/setup_env.sh"

init_root_env_file "$ROOT_DIR"

print_usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Restarts the compose stack. Admin passwords are reused (volumes preserved);
service and user passwords are rotated on every restart.

Options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file
  --force-build            Build images before starting (no cache reuse)
  --no-build               Skip image builds entirely
  -h, --help               Show this help
EOF
}

FORCE_BUILD=false
NO_BUILD=false

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force-build) FORCE_BUILD=true; shift ;;
    --no-build) NO_BUILD=true; shift ;;
    -h|--help) print_usage; exit 0 ;;
    *) error "stack_restart.sh" "Unknown argument: $1"; print_usage; exit 1 ;;
  esac
done

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "stack_restart.sh" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

export ROOT_ENV_FILE

# ---------------------------------------------------------------------------
# Step 1: Stop containers
# ---------------------------------------------------------------------------
info "stack_restart.sh" "Stopping containers..."
docker_compose stop 2>/dev/null || true
docker_compose down --remove-orphans 2>/dev/null || true

# ---------------------------------------------------------------------------
# Step 2: Generate secrets (BEFORE sourcing env file)
# The env file references ${DQ_DB_PASSWORD} etc. in URL construction,
# so secrets must be sourced first.
# ---------------------------------------------------------------------------
info "stack_restart.sh" "Generating secrets (--reuse-admin)..."
SECRETS_OUTPUT=$("$ROOT_DIR/scripts/generate_secrets.sh" --env-file "$ROOT_ENV_FILE" --force --reuse-admin 2>&1) || {
  error "stack_restart.sh" "Failed to generate secrets"
  error "stack_restart.sh" "$SECRETS_OUTPUT"
  exit 1
}
info "stack_restart.sh" "$SECRETS_OUTPUT"

SECRETS_ENV_FILE="$(echo "$SECRETS_OUTPUT" | grep '^SECRETS_ENV_FILE=' | cut -d= -f2-)"
if [ -n "$SECRETS_ENV_FILE" ] && [ -f "$SECRETS_ENV_FILE" ]; then
  set -a
  source "$SECRETS_ENV_FILE"
  set +a
  export SECRETS_ENV_FILE
else
  error "stack_restart.sh" "Secrets file not found after generation"
  exit 1
fi

# Now source the env file (password references are now resolved)
source_runtime_env_dependencies "$ROOT_ENV_FILE" pre-root
set -a
source "$ROOT_ENV_FILE"
set +a

# ---------------------------------------------------------------------------
# Step 4: Rotate env-file passwords (skip admin)
# ---------------------------------------------------------------------------
info "stack_restart.sh" "Rotating env-file passwords (--no-admin-rotate)..."
ROTATE_OUTPUT=$("$ROOT_DIR/scripts/python_arm64.sh" "$ROOT_DIR/scripts/supporting/seed_password_rotation.py" \
    --env-file "$ROOT_ENV_FILE" \
    --output-dir "$ROOT_DIR/tmp/env_passwords" \
    --no-admin-rotate 2>&1) || {
  error "stack_restart.sh" "Failed to rotate env-file passwords"
  error "stack_restart.sh" "$ROTATE_OUTPUT"
  exit 1
}
info "stack_restart.sh" "$ROTATE_OUTPUT"

# Source the rotated env file
_ENV_SUFFIX="$("$ROOT_DIR/scripts/python_arm64.sh" -c "
import sys
p = sys.argv[1]
p = p.rsplit('/', 1)[-1]
if p.endswith('.local'): p = p[:-6]
if p.startswith('.env.'): p = p[5:]
print(p or 'local')
" "$ROOT_ENV_FILE")"
ENV_PASSWORDS_FILE="$ROOT_DIR/tmp/env_passwords/${_ENV_SUFFIX}.env"
if [ -f "$ENV_PASSWORDS_FILE" ]; then
  set -a
  source "$ENV_PASSWORDS_FILE"
  set +a
fi

# ---------------------------------------------------------------------------
# Step 5: Ensure TLS certs
# ---------------------------------------------------------------------------
"$ROOT_DIR/scripts/create_certs.sh" --env-file "$ROOT_ENV_FILE" || {
  error "stack_restart.sh" "Certificate generation failed (create_certs.sh)"
  exit 1
}

# ---------------------------------------------------------------------------
# Step 6: Build and run the trust-bundle container
# ---------------------------------------------------------------------------
info "stack_restart.sh" "Building trust bundle (JKS/P12)..."
"$ROOT_DIR/scripts/build_trust_bundle.sh" --env-file "$ROOT_ENV_FILE" || {
  error "stack_restart.sh" "Trust-bundle build failed"
  exit 1
}

# ---------------------------------------------------------------------------
# Step 7: Build images if requested
# ---------------------------------------------------------------------------
if [ "$FORCE_BUILD" = true ]; then
  info "stack_restart.sh" "Building images (--force-build)..."
  docker_compose build --no-cache || {
    error "stack_restart.sh" "Image build failed"
    exit 1
  }
elif [ "$NO_BUILD" != true ]; then
  info "stack_restart.sh" "Building images..."
  docker_compose build || {
    error "stack_restart.sh" "Image build failed"
    exit 1
  }
else
  info "stack_restart.sh" "Skipping image build (--no-build)"
fi

# ---------------------------------------------------------------------------
# Step 8: Bring up containers
# ---------------------------------------------------------------------------
info "stack_restart.sh" "Starting containers..."
export COMPOSE_PROGRESS=plain
# Build profile args for compose up — include all default profiles
PROFILE_ARGS=()
source "$ROOT_DIR/scripts/stack_catalog.sh" 2>/dev/null || true
while IFS= read -r profile; do
  [ -z "$profile" ] && continue
  PROFILE_ARGS+=(--profile "$profile")
done < <(default_runtime_profile_values)
PROFILE_ARGS+=(--profile airflow --profile llm --profile seed --profile spark --profile metadata_ingestion)

docker_compose "${PROFILE_ARGS[@]}" up -d --force-recreate --remove-orphans || {
  error "stack_restart.sh" "docker compose up failed"
  exit 1
}

# ---------------------------------------------------------------------------
# Step 8: Wait for critical services
# ---------------------------------------------------------------------------
wait_for_compose_service_healthy keycloak "Keycloak (service=keycloak)" 120 5 || {
  error "stack_restart.sh" "Keycloak did not become healthy"
  docker_compose logs --no-color --tail 80 keycloak || true
  exit 1
}

wait_for_compose_service_healthy db "Postgres (service=db)" 120 5 || {
  error "stack_restart.sh" "Postgres (service=db) did not become healthy"
  docker_compose logs --no-color --tail 80 db || true
  exit 1
}

success "stack_restart.sh" "Stack restarted"
