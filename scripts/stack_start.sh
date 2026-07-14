#!/usr/bin/env bash
# Purpose: Start the compose stack. Generates/reuses secrets and starts all containers.
#
# What it does:
#   1. Detects whether this is a fresh start (no stateful volumes) or a restart (volumes exist)
#   2. On fresh start: generates ALL secrets and rotates ALL passwords (including admin)
#   3. On restart (volumes exist): reuses admin passwords from existing secrets,
#      generates new service/user passwords, rotates only non-admin env passwords
#   4. Ensures TLS certs exist
#   5. Brings up all compose containers
#   6. Waits for critical services (Keycloak, Postgres) to become healthy
#
# Usage:
#   ./scripts/stack_start.sh --env dev
#   ./scripts/stack_start.sh --env test
#   ./scripts/stack_start.sh --env prod
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

Starts the compose stack. Admin passwords are reused when stateful volumes exist
(to keep DB passwords consistent); service/user passwords always rotate.

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
    *) error "stack_start.sh" "Unknown argument: $1"; print_usage; exit 1 ;;
  esac
done

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "stack_start.sh" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

export ROOT_ENV_FILE
source_runtime_env_dependencies "$ROOT_ENV_FILE" pre-root
set -a
source "$ROOT_ENV_FILE"
set +a

# ---------------------------------------------------------------------------
# Determine start mode: fresh (no volumes) vs warm (volumes exist)
# ---------------------------------------------------------------------------
VOLUMES_EXIST=false
if stateful_volumes_exist; then
  VOLUMES_EXIST=true
  info "stack_start.sh" "Stateful volumes found — warm start (admin passwords will be reused)"
else
  info "stack_start.sh" "No stateful volumes — fresh start (all passwords will be generated)"
fi

# ---------------------------------------------------------------------------
# Step 1: Generate secrets
# ---------------------------------------------------------------------------
info "stack_start.sh" "Generating secrets..."
if [ "$VOLUMES_EXIST" = true ]; then
  # Reuse admin passwords from existing secrets file
  SECRETS_OUTPUT=$("$ROOT_DIR/scripts/generate_secrets.sh" --env-file "$ROOT_ENV_FILE" --force --reuse-admin 2>&1) || {
    error "stack_start.sh" "Failed to generate secrets"
    error "stack_start.sh" "$SECRETS_OUTPUT"
    exit 1
  }
  info "stack_start.sh" "$SECRETS_OUTPUT"
else
  # Fresh start — generate everything new
  SECRETS_OUTPUT=$("$ROOT_DIR/scripts/generate_secrets.sh" --env-file "$ROOT_ENV_FILE" --force 2>&1) || {
    error "stack_start.sh" "Failed to generate secrets"
    error "stack_start.sh" "$SECRETS_OUTPUT"
    exit 1
  }
  info "stack_start.sh" "$SECRETS_OUTPUT"
fi

# Extract and source the secrets file
SECRETS_ENV_FILE="$(echo "$SECRETS_OUTPUT" | grep '^SECRETS_ENV_FILE=' | cut -d= -f2-)"
if [ -n "$SECRETS_ENV_FILE" ] && [ -f "$SECRETS_ENV_FILE" ]; then
  set -a
  source "$SECRETS_ENV_FILE"
  set +a
  export SECRETS_ENV_FILE
else
  error "stack_start.sh" "Secrets file not found after generation"
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 2: Rotate env-file passwords
# ---------------------------------------------------------------------------
info "stack_start.sh" "Rotating env-file passwords..."
ROTATE_ARGS=(
  --env-file "$ROOT_ENV_FILE"
  --output-dir "$ROOT_DIR/tmp/env_passwords"
)
if [ "$VOLUMES_EXIST" = true ]; then
  # Skip admin passwords so DB credentials stay consistent
  ROTATE_ARGS+=(--no-admin-rotate)
fi

ROTATE_OUTPUT=$("$ROOT_DIR/scripts/python_arm64.sh" "$ROOT_DIR/scripts/supporting/seed_password_rotation.py" "${ROTATE_ARGS[@]}" 2>&1) || {
  error "stack_start.sh" "Failed to rotate env-file passwords"
  error "stack_start.sh" "$ROTATE_OUTPUT"
  exit 1
}
info "stack_start.sh" "$ROTATE_OUTPUT"

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
else
  error "stack_start.sh" "Rotated env file not found: $ENV_PASSWORDS_FILE"
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 3: Remove stale volumes on fresh start
# ---------------------------------------------------------------------------
if [ "$VOLUMES_EXIST" = true ]; then
  # On warm start, still remove stale stateful volumes so rotated passwords take effect
  # But NOT on stop→start — only remove if passwords actually changed.
  # For safety: remove only if --force-build is used or if this is clearly a new session.
  # We remove stateful volumes on fresh start (already handled above) and on destroy.
  # On warm start, we keep them so admin passwords remain consistent.
  info "stack_start.sh" "Preserving stateful volumes (warm start)"
fi

# ---------------------------------------------------------------------------
# Step 4: Ensure TLS certificates
# ---------------------------------------------------------------------------
info "stack_start.sh" "Ensuring TLS certificates..."
"$ROOT_DIR/scripts/create_certs.sh" 2>/dev/null || {
  warning "stack_start.sh" "Certificate generation failed; certs may already exist"
}

# ---------------------------------------------------------------------------
# Step 5: Build images if requested
# ---------------------------------------------------------------------------
if [ "$FORCE_BUILD" = true ]; then
  info "stack_start.sh" "Building images (--force-build)..."
  docker compose build --no-cache || {
    error "stack_start.sh" "Image build failed"
    exit 1
  }
elif [ "$NO_BUILD" != true ]; then
  info "stack_start.sh" "Building images..."
  docker compose build || {
    error "stack_start.sh" "Image build failed"
    exit 1
  }
else
  info "stack_start.sh" "Skipping image build (--no-build)"
fi

# ---------------------------------------------------------------------------
# Step 6: Bring up all containers
# ---------------------------------------------------------------------------
info "stack_start.sh" "Starting containers..."
export COMPOSE_PROGRESS=plain
docker_compose up -d --force-recreate --remove-orphans || {
  error "stack_start.sh" "docker compose up failed"
  exit 1
}

# ---------------------------------------------------------------------------
# Step 7: Wait for critical services
# ---------------------------------------------------------------------------
info "stack_start.sh" "Waiting for Keycloak..."
wait_for_compose_service_healthy keycloak "Keycloak" 120 5 || {
  error "stack_start.sh" "Keycloak did not become healthy"
  docker_compose logs --no-color --tail 80 keycloak || true
  exit 1
}

info "stack_start.sh" "Waiting for Postgres..."
wait_for_compose_service_healthy db "Postgres" 120 5 || {
  error "stack_start.sh" "Postgres did not become healthy"
  docker_compose logs --no-color --tail 80 db || true
  exit 1
}

success "stack_start.sh" "Stack started"
