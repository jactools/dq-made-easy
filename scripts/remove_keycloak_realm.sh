#!/usr/bin/env bash
set -euo pipefail


# Purpose: Delete an entire realm from Keycloak.
#
# What it does:
# - Authenticates to Keycloak as admin (password grant).
# - Issues a realm deletion request via the admin API.
# - Fails fast if KEYCLOAK_PUBLIC_URL is not configured.
#
# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
set_log_level DEBUG
source "$ROOT_DIR/.env"
source "$ROOT_DIR/scripts/supporting/setup_env.sh"
my_name="remove_keycloak_realm.sh"

REALM="${1}"

# Require a full public URL; do NOT fall back to host-only variants.
if [ -n "${KEYCLOAK_PUBLIC_URL:-}" ]; then
  KEYCLOAK_PUBLIC_BASE="${KEYCLOAK_PUBLIC_URL%/}"
else
  echo "KEYCLOAK_PUBLIC_URL is not set; aborting to avoid fallback behavior."
  exit 1
fi

# Authenticate and get admin token
TOKEN=$(curl -s -X POST "$KEYCLOAK_PUBLIC_BASE/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=admin-cli&username=${KEYCLOAK_SYSTEM_ADMIN_USERNAME}&password=${KEYCLOAK_SYSTEM_ADMIN_PASSWORD}&grant_type=password" \
  | jq -r '.access_token')

if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  echo "Failed to get admin token from Keycloak."
  exit 1
fi

echo "Authenticated to Keycloak at $KEYCLOAK_PUBLIC_BASE. Deleting realm: $REALM ..."
curl -s -X DELETE "$KEYCLOAK_PUBLIC_BASE/admin/realms/$REALM" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.message // "Realm deleted successfully or did not exist."'

echo "Done."
