#!/usr/bin/env bash
set -euo pipefail


# Purpose: Build the frontend locally and then build the frontend Docker image.
#
# What it does:
# - Verifies Node is available, installs deps, and runs the UI build.
# - Produces a local dist/ for the frontend Docker build.
# - Runs `docker compose build frontend` using the local dist/.
#
# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
init_root_env_file "$ROOT_DIR"

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "local_build_frontend.sh" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ROOT_ENV_FILE"
set +a

# Derive canonical registry variables (including NPM_CONFIG_REGISTRY) from env contract.
source "$ROOT_DIR/scripts/supporting/setup_env.sh"

if [ ! -f "$ROOT_DIR/.npmrc" ]; then
  error "local_build_frontend.sh" "Missing required npm config: $ROOT_DIR/.npmrc"
  exit 1
fi
export NPM_CONFIG_USERCONFIG="$ROOT_DIR/.npmrc"

# Optional: check node version
if command -v node >/dev/null 2>&1; then
  NODE_VER=$(node -v)
  info "local_build_frontend.sh" "Detected node $NODE_VER"
else
  error "local_build_frontend.sh" "node not found in PATH. Install Node 22+ before running this script."
  exit 1
fi

# Build frontend
cd "$ROOT_DIR/dq-ui"
info "local_build_frontend.sh" "Installing dependencies and building frontend (this will update package-lock.json)"
# Prefer `npm install` to regenerate lockfile; run with Node 22 on your machine.
# Use --include=dev to ensure devDependencies (like vite) are installed
npm install --include=dev
npm run build
cd "$ROOT_DIR"

# Build docker image for frontend using local dist
info "local_build_frontend.sh" "Building Docker image for frontend using local dist"
DOCKER_BUILDKIT=1 docker_compose --progress=plain -f "$ROOT_DIR/docker-compose.yml" build frontend

success "local_build_frontend.sh" "Done. If the docker build succeeds, run ./scripts/start_stack.sh to bring up the stack."
