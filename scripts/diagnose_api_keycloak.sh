#!/usr/bin/env bash

# Purpose: Diagnose API container connectivity to Keycloak.
#
# What it does:
# - Inspects compose services and relevant environment variables.
# - Fetches OpenID configuration and attempts a token POST.
# - Prints diagnostics without failing the whole run on individual step errors.
#
# Version: 1.0
# Last modified: 2026-04-07

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
init_root_env_file "$ROOT_DIR"

my_name="diagnose_api_keycloak.sh"

if [ ! -f "$ROOT_ENV_FILE" ]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

api_ct="$(docker ps --filter 'label=com.docker.compose.service=api' --filter 'status=running' --format '{{.ID}}' | head -1 || true)"
if [[ -z "$api_ct" ]]; then
  error "$my_name" "API container not found"
  exit 1
fi

run() {
  printf "\n--- %s ---\n" "$1"
  shift
  # run command but don't exit on error
  if ! eval "$*"; then
    printf "(command exited with non-zero status)\n"
  fi
}

run "docker version" docker version
run "docker ps api" docker ps --filter 'label=com.docker.compose.service=api' --filter 'status=running' || true

run "env (KEYCLOAK vars) inside api" docker exec -T "$api_ct" sh -lc 'env | grep KEYCLOAK || true'
run "which curl inside api" docker exec -T "$api_ct" sh -lc 'which curl || echo "curl missing"'

run "openid-configuration from api container" docker exec -T "$api_ct" sh -lc 'curl -vS http://keycloak:8080/realms/master/.well-known/openid-configuration || true'

# Try token POST using env inside container (if available)
run "token POST from api container (password grant)" docker exec -T "$api_ct" sh -lc "curl -vS -X POST http://keycloak:8080/realms/master/protocol/openid-connect/token -d 'grant_type=password&client_id=admin-cli&username=$$KEYCLOAK_SYSTEM_ADMIN_USERNAME&password=$$KEYCLOAK_SYSTEM_ADMIN_PASSWORD' || true"

printf "\nDone. If any step failed, inspect container logs with docker logs and check Keycloak logs likewise.\n"
