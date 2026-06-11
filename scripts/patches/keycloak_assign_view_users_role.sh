#!/usr/bin/env bash
set -euo pipefail

# Assign the realm-management 'view-users' client role to the service-account user
# for a confidential client (idempotent).
# Usage:
#   KEYCLOAK_NETWORK=dq-rulebuilder_default KEYCLOAK_HOST=keycloak:8080 \
#     ADMIN_USER=admin ADMIN_PASS=admin REALM=jaccloud CLIENT_ID=dq-rules-ui \
#     bash scripts/patches/keycloak_assign_view_users_role.sh

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="keycloak_assign_view_users_role.sh"

KEYCLOAK_NETWORK="${KEYCLOAK_NETWORK:-dq-rulebuilder_default}"
KEYCLOAK_HOST="${KEYCLOAK_HOST:-keycloak:8080}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-admin}"
REALM="${REALM:-jaccloud}"
CLIENT_ID="${CLIENT_ID:-dq-rules-ui}"

info "$my_name" "Using network: $KEYCLOAK_NETWORK host: $KEYCLOAK_HOST realm: $REALM client: $CLIENT_ID"

info "$my_name" "Obtaining master admin token..."
MASTER_TOKEN=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -X POST "http://$KEYCLOAK_HOST/realms/master/protocol/openid-connect/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "grant_type=password" -d "username=$ADMIN_USER" -d "password=$ADMIN_PASS" -d 'client_id=admin-cli' | jq -r .access_token)

if [ -z "$MASTER_TOKEN" ] || [ "$MASTER_TOKEN" = "null" ]; then
  error "$my_name" "failed to obtain master admin token"
  exit 2
fi

info "$my_name" "Resolving client UUID for $CLIENT_ID in realm $REALM..."
CLIENT_UUID=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $MASTER_TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients?clientId=$CLIENT_ID" | jq -r '.[0].id')

if [ -z "$CLIENT_UUID" ] || [ "$CLIENT_UUID" = "null" ]; then
  error "$my_name" "client $CLIENT_ID not found in realm $REALM"
  exit 3
fi

info "$my_name" "Client UUID: $CLIENT_UUID"

info "$my_name" "Resolving service-account user id for client..."
SERVICE_USER_ID=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $MASTER_TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients/$CLIENT_UUID/service-account-user" | jq -r .id)

if [ -z "$SERVICE_USER_ID" ] || [ "$SERVICE_USER_ID" = "null" ]; then
  error "$my_name" "service-account user not found for client $CLIENT_ID"
  exit 4
fi

info "$my_name" "Service-account user id: $SERVICE_USER_ID"

info "$my_name" "Resolving realm-management client UUID..."
RM_CLIENT_UUID=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $MASTER_TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients?clientId=realm-management" | jq -r '.[0].id')

if [ -z "$RM_CLIENT_UUID" ] || [ "$RM_CLIENT_UUID" = "null" ]; then
  error "$my_name" "realm-management client not found in realm $REALM"
  exit 5
fi

info "$my_name" "realm-management client UUID: $RM_CLIENT_UUID"

info "$my_name" "Resolving 'view-users' role id under realm-management..."
ROLE_ID=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $MASTER_TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/clients/$RM_CLIENT_UUID/roles" | jq -r '.[] | select(.name=="view-users") .id')

if [ -z "$ROLE_ID" ] || [ "$ROLE_ID" = "null" ]; then
  error "$my_name" "role 'view-users' not found under realm-management"
  exit 6
fi

info "$my_name" "role id: $ROLE_ID"

info "$my_name" "Checking existing client role mappings for service-account user..."
EXISTING=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $MASTER_TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/users/$SERVICE_USER_ID/role-mappings/clients/$RM_CLIENT_UUID" | jq -r '.[]?.name' || true)

if echo "$EXISTING" | grep -qx "view-users"; then
  success "$my_name" "Service-account user already has realm-management:view-users role — nothing to do."
  exit 0
fi

info "$my_name" "Assigning realm-management:view-users role to service-account user..."
PAYLOAD="[{\"id\":\"$ROLE_ID\",\"name\":\"view-users\"}]"

docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -X POST -H "Authorization: Bearer $MASTER_TOKEN" -H "Content-Type: application/json" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/users/$SERVICE_USER_ID/role-mappings/clients/$RM_CLIENT_UUID" \
  -d "$PAYLOAD"

info "$my_name" "Assigned role; verification:"
docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 \
  -s -H "Authorization: Bearer $MASTER_TOKEN" \
  "http://$KEYCLOAK_HOST/admin/realms/$REALM/users/$SERVICE_USER_ID/role-mappings/clients/$RM_CLIENT_UUID" | jq .

success "$my_name" "Done."
exit 0
