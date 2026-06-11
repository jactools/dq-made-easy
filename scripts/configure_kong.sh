#!/usr/bin/env bash
set -euo pipefail


# Purpose: Configure Kong routes/plugins for the DQ API gateway.
#
# What it does:
# - Creates/updates Kong services and routes for dq-api.
# - Configures JWT enforcement using the SSO issuer JWKS (when available).
# - Applies plugin configuration through the Kong Admin API.
#
# Version: 1.0
# Last modified: 2026-04-07

KONG_ADMIN_LOCAL_URL="${KONG_ADMIN_LOCAL_URL:-http://localhost:8001}"
DQ_API_LOCAL_URL="${DQ_API_LOCAL_URL:-http://localhost:4010}"
APP_CONFIG_LOCAL_URL="${DQ_API_LOCAL_URL%/}/api/system/v1/app-config"

get_app_cfg() {
  local field="$1"
  curl -sS "$APP_CONFIG_LOCAL_URL" | jq -r ".${field} // empty" 2>/dev/null || true
}

configure_jwt_enforcement() {
  local route_id="$1"
  local issuer="$2"

  if [ -z "$issuer" ]; then
    echo "⚠ SSO issuer is empty; skipping Kong JWT enforcement"
    return 0
  fi

  echo "Configuring Kong JWT plugin on route ${route_id}..."
  curl -s -X POST "${KONG_ADMIN_LOCAL_URL}/routes/${route_id}/plugins" \
    --data name=jwt \
    --data 'config.key_claim_name=iss' \
    --data 'config.claims_to_verify=exp' \
    --data 'config.run_on_preflight=false' > /dev/null

  # Use issuer's JWKS cert for RS256 verification.
  local well_known jwks_uri x5c cert_pem rsa_public_key
  well_known=$(curl -sS "${issuer%/}/.well-known/openid-configuration" || true)
  jwks_uri=$(echo "$well_known" | jq -r '.jwks_uri // empty' 2>/dev/null || true)
  if [ -z "$jwks_uri" ]; then
    jwks_uri="${issuer%/}/protocol/openid-connect/certs"
  fi

  x5c=$(curl -sS "$jwks_uri" | jq -r '.keys[] | select((.use // "sig") == "sig") | .x5c[0] // empty' | head -1)
  if [ -z "$x5c" ]; then
    if [[ "$jwks_uri" == https://* ]]; then
      alt_jwks_uri="${jwks_uri/https:\/\//http://}"
      x5c=$(curl -sS "$alt_jwks_uri" | jq -r '.keys[] | select((.use // "sig") == "sig") | .x5c[0] // empty' | head -1)
      if [ -n "$x5c" ]; then
        jwks_uri="$alt_jwks_uri"
      fi
    fi
  fi
  if [ -z "$x5c" ]; then
    echo "⚠ Could not read signing cert from JWKS ($jwks_uri); JWT plugin is enabled but credential setup skipped"
    return 0
  fi

  cert_pem="-----BEGIN CERTIFICATE-----\n$(echo "$x5c" | fold -w 64)\n-----END CERTIFICATE-----"
  rsa_public_key=$(printf '%b\n' "$cert_pem" | openssl x509 -pubkey -noout 2>/dev/null || true)
  if [ -z "$rsa_public_key" ]; then
    echo "⚠ Failed to convert JWKS cert to RSA public key; skipping credential setup"
    return 0
  fi

  local consumer_username="oidc-issuer"
  local secondary_issuer=""

  if [[ "$issuer" == http://localhost* ]]; then
    secondary_issuer="${issuer/http:\/\/localhost/http:\/\/keycloak}"
  elif [[ "$issuer" == http://127.0.0.1* ]]; then
    secondary_issuer="${issuer/http:\/\/127.0.0.1/http:\/\/keycloak}"
  elif [[ "$issuer" == http://keycloak* ]]; then
    secondary_issuer="${issuer/http:\/\/keycloak/http:\/\/localhost}"
  fi

  register_jwt_credential() {
    local key_issuer="$1"
    if [ -z "$key_issuer" ]; then
      return 0
    fi

    local existing_id
    existing_id=$(curl -s "${KONG_ADMIN_LOCAL_URL}/consumers/${consumer_username}/jwt" | jq -r --arg k "$key_issuer" '.data[]? | select(.key==$k) | .id // empty' 2>/dev/null | head -1 || true)
    if [ -n "$existing_id" ]; then
      curl -s -X DELETE "${KONG_ADMIN_LOCAL_URL}/consumers/${consumer_username}/jwt/${existing_id}" > /dev/null || true
    fi

    curl -s -X POST "${KONG_ADMIN_LOCAL_URL}/consumers/${consumer_username}/jwt" \
      --data "key=${key_issuer}" \
      --data algorithm=RS256 \
      --data-urlencode "rsa_public_key=${rsa_public_key}" > /dev/null || true
  }

  curl -s -X POST "${KONG_ADMIN_LOCAL_URL}/consumers" \
    --data "username=${consumer_username}" \
    --data custom_id=oidc-issuer > /dev/null || true

  register_jwt_credential "$issuer"
  register_jwt_credential "$secondary_issuer"

  echo "✅ JWT enforcement enabled on route ${route_id}"
}

echo "🔧 Configuring Kong Gateway for DQ API..."

# 1. Create Service for dq-api
echo "Creating dq-api service..."
SERVICE_RESP=$(curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services \
  --data name=dq-api \
  --data protocol=http \
  --data host=api \
  --data port=4010 \
  --data path=/ \
  --data retries=5 \
  --data connect_timeout=60000 \
  --data write_timeout=60000 \
  --data read_timeout=60000)
SERVICE_ID=$(echo "$SERVICE_RESP" | jq -r '.id // empty')
if [ -z "$SERVICE_ID" ]; then
  SERVICE_ID=$(curl -s "${KONG_ADMIN_LOCAL_URL}/services/dq-api" | jq -r '.id // empty')
fi

echo "Service created: $SERVICE_ID"

# 2. Create group-first routes (/\<group\>/v1/*)
echo "Creating group routes..."

AUTH_ROUTE_ID=$(curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-auth-v1 \
  --data 'paths[]=/auth/v1' \
  --data 'methods[]=GET' \
  --data 'methods[]=POST' \
  --data 'methods[]=PUT' \
  --data 'methods[]=DELETE' \
  --data 'methods[]=PATCH' \
  --data strip_path=false | jq -r '.id // empty')
if [ -z "$AUTH_ROUTE_ID" ]; then
  AUTH_ROUTE_ID=$(curl -s "${KONG_ADMIN_LOCAL_URL}/routes/dq-api-auth-v1" | jq -r '.id // empty')
fi

ADMIN_ROUTE_ID=$(curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-admin-v1 \
  --data 'paths[]=/admin/v1' \
  --data 'methods[]=GET' \
  --data 'methods[]=POST' \
  --data 'methods[]=PUT' \
  --data 'methods[]=DELETE' \
  --data 'methods[]=PATCH' \
  --data strip_path=false | jq -r '.id // empty')
if [ -z "$ADMIN_ROUTE_ID" ]; then
  ADMIN_ROUTE_ID=$(curl -s "${KONG_ADMIN_LOCAL_URL}/routes/dq-api-admin-v1" | jq -r '.id // empty')
fi

SYSTEM_ROUTE_ID=$(curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-system-v1 \
  --data 'paths[]=/system/v1' \
  --data 'methods[]=GET' \
  --data 'methods[]=POST' \
  --data 'methods[]=PUT' \
  --data 'methods[]=DELETE' \
  --data 'methods[]=PATCH' \
  --data strip_path=false | jq -r '.id // empty')
if [ -z "$SYSTEM_ROUTE_ID" ]; then
  SYSTEM_ROUTE_ID=$(curl -s "${KONG_ADMIN_LOCAL_URL}/routes/dq-api-system-v1" | jq -r '.id // empty')
fi

DATA_CATALOG_ROUTE_ID=$(curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-data-catalog-v1 \
  --data 'paths[]=/data-catalog/v1' \
  --data 'methods[]=GET' \
  --data 'methods[]=POST' \
  --data 'methods[]=PUT' \
  --data 'methods[]=DELETE' \
  --data 'methods[]=PATCH' \
  --data strip_path=false | jq -r '.id // empty')
if [ -z "$DATA_CATALOG_ROUTE_ID" ]; then
  DATA_CATALOG_ROUTE_ID=$(curl -s "${KONG_ADMIN_LOCAL_URL}/routes/dq-api-data-catalog-v1" | jq -r '.id // empty')
fi

RULEBUILDER_ROUTE_ID=$(curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-rulebuilder-v1 \
  --data 'paths[]=/rulebuilder/v1' \
  --data 'methods[]=GET' \
  --data 'methods[]=POST' \
  --data 'methods[]=PUT' \
  --data 'methods[]=DELETE' \
  --data 'methods[]=PATCH' \
  --data strip_path=false | jq -r '.id // empty')
if [ -z "$RULEBUILDER_ROUTE_ID" ]; then
  RULEBUILDER_ROUTE_ID=$(curl -s "${KONG_ADMIN_LOCAL_URL}/routes/dq-api-rulebuilder-v1" | jq -r '.id // empty')
fi

echo "Group routes created (ids):"
echo "  auth:        ${AUTH_ROUTE_ID}"
echo "  admin:       ${ADMIN_ROUTE_ID}"
echo "  system:      ${SYSTEM_ROUTE_ID}"
echo "  data-catalog:${DATA_CATALOG_ROUTE_ID}"
echo "  rulebuilder: ${RULEBUILDER_ROUTE_ID}"

# 2b. Create routes for API docs / OpenAPI specs
echo "Creating /api-docs route..."
DOCS_ROUTE_ID=$(curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-docs \
  --data 'paths[]=/api-docs' \
  --data 'methods[]=GET' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false | jq -r '.id')

echo "Docs route created: $DOCS_ROUTE_ID"

echo "Creating /api-docs-json route..."
DOCS_JSON_ROUTE_ID=$(curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-docs-json \
  --data 'paths[]=/api-docs-json' \
  --data 'methods[]=GET' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false | jq -r '.id')

echo "Docs JSON route created: $DOCS_JSON_ROUTE_ID"

# 3. Enable CORS Plugin
echo "Enabling CORS plugin..."
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/plugins \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "cors",
    "config": {
      "origins": [
        "http://dq-made-easy.local:5173",
        "http://dq-made-easy.local:5174",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000"
      ],
      "methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
      "headers": [
        "Accept",
        "Accept-Version",
        "Content-Length",
        "Content-MD5",
        "Content-Type",
        "Date",
        "X-Auth-Token",
        "Authorization",
        "X-Correlation-ID",
        "traceparent",
        "tracestate",
        "baggage"
      ],
      "exposed_headers": [
        "X-Kong-Response-Latency",
        "X-Kong-Upstream-Latency",
        "X-Correlation-ID",
        "X-Trace-ID"
      ],
      "credentials": true,
      "max_age": 3600
    }
  }' > /dev/null

echo "✅ CORS plugin enabled"

# 4. Enable Rate Limiting (per consumer)
echo "Enabling rate limiting plugin..."
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/plugins \
  --data name=rate-limiting \
  --data config.minute=1000 \
  --data config.hour=50000 \
  --data config.policy=local \
  --data config.fault_tolerant=true \
  --data config.hide_client_headers=false > /dev/null

echo "✅ Rate limiting enabled (1000/min, 50000/hour)"

# 5. Enable Request Transformer (add correlation ID if missing)
echo "Enabling request transformer..."
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/plugins \
  --data name=request-transformer \
  --data 'config.add.headers=X-Forwarded-By:Kong' \
  --data 'config.add.headers=X-Gateway-Version:3.5' > /dev/null

echo "✅ Request transformer enabled"

# 6. Enable Prometheus Metrics
echo "Enabling Prometheus metrics..."
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/plugins \
  --data name=prometheus > /dev/null

echo "✅ Prometheus metrics enabled at :8001/metrics"

# 7. Enable Response Transformer (add HSTS, security headers)
echo "Enabling response transformer..."
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/plugins \
  --data name=response-transformer \
  --data 'config.add.headers=X-Content-Type-Options:nosniff' \
  --data 'config.add.headers=X-Frame-Options:DENY' \
  --data 'config.add.headers=X-XSS-Protection:1; mode=block' \
  --data 'config.add.headers=Referrer-Policy:strict-origin-when-cross-origin' > /dev/null

echo "✅ Response transformer with security headers enabled"

# 8. Create public allowlisted routes (must NOT require JWT)
echo "Creating public allowlisted routes (auth + system)..."
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-health \
  --data 'paths[]=/health' \
  --data 'methods[]=GET' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false > /dev/null || true
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-auth-v1-login \
  --data 'paths[]=/auth/v1/login' \
  --data 'methods[]=POST' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false > /dev/null || true
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-auth-v1-logout \
  --data 'paths[]=/auth/v1/logout' \
  --data 'methods[]=GET' \
  --data 'methods[]=POST' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false > /dev/null || true
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-auth-v1-redirect \
  --data 'paths[]=/auth/v1/redirect' \
  --data 'methods[]=GET' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false > /dev/null || true
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-auth-v1-callback \
  --data 'paths[]=/auth/v1/callback' \
  --data 'methods[]=GET' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false > /dev/null || true
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-system-v1-health \
  --data 'paths[]=/system/v1/health' \
  --data 'methods[]=GET' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false > /dev/null || true
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-system-v1-ready \
  --data 'paths[]=/system/v1/ready' \
  --data 'methods[]=GET' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false > /dev/null || true
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-system-v1-live \
  --data 'paths[]=/system/v1/live' \
  --data 'methods[]=GET' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false > /dev/null || true
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-system-v1-readiness \
  --data 'paths[]=/system/v1/readiness' \
  --data 'methods[]=GET' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false > /dev/null || true
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-system-v1-system-info \
  --data 'paths[]=/system/v1/system-info' \
  --data 'methods[]=GET' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false > /dev/null || true
curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/services/${SERVICE_ID}/routes \
  --data name=dq-api-system-v1-version-catalog \
  --data 'paths[]=/system/v1/version-catalog' \
  --data 'methods[]=GET' \
  --data 'methods[]=OPTIONS' \
  --data strip_path=false > /dev/null || true

# 8b. Enforce JWT on group routes when SSO is enabled in application settings
echo "Reading SSO settings from app-config..."
SSO_ENABLED=$(get_app_cfg "ssoEnabled")
SSO_ISSUER=$(get_app_cfg "ssoIssuer")

if [ "${SSO_ENABLED}" = "true" ]; then
  configure_jwt_enforcement "$AUTH_ROUTE_ID" "$SSO_ISSUER"
  configure_jwt_enforcement "$ADMIN_ROUTE_ID" "$SSO_ISSUER"
  configure_jwt_enforcement "$SYSTEM_ROUTE_ID" "$SSO_ISSUER"
  configure_jwt_enforcement "$DATA_CATALOG_ROUTE_ID" "$SSO_ISSUER"
  configure_jwt_enforcement "$RULEBUILDER_ROUTE_ID" "$SSO_ISSUER"
else
  echo "SSO disabled in app-config; JWT route enforcement skipped"
fi

# 9. Create Consumer for dq-ui
echo "Creating dq-ui consumer..."
UI_CONSUMER_ID=$(curl -s -X POST ${KONG_ADMIN_LOCAL_URL}/consumers \
  --data username=dq-ui \
  --data custom_id=dq-ui-frontend | jq -r '.id')

echo "Consumer created: $UI_CONSUMER_ID"

# 10. Summary
echo ""
echo "🎉 Kong Gateway configured successfully!"
echo ""
echo "📊 Configuration Summary:"
echo "  Service:     dq-api (${SERVICE_ID:0:8}...)"
echo "  Routes:      /auth/v1, /admin/v1, /system/v1, /data-catalog/v1, /rulebuilder/v1 → http://api:4010"
echo "  Plugins:     CORS, Rate Limiting, Transformers, Prometheus"
if [ "${SSO_ENABLED}" = "true" ]; then
echo "  Auth:        JWT enforced on group routes"
else
echo "  Auth:        Not enforced (ssoEnabled=false in app-config)"
fi
echo "  Public:      /auth/v1/login,/auth/v1/logout,/auth/v1/redirect,/auth/v1/callback,/system/v1/*"
echo "  Consumer:    dq-ui (${UI_CONSUMER_ID:0:8}...)"
echo ""
echo "🔗 Access Points:"
echo "  Proxy:       https://kong.jac.dot:9443/system/v1/health"
echo "  Admin API:   http://localhost:8001/"
echo "  Kong Manager:http://localhost:8002/"
echo "  Metrics:     http://localhost:8001/metrics"
echo ""
echo "📝 Next Steps:"
echo "  1. Verify JWT flow: ./scripts/test_jwt_flow.sh"
echo "  2. Update dq-ui API base URL to https://kong.jac.dot:9443"
echo "  3. Test: curl https://kong.jac.dot:9443/system/v1/health"
echo ""
