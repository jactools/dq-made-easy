#!/usr/bin/env bash

# Purpose: Check API <-> Keycloak connectivity and token endpoint behavior.
#
# What it does:
# - Inspects the running api container and its Docker network.
# - Probes OpenID configuration and token endpoints.
# - Tails relevant compose logs for troubleshooting.
#
# Version: 1.0
# Last modified: 2026-04-07

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
init_root_env_file "$ROOT_DIR"

my_name="keycloak_connectivity_check.sh"

if [ ! -f "$ROOT_ENV_FILE" ]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

info "$my_name" "--- docker version ---"
docker version || true

info "$my_name" "--- docker image inspect api ---"
docker image inspect api || true

api_ct=$(docker ps --filter "label=com.docker.compose.service=api" --filter 'status=running' --format '{{.ID}}' | head -1 || true)
if [ -z "$api_ct" ]; then
  error "$my_name" "API container not found."
  info "$my_name" "Run: docker ps to see containers."
  exit 1
fi

keycloak_ct=$(docker ps --filter "label=com.docker.compose.service=keycloak" --filter 'status=running' --format '{{.Names}}' | head -1 || true)
if [ -z "$keycloak_ct" ]; then
  error "$my_name" "Keycloak container not found."
  exit 1
fi

info "$my_name" "--- docker ps api ---"
docker ps --filter "label=com.docker.compose.service=api" --filter 'status=running' || true

info "$my_name" "--- api container inspect (Image ID & Networks) ---"
docker inspect --format '{{.Id}} {{.Image}}' "$api_ct" || true
net_name=$(docker inspect --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' "$api_ct" || true)
if [ -z "$net_name" ]; then
  warning "$my_name" "No network found on api container."
else
  info "$my_name" "Detected network: $net_name"
fi

info "$my_name" "--- which curl inside api ---"
docker exec -T "$api_ct" sh -lc 'which curl || echo "curl missing"' || true

info "$my_name" "--- openid-configuration from api container ---"
docker exec -T "$api_ct" sh -lc 'curl -sS http://keycloak:8080/realms/master/.well-known/openid-configuration || echo "failed to fetch openid-configuration"' || true

info "$my_name" "--- token POST from api container (password grant) ---"
docker exec -T "$api_ct" sh -lc 'echo "POSTing token (from api container)"; curl -sS -X POST "http://keycloak:8080/realms/master/protocol/openid-connect/token" -d "grant_type=password&client_id=admin-cli&username=${KEYCLOAK_SYSTEM_ADMIN_USERNAME:-}" -d "password=${KEYCLOAK_SYSTEM_ADMIN_PASSWORD:-}" -w "\nHTTP:%{http_code}\n" || true'

# Temporary curl container -> uses detected network if available
if [ -n "$net_name" ]; then
  info "$my_name" "--- token POST from temporary curl container on network $net_name ---"
  docker run --rm --network "$net_name" curlimages/curl:8.4.0 -sS -X POST \
    "http://keycloak:8080/realms/master/protocol/openid-connect/token" \
    -d "grant_type=password&client_id=admin-cli&username=${KEYCLOAK_SYSTEM_ADMIN_USERNAME:-}" \
    -d "password=${KEYCLOAK_SYSTEM_ADMIN_PASSWORD:-}" -w "\nHTTP:%{http_code}\n" || true
else
  info "$my_name" "--- skipping temporary curl container: no network detected on api container ---"
fi

info "$my_name" "--- docker ps keycloak ---"
docker ps --filter "label=com.docker.compose.service=keycloak" --filter 'status=running' || true

info "$my_name" "--- tail Keycloak logs (last 200 lines) ---"
docker logs --tail 200 "$keycloak_ct" || true

info "$my_name" "--- tail API logs (last 200 lines) ---"
docker logs --tail 200 "$api_ct" || true

info "$my_name" "Done. If token POST fails, check KEYCLOAK_SYSTEM_ADMIN_USERNAME/PASSWORD in your env and Keycloak import status."
