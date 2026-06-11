#!/usr/bin/env bash
set -euo pipefail

# Verify the service-account user for a confidential client has the
# realm-management 'view-users' client role and test an admin user lookup.
# Usage (example):
# KEYCLOAK_NETWORK=dq-rulebuilder_default KEYCLOAK_HOST=keycloak:8080 \
#   ADMIN_USER=admin ADMIN_PASS=admin REALM=jaccloud \
#   CLIENT_ID=dq-rules-ui CLIENT_SECRET='hW9je...' \
#   EMAIL=jacbeekers@jaccloud.nl \
#   bash scripts/patches/keycloak_verify_service_account.sh

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="keycloak_verify_service_account.sh"

KEYCLOAK_NETWORK="${KEYCLOAK_NETWORK:-dq-rulebuilder_default}"
KEYCLOAK_HOST="${KEYCLOAK_HOST:-keycloak:8080}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-admin}"
REALM="${REALM:-jaccloud}"
CLIENT_ID="${CLIENT_ID:-dq-rules-ui}"
CLIENT_SECRET="${CLIENT_SECRET:-}"
EMAIL="${EMAIL:-jacbeekers@jaccloud.nl}"

if [ -z "$CLIENT_SECRET" ]; then
  error "$my_name" "CLIENT_SECRET must be provided via env CLIENT_SECRET"
  exit 2
fi

info "$my_name" "Using network=$KEYCLOAK_NETWORK host=$KEYCLOAK_HOST realm=$REALM client=$CLIENT_ID"

info "$my_name" "Obtaining master admin token..."
MASTER_TOKEN=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -X POST "http://$KEYCLOAK_HOST/realms/master/protocol/openid-connect/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "grant_type=password" -d "username=$ADMIN_USER" -d "password=$ADMIN_PASS" -d 'client_id=admin-cli' | jq -r .access_token)

if [ -z "$MASTER_TOKEN" ] || [ "$MASTER_TOKEN" = "null" ]; then
  error "$my_name" "failed to obtain master admin token"
  exit 3
fi

info "$my_name" "Resolving client UUID for $CLIENT_ID..."
CLIENT_UUID=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $MASTER_TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients?clientId=$CLIENT_ID" | jq -r '.[0].id')

info "$my_name" "client uuid: $CLIENT_UUID"

info "$my_name" "Resolving service-account user id..."
SERVICE_USER_ID=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $MASTER_TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients/$CLIENT_UUID/service-account-user" | jq -r .id)

info "$my_name" "service-account user id: $SERVICE_USER_ID"

info "$my_name" "Listing realm-level role mappings for service-account user (realm roles):"
docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $MASTER_TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/users/$SERVICE_USER_ID/role-mappings/realm" | jq .

info "$my_name" "Listing client role mappings for realm-management (client roles):"
RM_CLIENT_UUID=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $MASTER_TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients?clientId=realm-management" | jq -r '.[0].id')

info "$my_name" "realm-management client uuid: $RM_CLIENT_UUID"

docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $MASTER_TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/users/$SERVICE_USER_ID/role-mappings/clients/$RM_CLIENT_UUID" | jq .

info "$my_name" "Obtaining token via client_credentials for service-account..."
SERVICE_TOKEN=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -X POST "http://$KEYCLOAK_HOST/realms/$REALM/protocol/openid-connect/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=client_credentials' -d "client_id=$CLIENT_ID" -d "client_secret=$CLIENT_SECRET" | jq -r .access_token)

if [ -z "$SERVICE_TOKEN" ] || [ "$SERVICE_TOKEN" = "null" ]; then
  error "$my_name" "failed to obtain service-account token"
  exit 4
fi

info "$my_name" "Testing admin users search for email=$EMAIL using service-account token..."
HTTP=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 -s -w "%{http_code}" -o /tmp/_kc_body \
  -H "Authorization: Bearer $SERVICE_TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/users?email=$EMAIL")

info "$my_name" "HTTP status: $HTTP"
info "$my_name" "Body:"
docker run --rm -v /tmp:/tmp alpine:3.18 cat /tmp/_kc_body || true

success "$my_name" "Done."
exit 0
