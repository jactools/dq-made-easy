#!/usr/bin/env bash
set -euo pipefail

# Obtain an admin token from inside the Compose network and idempotently
# convert a client to confidential + enable service account + fetch secret
# and assign a realm role to the service-account user.
#
# Usage examples:
#  KEYCLOAK_ADMIN_USER=admin KEYCLOAK_ADMIN_PASSWORD=secret \
#    ./scripts/patches/keycloak-setup-client.sh --realm jaccloud --client dq-rules-ui --role view-users
#

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="keycloak-setup-client.sh"
REALM=jaccloud
ADMIN_REALM=${ADMIN_REALM:-master}
CLIENT_ID=dq-rules-ui
ROLE_NAME=view-users
GRANT=password

usage(){
  cat <<EOF
Usage: $0 [--realm REALM] [--client CLIENT_ID] [--role ROLE_NAME] [--grant password|client_credentials]

Requires either:
  - password grant: KEYCLOAK_ADMIN_USER and KEYCLOAK_ADMIN_PASSWORD env set
  - client_credentials grant: KEYCLOAK_ADMIN_SECRET env set (client id default 'admin-cli')

Example:
  KEYCLOAK_ADMIN_USER=admin KEYCLOAK_ADMIN_PASSWORD=secret \
    $0 --realm jaccloud --client dq-rules-ui --role view-users

EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --realm) REALM="$2"; shift 2 ;;
    --client) CLIENT_ID="$2"; shift 2 ;;
    --role) ROLE_NAME="$2"; shift 2 ;;
    --grant) GRANT="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) error "$my_name" "Unknown arg: $1"; usage; exit 2 ;;
  esac
done

project_dir=$(basename "$(pwd)")
candidate_network="${project_dir}_default"
if docker network inspect "$candidate_network" >/dev/null 2>&1; then
  NETWORK="$candidate_network"
else
  NETWORK=$(docker network ls --format '{{.Name}}' | grep -m1 "${project_dir}" || true)
fi
if [ -z "${NETWORK}" ]; then
  error "$my_name" "Could not detect a Compose network for project '${project_dir}'."
  docker network ls --format '  {{.ID}}\t{{.Name}}\t{{.Driver}}' >&2
  exit 3
fi

info "$my_name" "Using Docker network: $NETWORK"
KC_HOST=http://keycloak:8080
KC_TOKEN_ENDPOINT="$KC_HOST/realms/${ADMIN_REALM}/protocol/openid-connect/token"

get_token_via_compose() {
  if [ "$GRANT" = "password" ]; then
    if [ -z "${KEYCLOAK_ADMIN_USER:-}" ] || [ -z "${KEYCLOAK_ADMIN_PASSWORD:-}" ]; then
      error "$my_name" "KEYCLOAK_ADMIN_USER and KEYCLOAK_ADMIN_PASSWORD must be set for password grant"
      return 2
    fi
    info "$my_name" "Requesting password grant token from realm '${ADMIN_REALM}' inside Compose network..."
    TOKEN_JSON=$(docker run --rm --network "$NETWORK" curlimages/curl:8.7.1 \
      curl -s -X POST "$KC_TOKEN_ENDPOINT" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "grant_type=password" \
        -d "client_id=admin-cli" \
        -d "username=${KEYCLOAK_ADMIN_USER}" \
        -d "password=${KEYCLOAK_ADMIN_PASSWORD}")
  else
    if [ -z "${KEYCLOAK_ADMIN_SECRET:-}" ]; then
      error "$my_name" "KEYCLOAK_ADMIN_SECRET must be set for client_credentials grant"
      return 2
    fi
    info "$my_name" "Requesting client_credentials token from realm '${ADMIN_REALM}' inside Compose network..."
    TOKEN_JSON=$(docker run --rm --network "$NETWORK" curlimages/curl:8.7.1 \
      curl -s -X POST "$KC_TOKEN_ENDPOINT" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "grant_type=client_credentials" \
        -d "client_id=admin-cli" \
        -d "client_secret=${KEYCLOAK_ADMIN_SECRET}")
  fi
  ADMIN_TOKEN=$(echo "$TOKEN_JSON" | jq -r '.access_token // empty') || true
  if [ -z "${ADMIN_TOKEN}" ]; then
    error "$my_name" "Failed to obtain admin token; response:"
    info "$my_name" "$TOKEN_JSON"
    return 3
  fi
  success "$my_name" "Obtained admin token."
}

info "$my_name" "Obtaining admin token..."
get_token_via_compose

info "$my_name" "Using admin token to configure client '${CLIENT_ID}' in realm '${REALM}'"
KC_HOST_LOCAL=http://localhost:8080

# find client uuid (handle unexpected responses)
CLIENT_SEARCH=$(curl -sS -H "Authorization: Bearer ${ADMIN_TOKEN}" "${KC_HOST_LOCAL}/admin/realms/${REALM}/clients?clientId=${CLIENT_ID}")

CLIENT_UUID=$(echo "$CLIENT_SEARCH" | jq -r 'if type=="array" then (.[0].id // "") elif type=="object" and (.id? // empty) != "" then (.id) else "" end') || true
if [ -z "$CLIENT_UUID" ]; then
  error "$my_name" "failed to resolve client UUID for '${CLIENT_ID}' in realm '${REALM}'. Response from Keycloak:"
  info "$my_name" "$CLIENT_SEARCH"
  exit 4
fi
info "$my_name" "Found client UUID: $CLIENT_UUID"

# fetch client JSON, update fields
CLIENT_JSON=$(curl -sS -H "Authorization: Bearer ${ADMIN_TOKEN}" "${KC_HOST_LOCAL}/admin/realms/${REALM}/clients/${CLIENT_UUID}")
UPDATED_JSON=$(echo "$CLIENT_JSON" | jq '.serviceAccountsEnabled=true | .publicClient=false | .clientAuthenticatorType="client-secret"')

info "$my_name" "Updating client settings (service account + confidential)"
curl -sS -X PUT -H "Authorization: Bearer ${ADMIN_TOKEN}" -H "Content-Type: application/json" \
  --data "$UPDATED_JSON" "${KC_HOST_LOCAL}/admin/realms/${REALM}/clients/${CLIENT_UUID}"

info "$my_name" "Creating/fetching client secret"
SECRET_JSON=$(curl -sS -X POST -H "Authorization: Bearer ${ADMIN_TOKEN}" "${KC_HOST_LOCAL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/client-secret")
CLIENT_SECRET=$(echo "$SECRET_JSON" | jq -r '.value // empty')
info "$my_name" "Client secret: $CLIENT_SECRET"

info "$my_name" "Retrieving service-account user id"
SA_USER_JSON=$(curl -sS -H "Authorization: Bearer ${ADMIN_TOKEN}" "${KC_HOST_LOCAL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/service-account-user")
SA_USER_ID=$(echo "$SA_USER_JSON" | jq -r '.id // empty')
if [ -z "$SA_USER_ID" ]; then
  error "$my_name" "Failed to get service-account user id"
  exit 5
fi
info "$my_name" "Service-account user id: $SA_USER_ID"

info "$my_name" "Fetching role '${ROLE_NAME}' object"
ROLE_JSON=$(curl -sS -H "Authorization: Bearer ${ADMIN_TOKEN}" "${KC_HOST_LOCAL}/admin/realms/${REALM}/roles/${ROLE_NAME}" || true)

# If Keycloak returned an error object (e.g. {"error":...}) or empty/null, try to create the role
if [ -z "$ROLE_JSON" ] || [ "$ROLE_JSON" = "null" ] || echo "$ROLE_JSON" | jq -e 'has("error")' >/dev/null 2>&1; then
  error "$my_name" "Role '${ROLE_NAME}' not found or returned error: ${ROLE_JSON}"
  info "$my_name" "Attempting to create role '${ROLE_NAME}' in realm '${REALM}'..."
  create_resp=$(curl -sS -o /dev/null -w "%{http_code}" -X POST -H "Authorization: Bearer ${ADMIN_TOKEN}" -H "Content-Type: application/json" \
    --data "{\"name\":\"${ROLE_NAME}\"}" "${KC_HOST_LOCAL}/admin/realms/${REALM}/roles" || true)
  if [ "$create_resp" = "201" ] || [ "$create_resp" = "204" ] || [ "$create_resp" = "0" ]; then
    success "$my_name" "Role '${ROLE_NAME}' created (HTTP $create_resp)."
  else
    warning "$my_name" "role create returned HTTP $create_resp (may already exist or creation failed). Continuing to fetch role object."
  fi
  ROLE_JSON=$(curl -sS -H "Authorization: Bearer ${ADMIN_TOKEN}" "${KC_HOST_LOCAL}/admin/realms/${REALM}/roles/${ROLE_NAME}" || true)
fi

if [ -z "$ROLE_JSON" ] || [ "$ROLE_JSON" = "null" ] || echo "$ROLE_JSON" | jq -e 'has("error")' >/dev/null 2>&1; then
  error "$my_name" "could not retrieve role '${ROLE_NAME}' after create attempt. Response: $ROLE_JSON"
  exit 6
fi

info "$my_name" "Assigning realm role '${ROLE_NAME}' to service-account user (id: $SA_USER_ID)"
curl -sS -X POST -H "Authorization: Bearer ${ADMIN_TOKEN}" -H "Content-Type: application/json" \
  --data "[$ROLE_JSON]" "${KC_HOST_LOCAL}/admin/realms/${REALM}/users/${SA_USER_ID}/role-mappings/realm"

info "$my_name" ""
success "$my_name" "Done. Client '${CLIENT_ID}' is confidential, service-account enabled, secret printed above, and role '${ROLE_NAME}' mapped."
