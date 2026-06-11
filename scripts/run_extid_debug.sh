#!/usr/bin/env bash
set -euo pipefail


# Purpose: Debug Keycloak token flows and external_id patch generation in-network.
#
# What it does:
# - Runs password-grant and client-credentials token requests inside the compose network.
# - Starts a short-lived debug container to run generate_external_id_patch.py.
# - Writes logs and points to the generated SQL output.
#
# Version: 1.0
# Last modified: 2026-04-07

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$REPO_ROOT"

source "$REPO_ROOT/scripts/supporting/root_env_file.sh"
init_root_env_file "$REPO_ROOT"

print_usage() {
  printf '%s\n' \
    "Usage: ./scripts/run_extid_debug.sh [OPTIONS]" \
    "" \
    "Canonical env options:" \
    "  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local" \
    "  --env-file PATH          Use an explicit env file" \
    "  -h, --help"
}

if ! consume_root_env_selection_args "$REPO_ROOT" "$@"; then
  print_usage
  exit 1
fi

set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      print_usage
      exit 1
      ;;
  esac
done

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "run_extid_debug.sh" "env file not found: $ROOT_ENV_FILE"
  exit 1
fi

set -a
source "$ROOT_ENV_FILE"
set +a

source "$REPO_ROOT/scripts/supporting/logging.sh"
my_name="run_extid_debug.sh"

NETWORK_DEFAULT="dq-rulebuilder_default"
NETWORK=${KEYCLOAK_NETWORK:-$NETWORK_DEFAULT}

info "$my_name" "Using docker network: $NETWORK"
info "$my_name" "Using env file: $ROOT_ENV_FILE"

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  error "$my_name" "docker network '$NETWORK' not found. Start your compose stack first."
  exit 1
fi

info "$my_name" "1) Password grant against 'jaccloud' using KEYCLOAK_SYSTEM_ADMIN_USERNAME/PASSWORD"
docker run --rm --network "$NETWORK" --env-file "$ROOT_ENV_FILE" curlimages/curl:8.7.1 \
  /bin/sh -c 'curl -s -X POST "http://keycloak:8080/realms/jaccloud/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=password" -d "username=$KEYCLOAK_SYSTEM_ADMIN_USERNAME" -d "password=$KEYCLOAK_SYSTEM_ADMIN_PASSWORD" -d "client_id=admin-cli"'

info "$my_name" "2) Password grant against 'master' using KEYCLOAK_ADMIN_USER/PASS"
docker run --rm --network "$NETWORK" --env-file "$ROOT_ENV_FILE" curlimages/curl:8.7.1 \
  /bin/sh -c 'curl -s -X POST "http://keycloak:8080/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=password" -d "username=$KEYCLOAK_ADMIN_USER" -d "password=$KEYCLOAK_ADMIN_PASS" -d "client_id=$KEYCLOAK_ADMIN_ID"'

echo
if grep -q '^KEYCLOAK_CLIENT_SECRET=' "$ROOT_ENV_FILE" 2>/dev/null; then
  info "$my_name" "3) client_credentials against realm in .env (KEYCLOAK_REALM) using KEYCLOAK_CLIENT_ID/KEYCLOAK_CLIENT_SECRET"
  docker run --rm --network "$NETWORK" --env-file "$ROOT_ENV_FILE" curlimages/curl:8.7.1 \
    /bin/sh -c 'curl -s -X POST "http://keycloak:8080/realms/${KEYCLOAK_REALM:-jaccloud}/protocol/openid-connect/token" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "grant_type=client_credentials" -d "client_id=$KEYCLOAK_CLIENT_ID" -d "client_secret=$KEYCLOAK_CLIENT_SECRET"'
else
  warning "$my_name" "Skipping client_credentials test (no KEYCLOAK_CLIENT_SECRET in $ROOT_ENV_FILE)"
fi

info "$my_name" "4) Start persistent debug container that runs the generator (detached)."
info "$my_name" "   Container name: extid-gen-debug"
if docker ps -a --format '{{.Names}}' | grep -q '^extid-gen-debug$'; then
  info "$my_name" "Removing existing container 'extid-gen-debug'"
  docker rm -f extid-gen-debug >/dev/null 2>&1 || true
fi

docker run --name extid-gen-debug --network "$NETWORK" -v "$(pwd)":/work -w /work \
  --env-file "$ROOT_ENV_FILE" -e KEYCLOAK_TOKEN_REALM=${KEYCLOAK_TOKEN_REALM:-jaccloud} -e KEYCLOAK_CLIENT_ID=${KEYCLOAK_CLIENT_ID:-admin-cli} \
  -d python:3.12-slim /bin/sh -c 'python3 scripts/generate_external_id_patch.py || true; sleep 300'

success "$my_name" "Generator container started (detached). Show last 200 lines of logs with: docker logs extid-gen-debug"
info "$my_name" "And check generated SQL at: dq-api/fastapi/migrations/versions/ensure_external_ids.sql"

exit 0
