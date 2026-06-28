#!/bin/bash
set -e


# Purpose: Create or update the Keycloak realm and OIDC clients for the stack.
#
# What it does:
# - Loads repo env and realm JSON payload.
# - Obtains an admin token from Keycloak.
# - Applies realm/client configuration needed for Kong OIDC integration.
#
# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/.env"
source "$ROOT_DIR/scripts/supporting/setup_env.sh"

source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="setup_keycloak_realm.sh"

REALM_FILE=${ROOT_DIR}/dq-keycloak/${KEYCLOAK_REALM}-realm.json

info "$my_name" "Setting up Keycloak realm for Kong OIDC integration..."
KONG_OIDC_REDIRECT_BASE="${OIDC_REDIRECT_BASE_URL:-${KONG_PUBLIC_URL:-}}"
if [ -z "$KONG_OIDC_REDIRECT_BASE" ]; then
  error "$my_name" "OIDC_REDIRECT_BASE_URL or KONG_PUBLIC_URL must be set; aborting to avoid fallback behavior."
  exit 1
fi

# working in the python module:
# kc_base = os.environ.get("SSO_INTERNAL_ISSUER")
# kc_realm = os.environ.get("KEYCLOAK_REALM")
# kc_token_realm = os.environ.get("KEYCLOAK_TOKEN_REALM", "master")
# kc_user = os.environ.get("KEYCLOAK_SYSTEM_ADMIN_USERNAME")
# kc_pass = os.environ.get("KEYCLOAK_SYSTEM_ADMIN_PASSWORD")
# kc_client = os.environ.get("KEYCLOAK_MASTER_CLIENT_ID", "admin-cli")
# kc_client_secret = None

# 1. Get admin token
# Require a full public URL for Keycloak; do not fall back to host-only vars.
if [ -z "${KEYCLOAK_PUBLIC_URL:-}" ]; then
  error "$my_name" "KEYCLOAK_PUBLIC_URL is not set; aborting to avoid fallback behavior."
  exit 1
fi
KEYCLOAK_PUBLIC_BASE="${KEYCLOAK_PUBLIC_URL%/}"

info "$my_name" "1. Getting admin token from Keycloak using ${KEYCLOAK_PUBLIC_BASE} and realm ${KEYCLOAK_TOKEN_REALM}..."
TOKEN=$(curl -s -X POST "${KEYCLOAK_PUBLIC_BASE}/realms/${KEYCLOAK_TOKEN_REALM}/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=${KEYCLOAK_MASTER_CLIENT_ID:-admin-cli}&username=${KEYCLOAK_SYSTEM_ADMIN_USERNAME}&password=${KEYCLOAK_SYSTEM_ADMIN_PASSWORD}&grant_type=password" \
  | jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" == "null" ]; then
  error "$my_name" "Failed to get admin token from Keycloak. Check your .env file for correct Keycloak credentials and URL."
  error "$my_name" "env vars used: KEYCLOAK_PUBLIC_URL, KEYCLOAK_TOKEN_REALM, KEYCLOAK_MASTER_CLIENT_ID, KEYCLOAK_SYSTEM_ADMIN_USERNAME, KEYCLOAK_SYSTEM_ADMIN_PASSWORD"
  exit 1
fi
info "$my_name" "✓ Admin token obtained"

# 2. Create realm
info "$my_name" "2. Creating ${KEYCLOAK_REALM} realm..."
REALM_RESPONSE=$(curl -s -X POST "${KEYCLOAK_PUBLIC_BASE}/admin/realms" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @"${REALM_FILE}")

info "$my_name" "Realm creation response: $REALM_RESPONSE"

# if echo "$REALM_RESPONSE" | jq -e '.realm' > /dev/null 2>&1; then
#   info "$my_name" "✓ Realm created successfully"
# elif echo "$REALM_RESPONSE" | grep -q "already exists"; then
#   info "$my_name" "✓ Realm already exists"
# else
#   error "$my_name" "Failed to create realm: $REALM_RESPONSE"
#   exit 1
# fi

# 3. Add Kong client to realm (for OIDC)
info "$my_name" "3. Creating Kong OIDC client..."
KONG_CLIENT=$(curl -s -X POST "${KEYCLOAK_PUBLIC_BASE}/admin/realms/${KEYCLOAK_REALM}/clients" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"clientId\": \"dq-made-easy-kong\",
    \"name\": \"Kong Gateway\",
    \"description\": \"Kong Gateway OIDC Client\",
    \"enabled\": true,
    \"clientAuthenticatorType\": \"client-secret\",
    \"publicClient\": false,
    \"protocol\": \"openid-connect\",
    \"redirectUris\": [
      \"${KONG_OIDC_REDIRECT_BASE}/v1/*\"
    ],
    \"webOrigins\": ${CORS_ALLOWED_ORIGINS},
    \"directAccessGrantsEnabled\": false,
    \"standardFlowEnabled\": true,
    \"implicitFlowEnabled\": false,
    \"serviceAccountsEnabled\": true,
    \"consentRequired\": false,
    \"fullScopeAllowed\": true,
    \"access\": {
      \"view\": true,
      \"configure\": true,
      \"manage\": true
    }
  }"
)

info "$my_name" "Kong client creation response: $KONG_CLIENT"

if echo "$KONG_CLIENT" | jq -r '.id' > /dev/null 2>&1; then
  info "$my_name" "✓ Kong OIDC client created successfully"
  client_status="new"
elif echo "$KONG_CLIENT" | grep -q "already exists"; then
  info "$my_name" "✓ Kong OIDC client already exists"
  client_status="existing"
else
  error "$my_name" "Failed to create Kong OIDC client: $KONG_CLIENT"
  exit 2
fi

if [ "$client_status" = "new" ] || [ "$client_status" = "existing" ]; then
  info "$my_name" "Retrieving client secret for Kong OIDC client..."  
  # Get client secret
  CLIENT_SECRET=$(curl -s -X GET "${KEYCLOAK_PUBLIC_BASE}/admin/realms/${KEYCLOAK_REALM}/clients/${KONG_CLIENT_ID}/client-secret" \
    -H "Authorization: Bearer $TOKEN" \
    | jq -r '.value')
  info "$my_name" "✓ Kong client secret: ${CLIENT_SECRET:0:20}..."
  
  # Save credentials to file
  cat > /tmp/kong-client-credentials.txt << EOF
Kong OIDC Client Credentials:
Client ID: dq-made-easy-kong
Client Secret: ${CLIENT_SECRET}
Token Endpoint: ${KEYCLOAK_PUBLIC_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token
Issuer: ${KEYCLOAK_PUBLIC_URL}/realms/${KEYCLOAK_REALM}
JWKS URI: ${KEYCLOAK_PUBLIC_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/certs
EOF
  info "$my_name" "✓ Client credentials saved to /tmp/kong-client-credentials.txt"
else
  error "$my_name" "Failed to create Kong client: $KONG_CLIENT"
  exit 2
fi

# 4. Get realm public key
info "$my_name" "4. Getting realm public key..."
REALM_KEYS=$(curl -s "${KEYCLOAK_PUBLIC_BASE}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/certs" | jq '.keys[0]')
info "$my_name" "✓ Realm public keys available"

# 5. Display OIDC discovery endpoint
info "$my_name" "5. OIDC Discovery URL:"
info "$my_name" "${KEYCLOAK_PUBLIC_BASE}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration"

success "$my_name" "Keycloak realm setup complete!"
info "$my_name" "Next steps:"
info "$my_name" "1. Install Kong OIDC plugin: docker-compose exec kong luarocks install kong-oidc"
info "$my_name" "2. Enable OIDC plugin on /v1 route in Kong"
info "$my_name" "3. Test JWT token flow: Get token from Keycloak, send to Kong"
