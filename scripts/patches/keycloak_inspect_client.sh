#!/usr/bin/env bash
set -euo pipefail

# Inspect Keycloak client configuration from the compose network.
# Usage (from repo root):
#   KEYCLOAK_NETWORK=dq-rulebuilder_default KEYCLOAK_HOST=keycloak:8080 \ 
#     ADMIN_USER=admin ADMIN_PASS=admin REALM=jaccloud CLIENT_ID=dq-rules-ui \ 
#     bash scripts/patches/keycloak_inspect_client.sh

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="keycloak_inspect_client.sh"

KEYCLOAK_NETWORK="${KEYCLOAK_NETWORK:-dq-rulebuilder_default}"
KEYCLOAK_HOST="${KEYCLOAK_HOST:-keycloak:8080}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-admin}"
REALM="${REALM:-jaccloud}"
CLIENT_ID="${CLIENT_ID:-dq-rules-ui}"

info "$my_name" "Using network: $KEYCLOAK_NETWORK host: $KEYCLOAK_HOST realm: $REALM client: $CLIENT_ID"

info "$my_name" "Fetching master admin token..."
TOKEN=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -X POST "http://$KEYCLOAK_HOST/realms/master/protocol/openid-connect/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "grant_type=password" -d "username=$ADMIN_USER" -d "password=$ADMIN_PASS" -d 'client_id=admin-cli' | jq -r .access_token)

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  error "$my_name" "failed to obtain master admin token"
  exit 2
fi

info "$my_name" "Token length: $(printf '%s' "$TOKEN" | wc -c)"

info "$my_name" "Listing clients matching clientId=$CLIENT_ID in realm $REALM..."
docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients?clientId=$CLIENT_ID" | jq .

CLIENT_UUID=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients?clientId=$CLIENT_ID" | jq -r '.[0].id')

if [ -z "$CLIENT_UUID" ] || [ "$CLIENT_UUID" = "null" ]; then
  error "$my_name" "client not found or multiple results returned"
  exit 3
fi

info "$my_name" "Client UUID: $CLIENT_UUID"

info "$my_name" "Client details:"
docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients/$CLIENT_UUID" | jq .

info "$my_name" "Client secret (if confidential client):"
docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients/$CLIENT_UUID/client-secret" | jq .

info "$my_name" "Service-account user (if enabled):"
docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients/$CLIENT_UUID/service-account-user" | jq .

# If service-account user exists, print its realm role mappings
SERVICE_USER_ID=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients/$CLIENT_UUID/service-account-user" | jq -r .id)

if [ -n "$SERVICE_USER_ID" ] && [ "$SERVICE_USER_ID" != "null" ]; then
  info "$my_name" "Service-account user id: $SERVICE_USER_ID"
  info "$my_name" "Realm role mappings for service-account user:"
  docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
    -s -H "Authorization: Bearer $TOKEN" \
    "http://$KEYCLOAK_HOST/admin/realms/$REALM/users/$SERVICE_USER_ID/role-mappings/realm" | jq .
else
  warning "$my_name" "No service-account user found for client $CLIENT_ID"
fi

exit 0
