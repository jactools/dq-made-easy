#!/usr/bin/env bash
set -euo pipefail

: "${KEYCLOAK_INTERNAL_URL:=http://keycloak:8080}"
: "${KEYCLOAK_REALM:?Need KEYCLOAK_REALM}"
: "${KEYCLOAK_ADMIN_USER:?Need KEYCLOAK_ADMIN_USER}"
: "${KEYCLOAK_ADMIN_PASS:?Need KEYCLOAK_ADMIN_PASS}"
: "${KEYCLOAK_CLIENT_ID:?Need KEYCLOAK_CLIENT_ID}"
NETWORK="${DOCKER_NETWORK:-dq-rulebuilder_default}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"

echo "Using network: $NETWORK host: ${KEYCLOAK_INTERNAL_URL#http://} realm: $KEYCLOAK_REALM client: $KEYCLOAK_CLIENT_ID"

echo "Fetching master admin token..."
ADMIN_JSON=$(docker run --rm --network "$NETWORK" curlimages/curl:8.4.0 -sS -X POST "$KEYCLOAK_INTERNAL_URL/realms/master/protocol/openid-connect/token" \
  -d "grant_type=password" -d "client_id=admin-cli" -d "username=$KEYCLOAK_ADMIN_USER" -d "password=$KEYCLOAK_ADMIN_PASS")
ADMIN_TOKEN=$(echo "$ADMIN_JSON" | "$PYTHON_RUNNER" --python-bin python3 -c "import sys,json;obj=json.load(sys.stdin);print(obj.get('access_token',''))")

if [ -z "$ADMIN_TOKEN" ]; then
  echo "Failed to get admin token: $ADMIN_JSON"
  exit 1
fi

echo "Listing clients matching clientId=$KEYCLOAK_CLIENT_ID in realm $KEYCLOAK_REALM..."
CLIENTS_JSON=$(docker run --rm --network "$NETWORK" curlimages/curl:8.4.0 -sS -H "Authorization: Bearer $ADMIN_TOKEN" "$KEYCLOAK_INTERNAL_URL/admin/realms/$KEYCLOAK_REALM/clients?clientId=$KEYCLOAK_CLIENT_ID")
CLIENT_ID=$(echo "$CLIENTS_JSON" | "$PYTHON_RUNNER" --python-bin python3 -c "import sys,json;arr=json.load(sys.stdin);print(arr[0].get('id','') if arr else '')")
if [ -z "$CLIENT_ID" ]; then
  echo "Client not found for clientId=$KEYCLOAK_CLIENT_ID"
  echo "$CLIENTS_JSON"
  exit 1
fi

echo "Client UUID: $CLIENT_ID"

echo "Generating new client secret..."
NEW_JSON=$(docker run --rm --network "$NETWORK" curlimages/curl:8.4.0 -sS -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "$KEYCLOAK_INTERNAL_URL/admin/realms/$KEYCLOAK_REALM/clients/$CLIENT_ID/client-secret")
NEW_SECRET=$(echo "$NEW_JSON" | "$PYTHON_RUNNER" --python-bin python3 -c "import sys,json;obj=json.load(sys.stdin);print(obj.get('value',''))")
if [ -z "$NEW_SECRET" ]; then
  echo "Failed to generate new secret: $NEW_JSON"
  exit 1
fi

echo "New secret created for client '$KEYCLOAK_CLIENT_ID':"
echo "$NEW_SECRET"

echo
echo "Run the generator with the new secret like this:"
echo "KEYCLOAK_CLIENT_SECRET='$NEW_SECRET' KEYCLOAK_TOKEN_REALM=$KEYCLOAK_REALM bash scripts/patches/run_generate_external_id_patch.sh"
