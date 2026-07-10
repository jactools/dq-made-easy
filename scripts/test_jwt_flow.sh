#!/usr/bin/env bash
set -euo pipefail


# Purpose: Test JWT authentication end-to-end through Keycloak and Kong.
#
# What it does:
# - Reads SSO settings from the API app-config.
# - Obtains a JWT from Keycloak using password grant.
# - Calls API routes directly and via Kong with/without JWT.
#
# Version: 1.1
# Last modified: 2026-04-22
# Changelog:
# - 1.1 (2026-04-22): Switched JWT payload decoding from shell `base64` flags to a portable python3 helper.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/env/selection.sh"
init_root_env_file "$ROOT_DIR"
source_selected_root_env_file

my_name="test_jwt_flow.sh"

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [ -f "$KONG_CA_CERT" ] && [ -z "${CURL_CA_BUNDLE:-}" ]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

KEYCLOAK_BASE_URL="${KEYCLOAK_LOCAL_URL:-${KEYCLOAK_PUBLIC_URL:-https://keycloak.jac.dot:9444}}"
KONG_LOCAL_URL="${KONG_LOCAL_URL:-${KONG_PUBLIC_URL:-https://kong.jac.dot:9443}}"
API_URL="http://localhost:4010"

APPCFG=$(curl -sS "${API_URL}/api/system/v1/app-config" 2>/dev/null || echo "")
SSO_ENABLED=$(echo "$APPCFG" | jq -r '.ssoEnabled // false' 2>/dev/null || echo "false")
SSO_ISSUER=$(echo "$APPCFG" | jq -r '.ssoIssuer // empty' 2>/dev/null || echo "")
SSO_CLIENT_ID=$(echo "$APPCFG" | jq -r '.ssoClientId // empty' 2>/dev/null || echo "")

if [ "$SSO_ENABLED" = "true" ] && [ -n "$SSO_ISSUER" ]; then
  KEYCLOAK_BASE_URL=$(echo "$SSO_ISSUER" | sed -E 's#/realms/.*$##')
fi

if [ -z "$SSO_CLIENT_ID" ]; then
  SSO_CLIENT_ID="dq-rules-ui"
fi

TOKEN_ENDPOINT="${KEYCLOAK_BASE_URL}/realms/jaccloud/protocol/openid-connect/token"
if [ -n "$SSO_ISSUER" ]; then
  TOKEN_ENDPOINT="${SSO_ISSUER%/}/protocol/openid-connect/token"
fi

info "$my_name" "=============================================="
info "$my_name" "Kong + Keycloak JWT End-to-End Test"
info "$my_name" "=============================================="
info "$my_name" "Using issuer: ${SSO_ISSUER:-${KEYCLOAK_BASE_URL}/realms/jaccloud}"
info "$my_name" "Using client: ${SSO_CLIENT_ID}"

# Step 1: Get token from Keycloak
info "$my_name" ""
info "$my_name" "Step 1: Getting JWT token from Keycloak..."
TOKEN_RESPONSE=$(curl -s -X POST "${TOKEN_ENDPOINT}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=${SSO_CLIENT_ID}&username=dq-admin@jaccloud.nl&password=password&grant_type=password")

TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
  error "$my_name" "Failed to get token"
  info "$my_name" "Response: $TOKEN_RESPONSE"
  exit 1
fi

success "$my_name" "Token obtained (${#TOKEN} chars)"

decode_base64_json() {
  local segment="$1"
  local normalized="$segment"

  normalized="${normalized//-/+}"
  normalized="${normalized//_/\/}"
  while (( ${#normalized} % 4 != 0 )); do
    normalized="${normalized}="
  done

  if ! command -v python3 >/dev/null 2>&1; then
    return 1
  fi

  python3 - "$normalized" <<'PY'
import base64
import binascii
import sys

try:
    decoded = base64.b64decode(sys.argv[1])
except (binascii.Error, ValueError):
    raise SystemExit(1)

sys.stdout.write(decoded.decode("utf-8"))
PY
}

# Step 2: Decode and display token payload
info "$my_name" ""
info "$my_name" "Step 2: Token payload (decoded):"
decode_base64_json "$(echo "$TOKEN" | cut -d'.' -f2)" 2>/dev/null | jq . 2>/dev/null || echo "(Could not decode - that's OK)"

# Step 3: Test API directly with token
info "$my_name" ""
info "$my_name" "Step 3: Testing API directly with JWT token..."
DIRECT_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "${API_URL}/api/rulebuilder/v1/rules" \
  -H "Authorization: Bearer $TOKEN")

HTTP_CODE=$(echo "$DIRECT_RESPONSE" | tail -1)
BODY=$(echo "$DIRECT_RESPONSE" | sed '$d')

info "$my_name" "HTTP Status: $HTTP_CODE"
if [ "$HTTP_CODE" = "200" ]; then
  success "$my_name" "Direct API call successful"
  echo "$BODY" | jq '.[] | {id, name}' | head -4
else
  error "$my_name" "Direct API returned $HTTP_CODE"
fi

# Step 3b: Verify Kong blocks unauthenticated calls
info "$my_name" ""
info "$my_name" "Step 3b: Verifying Kong rejects unauthenticated /rulebuilder/v1 calls..."
KONG_NO_AUTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X GET "${KONG_LOCAL_URL}/rulebuilder/v1/rules")
if [ "$KONG_NO_AUTH_CODE" = "401" ]; then
  success "$my_name" "Kong enforces JWT (unauthenticated request rejected with 401)"
else
  error "$my_name" "Expected 401 without JWT, got $KONG_NO_AUTH_CODE"
fi

# Step 4: Test through Kong with token
info "$my_name" ""
info "$my_name" "Step 4: Testing API through Kong proxy with JWT token..."
KONG_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "${KONG_LOCAL_URL}/rulebuilder/v1/rules" \
  -H "Authorization: Bearer $TOKEN")

HTTP_CODE=$(echo "$KONG_RESPONSE" | tail -1)
BODY=$(echo "$KONG_RESPONSE" | sed '$d')

info "$my_name" "HTTP Status: $HTTP_CODE"
if [ "$HTTP_CODE" = "200" ]; then
  success "$my_name" "Kong proxy call successful with JWT"
  echo "$BODY" | jq '.[] | {id, name}' | head -4
else
  error "$my_name" "Kong returned $HTTP_CODE"
  info "$my_name" "Response: $BODY"
fi

# Step 5: Test Kong health endpoint with token
info "$my_name" ""
info "$my_name" "Step 5: Testing health endpoint through Kong with JWT..."
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "${KONG_LOCAL_URL}/system/v1/health" \
  -H "Authorization: Bearer $TOKEN")

HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -1)
BODY=$(echo "$HEALTH_RESPONSE" | sed '$d')

info "$my_name" "HTTP Status: $HTTP_CODE"
if [ "$HTTP_CODE" = "200" ]; then
  success "$my_name" "Health endpoint accessible with JWT"
  echo "$BODY" | jq .
else
  info "$my_name" "Note: Health endpoint returned $HTTP_CODE (may not require auth)"
fi

# Step 6: Compare headers with and without JWT
info "$my_name" ""
info "$my_name" "Step 6: Comparing response headers..."
info "$my_name" "Without JWT:"
curl -s -I "${KONG_LOCAL_URL}/rulebuilder/v1/rules" 2>/dev/null | grep -E "X-RateLimit|X-Kong" | head -3

info "$my_name" ""
info "$my_name" "With JWT:"
curl -s -I "${KONG_LOCAL_URL}/rulebuilder/v1/rules" -H "Authorization: Bearer $TOKEN" 2>/dev/null | grep -E "X-RateLimit|X-Kong" | head -3

info "$my_name" ""
info "$my_name" "=============================================="
success "$my_name" "JWT End-to-End Testing Complete"
info "$my_name" "=============================================="
