#!/usr/bin/env bash
set -euo pipefail


# Purpose: Initialize Kong configuration after startup.
#
# What it does:
# - Waits for the Kong Admin API to become reachable.
# - Creates required services and routes if missing.
# - Enables baseline plugins (e.g. CORS, rate limiting) when needed.
#
# Version: 1.0
# Last modified: 2026-04-07

KONG_ADMIN_LOCAL_URL="${KONG_ADMIN_LOCAL_URL:-http://localhost:8001}"
JWT_JWKS_URL="${JWT_JWKS_URL:-}"
MAX_RETRIES=30
RETRY_COUNT=0

require_env() {
  local name="$1"
  local value="${!name:-}"
  if [ -z "$value" ]; then
    echo "Missing required environment variable: $name" >&2
    exit 1
  fi
  printf '%s' "$value"
}

UI_VITE_LOCAL_URL="$(require_env UI_VITE_LOCAL_URL)"
UI_NGINX_LOCAL_URL="$(require_env UI_NGINX_LOCAL_URL)"
DQ_API_LOCAL_URL="$(require_env DQ_API_LOCAL_URL)"
APP_CONFIG_LOCAL_URL="${DQ_API_LOCAL_URL%/}/api/system/v1/app-config"

echo "Waiting for Kong Admin API to become available..."
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  if curl -s -f "$KONG_ADMIN_LOCAL_URL/" > /dev/null 2>&1; then
    echo "✓ Kong Admin API is available"
    break
  fi
  echo -n "."
  RETRY_COUNT=$((RETRY_COUNT + 1))
  sleep 1
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
  echo "⚠ Kong Admin API did not become available after $MAX_RETRIES seconds"
  exit 1
fi

echo ""
echo "Configuring Kong services and routes..."

# Function to create service if it doesn't exist
create_service() {
  local SERVICE_NAME=$1
  local SERVICE_URL=$2
  
  # Check if service already exists using HTTP status code
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$KONG_ADMIN_LOCAL_URL/services/$SERVICE_NAME")
  
  if [ "$HTTP_CODE" != "200" ]; then
    echo "Creating service: $SERVICE_NAME -> $SERVICE_URL"
    CREATE_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$KONG_ADMIN_LOCAL_URL/services" \
      -H 'Content-Type: application/json' \
      -d "{\"name\": \"$SERVICE_NAME\", \"url\": \"$SERVICE_URL\"}")
    if [ "$CREATE_CODE" = "201" ] || [ "$CREATE_CODE" = "409" ]; then
      echo "✓ Created service: $SERVICE_NAME"
    else
      echo "⚠ Failed creating service: $SERVICE_NAME (HTTP $CREATE_CODE)"
      exit 1
    fi
  else
    echo "✓ Service already exists: $SERVICE_NAME"
  fi
}

# Function to create route if it doesn't exist
create_route() {
  local SERVICE_NAME=$1
  local ROUTE_NAME=$2
  local ROUTE_PATH=$3
  
  # Check if route already exists by name
  if ! curl -s "$KONG_ADMIN_LOCAL_URL/services/$SERVICE_NAME/routes" | grep -q "\"name\":\"$ROUTE_NAME\""; then
    echo "Creating route: $ROUTE_NAME ($ROUTE_PATH) for service $SERVICE_NAME"
    CREATE_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$KONG_ADMIN_LOCAL_URL/services/$SERVICE_NAME/routes" \
      -H 'Content-Type: application/json' \
      -d "{
        \"name\": \"$ROUTE_NAME\",
        \"paths\": [\"$ROUTE_PATH\"],
        \"path_handling\": \"v1\",
        \"methods\": [\"GET\", \"POST\", \"PUT\", \"DELETE\", \"PATCH\", \"OPTIONS\"],
        \"strip_path\": false
      }")
    if [ "$CREATE_CODE" = "201" ] || [ "$CREATE_CODE" = "409" ]; then
      echo "✓ Created route: $ROUTE_NAME"
    else
      echo "⚠ Failed creating route: $ROUTE_NAME (HTTP $CREATE_CODE)"
      exit 1
    fi
  else
    echo "✓ Route already exists: $ROUTE_NAME"
  fi
}

# Function to enable CORS plugin
enable_cors_plugin() {
  local SERVICE_NAME=$1
  
  # Check if CORS plugin already exists for this service
  if ! curl -s "$KONG_ADMIN_LOCAL_URL/services/$SERVICE_NAME/plugins" | grep -q '"name":"cors"'; then
    echo "Enabling CORS plugin for service: $SERVICE_NAME"
    CREATE_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$KONG_ADMIN_LOCAL_URL/services/$SERVICE_NAME/plugins" \
      -H 'Content-Type: application/json' \
      -d '{
        "name": "cors",
        "config": {
          "origins": ["${UI_VITE_LOCAL_URL}", "${UI_NGINX_LOCAL_URL}", "http://localhost:5173", "http://localhost:3000"],
          "methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
          "headers": ["Accept", "Accept-Version", "Content-Length", "Content-MD5", "Content-Type", "Date", "X-Auth-Token", "Authorization", "X-Correlation-ID", "traceparent", "tracestate", "baggage"],
          "exposed_headers": ["X-Kong-Response-Latency", "X-Kong-Upstream-Latency", "X-Correlation-ID", "X-Trace-ID"],
          "credentials": true,
          "max_age": 3600
        }
      }')
    if [ "$CREATE_CODE" = "201" ] || [ "$CREATE_CODE" = "409" ]; then
      echo "✓ Enabled CORS plugin for: $SERVICE_NAME"
    else
      echo "⚠ Failed enabling CORS plugin for: $SERVICE_NAME (HTTP $CREATE_CODE)"
      exit 1
    fi
  else
    echo "✓ CORS plugin already enabled for: $SERVICE_NAME"
  fi
}

# Function to enable rate limiting plugin
enable_rate_limiting() {
  local SERVICE_NAME=$1
  
  # Check if rate-limiting plugin already exists for this service
  if ! curl -s "$KONG_ADMIN_LOCAL_URL/services/$SERVICE_NAME/plugins" | grep -q '"name":"rate-limiting"'; then
    echo "Enabling rate-limiting plugin for service: $SERVICE_NAME"
    CREATE_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$KONG_ADMIN_LOCAL_URL/services/$SERVICE_NAME/plugins" \
      -H 'Content-Type: application/json' \
      -d '{
        "name": "rate-limiting",
        "config": {
          "minute": 1000,
          "hour": 50000,
          "policy": "local"
        }
      }')
    if [ "$CREATE_CODE" = "201" ] || [ "$CREATE_CODE" = "409" ]; then
      echo "✓ Enabled rate-limiting plugin for: $SERVICE_NAME"
    else
      echo "⚠ Failed enabling rate-limiting plugin for: $SERVICE_NAME (HTTP $CREATE_CODE)"
      exit 1
    fi
  else
    echo "✓ Rate-limiting plugin already enabled for: $SERVICE_NAME"
  fi
}

json_get_string() {
  local json="$1"
  local key="$2"
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$json" | jq -r --arg k "$key" '.[$k] // empty' 2>/dev/null || true
    return 0
  fi
  printf '%s' "$json" | tr -d '\n' | sed -n "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p"
}

json_get_bool() {
  local json="$1"
  local key="$2"
  if command -v jq >/dev/null 2>&1; then
    local value
    value=$(printf '%s' "$json" | jq -r --arg k "$key" '.[$k] // false' 2>/dev/null || true)
    if [ "$value" = "true" ] || [ "$value" = "false" ]; then
      printf '%s' "$value"
      return 0
    fi
  fi
  local value
  value=$(printf '%s' "$json" | tr -d '\n' | sed -n "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\(true\|false\).*/\1/p")
  printf '%s' "${value:-false}"
}

enable_jwt_for_route() {
  local route_name=$1

  APP_CFG=$(curl -s "$APP_CONFIG_LOCAL_URL" || true)
  if [ -z "$APP_CFG" ] || [ "$APP_CFG" = "null" ]; then
    APP_CFG=$(curl -s "$APP_CONFIG_LOCAL_URL" || true)
  fi
  SSO_ENABLED=$(json_get_bool "$APP_CFG" "ssoEnabled")
  SSO_ISSUER=$(json_get_string "$APP_CFG" "ssoIssuer")

  if [ "$SSO_ENABLED" != "true" ]; then
    echo "SSO disabled in app-config; skipping JWT enforcement"
    return 0
  fi

  if [ -z "$SSO_ISSUER" ]; then
    echo "SSO enabled but ssoIssuer is empty; skipping JWT enforcement"
    return 0
  fi

  ROUTE_ID=$(curl -s "$KONG_ADMIN_LOCAL_URL/routes/$route_name" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
  if [ -z "$ROUTE_ID" ]; then
    echo "⚠ Could not resolve route ID for $route_name; skipping JWT enforcement"
    return 0
  fi

  if ! curl -s "$KONG_ADMIN_LOCAL_URL/routes/$ROUTE_ID/plugins" | grep -q '"name":"jwt"'; then
    echo "Enabling JWT plugin on route: $route_name"
    CREATE_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$KONG_ADMIN_LOCAL_URL/routes/$ROUTE_ID/plugins" \
      -H 'Content-Type: application/json' \
      -d '{
        "name": "jwt",
        "config": {
          "key_claim_name": "iss",
          "claims_to_verify": ["exp"],
          "run_on_preflight": false
        }
      }')
    if [ "$CREATE_CODE" = "201" ] || [ "$CREATE_CODE" = "409" ]; then
      echo "✓ Enabled JWT plugin for route: $route_name"
    else
      echo "⚠ Failed enabling JWT plugin for route: $route_name (HTTP $CREATE_CODE)"
      exit 1
    fi
  else
    echo "✓ JWT plugin already enabled for route: $route_name"
  fi

  # Register issuer public key so Kong can verify RS256 tokens.
  if ! curl -s "$KONG_ADMIN_LOCAL_URL/consumers/oidc-issuer" | grep -q '"username":"oidc-issuer"'; then
    curl -s -X POST "$KONG_ADMIN_LOCAL_URL/consumers" \
      -H 'Content-Type: application/json' \
      -d '{"username":"oidc-issuer","custom_id":"oidc-issuer"}' > /dev/null || true
  fi

  JWKS_URI="$JWT_JWKS_URL"
  if [ -z "$JWKS_URI" ]; then
    JWKS_URI="${SSO_ISSUER%/}/protocol/openid-connect/certs"
  fi
  X5C=$(curl -s "$JWKS_URI" | tr -d '\n' | sed -n 's/.*"x5c"[[:space:]]*:[[:space:]]*\["\([^"]*\)"\].*/\1/p')

  if [ -n "$X5C" ]; then
    CERT_PEM="-----BEGIN CERTIFICATE-----\n$(printf '%s' "$X5C" | fold -w 64)\n-----END CERTIFICATE-----"
    RSA_PUBLIC_KEY=$(printf '%b\n' "$CERT_PEM" | openssl x509 -pubkey -noout 2>/dev/null || true)
    if [ -z "$RSA_PUBLIC_KEY" ]; then
      echo "⚠ Failed converting x5c certificate to RSA public key; skipping JWT credential setup"
      return 0
    fi

    upsert_issuer_key() {
      local issuer="$1"
      local jwt_id

      [ -z "$issuer" ] && return 0
      jwt_id=$(curl -s "$KONG_ADMIN_LOCAL_URL/consumers/oidc-issuer/jwt" | jq -r --arg k "$issuer" '.data[]? | select(.key==$k) | .id // empty' 2>/dev/null | head -1 || true)
      if [ -n "$jwt_id" ]; then
        curl -s -X DELETE "$KONG_ADMIN_LOCAL_URL/consumers/oidc-issuer/jwt/$jwt_id" >/dev/null || true
      fi

      curl -s -X POST "$KONG_ADMIN_LOCAL_URL/consumers/oidc-issuer/jwt" \
        --data "key=$issuer" \
        --data algorithm=RS256 \
        --data-urlencode "rsa_public_key=$RSA_PUBLIC_KEY" > /dev/null || true
    }

    upsert_issuer_key "$SSO_ISSUER"

    ALT_ISSUER=""
    if [[ "$SSO_ISSUER" == http://localhost* ]]; then
      ALT_ISSUER="${SSO_ISSUER/http:\/\/localhost/http:\/\/keycloak}"
    elif [[ "$SSO_ISSUER" == http://127.0.0.1* ]]; then
      ALT_ISSUER="${SSO_ISSUER/http:\/\/127.0.0.1/http:\/\/keycloak}"
    elif [[ "$SSO_ISSUER" == http://keycloak* ]]; then
      ALT_ISSUER="${SSO_ISSUER/http:\/\/keycloak/http:\/\/localhost}"
    fi

    upsert_issuer_key "$ALT_ISSUER"
    echo "✓ Registered issuer key material for JWT verification"
  else
    echo "⚠ Could not extract x5c from JWKS ($JWKS_URI); create JWT credential manually"
  fi
}

echo ""

# Create services
create_service "dq-api" "http://api:4010"

# Create routes
create_route "dq-api" "dq-api-auth-v1" "/auth/v1"
create_route "dq-api" "dq-api-admin-v1" "/admin/v1"
create_route "dq-api" "dq-api-system-v1" "/system/v1"
create_route "dq-api" "dq-api-data-catalog-v1" "/data-catalog/v1"
create_route "dq-api" "dq-api-rulebuilder-v1" "/rulebuilder/v1"

# Public allowlisted endpoints (must NOT require JWT at Kong)
create_route "dq-api" "dq-api-health" "/health"
create_route "dq-api" "dq-api-auth-v1-redirect" "/auth/v1/redirect"
create_route "dq-api" "dq-api-auth-v1-callback" "/auth/v1/callback"
create_route "dq-api" "dq-api-auth-v1-logout" "/auth/v1/logout"
create_route "dq-api" "dq-api-auth-v1-login" "/auth/v1/login"
create_route "dq-api" "dq-api-system-v1-version-catalog" "/system/v1/version-catalog"
create_route "dq-api" "dq-api-system-v1-system-info" "/system/v1/system-info"
create_route "dq-api" "dq-api-system-v1-health" "/system/v1/health"
create_route "dq-api" "dq-api-system-v1-readiness" "/system/v1/readiness"
create_route "dq-api" "dq-api-system-v1-live" "/system/v1/live"
create_route "dq-api" "dq-api-system-v1-ready" "/system/v1/ready"

create_route "dq-api" "dq-api-docs" "/api-docs"
create_route "dq-api" "dq-api-docs-json" "/api-docs-json"

# Enable plugins
enable_cors_plugin "dq-api"
enable_rate_limiting "dq-api"
enable_jwt_for_route "dq-api-auth-v1"
enable_jwt_for_route "dq-api-admin-v1"
enable_jwt_for_route "dq-api-system-v1"
enable_jwt_for_route "dq-api-data-catalog-v1"
enable_jwt_for_route "dq-api-rulebuilder-v1"

echo ""
echo "✓ Kong configuration complete!"
echo ""
echo "Available endpoints:"
echo "  - Kong Proxy:       https://kong.jac.dot:9443"
echo "  - Kong Admin API:   http://localhost:8001"
echo "  - Kong Manager GUI: https://localhost:8444/ops/kong"
echo "  - API Docs (Kong):  https://kong.jac.dot:9443/api-docs"
echo "  - OpenAPI JSON:     https://kong.jac.dot:9443/api-docs-json"
echo ""
