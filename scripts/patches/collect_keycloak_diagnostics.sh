#!/usr/bin/env bash
set -euo pipefail

# Collect Keycloak diagnostics (token response, admin lookups, and container logs)
# Usage:
#   KEYCLOAK_ADMIN_USER=admin KEYCLOAK_ADMIN_PASSWORD=secret \
#     ./scripts/patches/collect_keycloak_diagnostics.sh

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="collect_keycloak_diagnostics.sh"

OUT=tmp/keycloak-diagnostics.txt
mkdir -p tmp

PROJECT_DIR=$(basename "$PWD")
NETWORK="${PROJECT_DIR}_default"
if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  NETWORK=$(docker network ls --format '{{.Name}}' | grep -m1 "$PROJECT_DIR" || true)
fi

' "$NETWORK" > "$OUT"
info "$my_name" "Using network: $NETWORK" | tee -a "$OUT"

if [ -z "${KEYCLOAK_ADMIN_USER:-}" ] || [ -z "${KEYCLOAK_ADMIN_PASSWORD:-}" ]; then
  error "$my_name" "set KEYCLOAK_ADMIN_USER and KEYCLOAK_ADMIN_PASSWORD in environment"
  info "$my_name" "Usage: KEYCLOAK_ADMIN_USER=admin KEYCLOAK_ADMIN_PASSWORD=secret ./scripts/patches/collect_keycloak_diagnostics.sh"
  exit 2
fi

info "$my_name" "--- TOKEN REQUEST (password grant) ---" | tee -a "$OUT"
docker run --rm --network "$NETWORK" curlimages/curl:8.7.1 -v -s -X POST \
  "http://keycloak:8080/realms/jaccloud/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=admin-cli" \
  -d "username=${KEYCLOAK_ADMIN_USER}" \
  -d "password=${KEYCLOAK_ADMIN_PASSWORD}" 2>&1 | tee -a "$OUT"

# Also run a quiet token request to capture only the JSON body for parsing
TOKEN_JSON=$(docker run --rm --network "$NETWORK" curlimages/curl:8.7.1 -s -X POST \
  "http://keycloak:8080/realms/jaccloud/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=admin-cli" \
  -d "username=${KEYCLOAK_ADMIN_USER}" \
  -d "password=${KEYCLOAK_ADMIN_PASSWORD}")

info "$my_name" "--- TOKEN JSON (parsed) ---" | tee -a "$OUT"
printf '%s\n' "$TOKEN_JSON" | tee -a "$OUT"

TOKEN=$(echo "$TOKEN_JSON" | jq -r '.access_token // empty' 2>/dev/null || true)

info "$my_name" "--- LIST REALMS ---" | tee -a "$OUT"
docker run --rm --network "$NETWORK" curlimages/curl:8.7.1 -v -s \
  -H "Authorization: Bearer $TOKEN" "http://keycloak:8080/admin/realms" 2>&1 | tee -a "$OUT" || true

info "$my_name" "--- CLIENT LOOKUP dq-rules-ui ---" | tee -a "$OUT"
docker run --rm --network "$NETWORK" curlimages/curl:8.7.1 -v -s \
  -H "Authorization: Bearer $TOKEN" \
  "http://keycloak:8080/admin/realms/jaccloud/clients?clientId=dq-rules-ui" 2>&1 | tee -a "$OUT" || true

info "$my_name" "--- KEYCLOAK LOGS (last 500 lines) ---" | tee -a "$OUT"
if command -v docker-compose >/dev/null 2>&1; then
  docker-compose logs --no-color --tail=500 keycloak 2>&1 | tee -a "$OUT" || true
else
  docker compose logs --no-color --tail=500 keycloak 2>&1 | tee -a "$OUT" || true
fi

success "$my_name" "Wrote diagnostics to $OUT"
