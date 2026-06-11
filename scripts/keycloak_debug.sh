#!/usr/bin/env bash
set -euo pipefail


# Purpose: Debug Keycloak token/client-secret flows and persist output.
#
# What it does:
# - Obtains an admin token and inspects a client by clientId.
# - Fetches client secret when confidential.
# - Attempts token flows and writes verbose output to tmp/keycloak-debug.log.
#
# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="keycloak_debug.sh"

LOG=tmp/keycloak-debug.log
mkdir -p "$(dirname "$LOG")"
: > "$LOG"

KC_BASE=${KEYCLOAK_LOCAL_URL:-}
KC_REALM=${KEYCLOAK_REALM:-}
KC_USER=${KEYCLOAK_USERNAME:-}
KC_PASS=${KEYCLOAK_PASSWORD:-}
CLIENT_ID=${KEYCLOAK_CLIENT_ID:-dq-rulebuilder}

if [ -z "$KC_BASE" ] || [ -z "$KC_REALM" ] || [ -z "$KC_USER" ] || [ -z "$KC_PASS" ]; then
  error "$my_name" "please export KEYCLOAK_LOCAL_URL, KEYCLOAK_REALM, KEYCLOAK_USERNAME, KEYCLOAK_PASSWORD" 2>&1 | tee -a "$LOG" || true
  exit 2
fi

info "$my_name" "Starting Keycloak debug run" | tee -a "$LOG"
info "$my_name" "KC_BASE=$KC_BASE REALM=$KC_REALM CLIENT_ID=$CLIENT_ID" | tee -a "$LOG"

info "$my_name" "[STEP] Obtain admin token from master realm (admin-cli)" | tee -a "$LOG"
curl -v -sS -X POST "$KC_BASE/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=admin-cli&username=$KC_USER&password=$KC_PASS" 2>>"$LOG" | tee -a "$LOG" | jq . > /dev/null || true

ADMIN_TOKEN=$(curl -sS -X POST "$KC_BASE/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=admin-cli&username=$KC_USER&password=$KC_PASS" | jq -r .access_token)

if [ -z "$ADMIN_TOKEN" ] || [ "$ADMIN_TOKEN" = "null" ]; then
  error "$my_name" "failed to obtain admin token (check credentials). See $LOG for details." 2>&1 | tee -a "$LOG" || true
  exit 3
fi

success "$my_name" "Obtained admin token" | tee -a "$LOG"

info "$my_name" "[STEP] Find client UUID for clientId=${CLIENT_ID}" | tee -a "$LOG"
CLIENTS_JSON=$(curl -sS -H "Authorization: Bearer $ADMIN_TOKEN" "$KC_BASE/admin/realms/$KC_REALM/clients?clientId=$CLIENT_ID")
printf '%s\n' "$CLIENTS_JSON" | tee -a "$LOG" | jq . > /dev/null || true
CLIENT_UUID=$(echo "$CLIENTS_JSON" | jq -r '.[0].id')

if [ -z "$CLIENT_UUID" ] || [ "$CLIENT_UUID" = "null" ]; then
  error "$my_name" "client '$CLIENT_ID' not found in realm '$KC_REALM'. Check clientId." 2>&1 | tee -a "$LOG" || true
  exit 4
fi

success "$my_name" "client UUID: $CLIENT_UUID" | tee -a "$LOG"

info "$my_name" "[STEP] Fetch client secret (if confidential)" | tee -a "$LOG"
CLIENT_SECRET_JSON=$(curl -sS -H "Authorization: Bearer $ADMIN_TOKEN" "$KC_BASE/admin/realms/$KC_REALM/clients/$CLIENT_UUID/client-secret")
printf '%s\n' "$CLIENT_SECRET_JSON" | tee -a "$LOG" | jq . > /dev/null || true
CLIENT_SECRET=$(printf '%s' "$CLIENT_SECRET_JSON" | jq -r .value)

if [ -n "$CLIENT_SECRET" ] && [ "$CLIENT_SECRET" != "null" ]; then
  success "$my_name" "client secret retrieved" | tee -a "$LOG"
else
  warning "$my_name" "no client secret present (client may be public)." | tee -a "$LOG"
  CLIENT_SECRET=""
fi

info "$my_name" "[STEP] Attempt resource-owner token exchange using client credentials" | tee -a "$LOG"
if [ -n "$CLIENT_SECRET" ]; then
  curl -v -sS -X POST "$KC_BASE/realms/$KC_REALM/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=password&username=$KC_USER&password=$KC_PASS&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET" 2>>"$LOG" | tee -a "$LOG" | jq . > /dev/null || true
else
  # try admin-cli as fallback attempt to verify password flow (will show server message)
  curl -v -sS -X POST "$KC_BASE/realms/$KC_REALM/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=password&username=$KC_USER&password=$KC_PASS&client_id=admin-cli" 2>>"$LOG" | tee -a "$LOG" | jq . > /dev/null || true
fi

info "$my_name" "[RESULT] Debug log written to $LOG" | tee -a "$LOG"
info "$my_name" "You can open it with: less $LOG" | tee -a "$LOG"

exit 0
