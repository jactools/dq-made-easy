#!/usr/bin/env bash
set -euo pipefail

# One-shot script to reproduce the three checks so command boxes aren't needed.
# Usage: bash scripts/patches/check_keycloak_users.sh

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

echo "1) Rotated client secret (tmp/keycloak_client_secret.txt):"
if [ -f tmp/keycloak_client_secret.txt ]; then
  sed -n '1,120p' tmp/keycloak_client_secret.txt || true
else
  echo "tmp/keycloak_client_secret.txt not found"
fi

echo
echo "2) Realm users in dq-keycloak/jaccloud-realm.json (first user + count):"
if command -v jq >/dev/null 2>&1; then
  jq '.users | length, .users[0]' dq-keycloak/jaccloud-realm.json || true
else
  echo "jq not installed; showing head of file instead:"
  head -n 120 dq-keycloak/jaccloud-realm.json || true
fi

echo
echo "3) Obtain admin token (master realm) and query Keycloak in-network for alice@jaccloud.nl"
KEYCLOAK_NETWORK="${KEYCLOAK_NETWORK:-dq-rulebuilder_default}"
KC_ADMIN_USER="${KEYCLOAK_ADMIN_USER:-admin}"
KC_ADMIN_PASS="${KEYCLOAK_ADMIN_PASS:-admin}"

TOKEN=$(docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 -s -X POST \
  "http://keycloak:8080/realms/master/protocol/openid-connect/token" \
  -d 'grant_type=password' -d 'client_id=admin-cli' -d "username=${KC_ADMIN_USER}" -d "password=${KC_ADMIN_PASS}" | jq -r .access_token 2>/dev/null || true)

if [ -n "$TOKEN" ]; then
  echo "TOKEN length: ${#TOKEN}"
  docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 -s -H "Authorization: Bearer $TOKEN" \
    "http://keycloak:8080/admin/realms/jaccloud/users?email=alice@jaccloud.nl" | jq . || true
else
  echo "Failed to obtain token; showing raw token response for debugging:" 
  docker run --rm --network "$KEYCLOAK_NETWORK" curlimages/curl:8.7.1 -s -X POST \
    "http://keycloak:8080/realms/master/protocol/openid-connect/token" \
    -d 'grant_type=password' -d 'client_id=admin-cli' -d "username=${KC_ADMIN_USER}" -d "password=${KC_ADMIN_PASS}"
fi

echo
echo "Done."
