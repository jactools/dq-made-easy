#!/usr/bin/env bash
set -euo pipefail


# Purpose: Smoke-test Kong public auth endpoints and redirect behavior.
#
# What it does:
# - Verifies Kong proxy is reachable.
# - Ensures protected routes remain protected.
# - Confirms /auth/v1/redirect points to the expected Keycloak auth endpoint.
# - Verifies /auth/v1/login is reachable through Kong without a JWT.
#
# Version: 1.2
# Last modified: 2026-05-01

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

validate_selected_root_env_file "$ROOT_DIR" full

if ! source_selected_root_env_file; then
  exit 1
fi

if [[ $# -gt 0 ]]; then
  error "smoke_test_auth_kong.sh" "Unknown arg: $1"
  exit 1
fi

dq_source_seeded_user_credentials --quiet

KONG_PUBLIC_URL="${KONG_PUBLIC_URL:?KONG_PUBLIC_URL must be set to the real HTTPS Kong URL used by the UI}"
FRONTEND_ORIGIN="${UI_NGINX_LOCAL_URL:?UI_NGINX_LOCAL_URL must be set to the real frontend origin used by the UI}"
LOGIN_EMAIL="${KEYCLOAK_JACCLOUD_USERNAME:?KEYCLOAK_JACCLOUD_USERNAME must be set}"
EXPECTED_ISSUER_BASE="${SSO_PUBLIC_ISSUER_URL:?SSO_PUBLIC_ISSUER_URL must be set to the real Keycloak issuer URL used by the UI}"

if [[ "$KONG_PUBLIC_URL" != https://* ]]; then
  error "smoke_test_auth_kong.sh" "KONG_PUBLIC_URL must use https:// (got ${KONG_PUBLIC_URL})"
  exit 1
fi

if [[ "$FRONTEND_ORIGIN" != https://* ]]; then
  error "smoke_test_auth_kong.sh" "Frontend origin must use https:// (got ${FRONTEND_ORIGIN})"
  exit 1
fi

if [[ "$EXPECTED_ISSUER_BASE" != https://* ]]; then
  error "smoke_test_auth_kong.sh" "SSO_PUBLIC_ISSUER_URL must use https:// (got ${EXPECTED_ISSUER_BASE})"
  exit 1
fi

EXPECTED_AUTH_PREFIX="${EXPECTED_ISSUER_BASE%/}/protocol/openid-connect/auth"

print_redacted_body() {
  local file_path="$1"
  if command -v jq >/dev/null 2>&1; then
    if jq -e . "$file_path" >/dev/null 2>&1; then
      jq 'if type == "object" and has("token") then .token = "***REDACTED***" else . end' "$file_path"
      return 0
    fi
  fi

  cat "$file_path"
}

FRONTEND_ENCODED=$(FRONTEND_ORIGIN="$FRONTEND_ORIGIN" "$PYTHON_RUNNER" - <<'PY'
import os
import urllib.parse

print(urllib.parse.quote(os.environ["FRONTEND_ORIGIN"], safe=""))
PY
)
REDIRECT_URL="${KONG_PUBLIC_URL%/}/auth/v1/redirect?frontend=${FRONTEND_ENCODED}"

info "smoke_test_auth_kong.sh" "=============================================="
info "smoke_test_auth_kong.sh" "Kong Public Auth Smoke Test"
info "smoke_test_auth_kong.sh" "=============================================="
info "smoke_test_auth_kong.sh" "KONG_PUBLIC_URL=${KONG_PUBLIC_URL}"
info "smoke_test_auth_kong.sh" "FRONTEND_ORIGIN=${FRONTEND_ORIGIN}"
info "smoke_test_auth_kong.sh" "LOGIN_EMAIL=${LOGIN_EMAIL}"

# 1) Kong proxy responds (health endpoint)
HEALTH_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "${KONG_PUBLIC_URL%/}/system/v1/health")
if [ "$HEALTH_CODE" != "200" ] && [ "$HEALTH_CODE" != "401" ]; then
  error "smoke_test_auth_kong.sh" "Kong health endpoint not reachable (HTTP ${HEALTH_CODE})"
  exit 1
fi
success "smoke_test_auth_kong.sh" "Kong health endpoint reachable (HTTP ${HEALTH_CODE})"

# 2) Protected route should still require auth
RULES_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "${KONG_PUBLIC_URL%/}/rulebuilder/v1/rules")
if [ "$RULES_CODE" != "401" ]; then
  error "smoke_test_auth_kong.sh" "Expected /rulebuilder/v1/rules to require auth (HTTP 401), got ${RULES_CODE}"
  exit 1
fi
success "smoke_test_auth_kong.sh" "/rulebuilder/v1/rules remains protected"

# 3) Public auth redirect should return 302 to Keycloak
REDIRECT_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$REDIRECT_URL")
if [ "$REDIRECT_CODE" != "302" ]; then
  error "smoke_test_auth_kong.sh" "Expected /auth/v1/redirect to return 302, got ${REDIRECT_CODE}"
  exit 1
fi

LOCATION=$(curl -sS -D - -o /dev/null "$REDIRECT_URL" | grep -i '^location:' | sed -E 's/^[Ll]ocation:[[:space:]]*//' | tr -d '\r' | tail -1)
if [[ "$LOCATION" != ${EXPECTED_AUTH_PREFIX}* ]]; then
  error "smoke_test_auth_kong.sh" "Redirect location does not point to Keycloak auth endpoint"
  error "smoke_test_auth_kong.sh" "Expected prefix: ${EXPECTED_AUTH_PREFIX}"
  error "smoke_test_auth_kong.sh" "Location: ${LOCATION}"
  exit 1
fi
success "smoke_test_auth_kong.sh" "/auth/v1/redirect points to Keycloak"

# 4) Public login route should be reachable through Kong without JWT
LOGIN_BODY_FILE=$(mktemp)
LOGIN_CODE=$(curl -sS -o "$LOGIN_BODY_FILE" -w "%{http_code}" -X POST "${KONG_PUBLIC_URL%/}/auth/v1/login" \
  -H "content-type: application/json" \
  -d "{\"email\":\"${LOGIN_EMAIL}\"}")

if [ "$LOGIN_CODE" = "401" ] || [ "$LOGIN_CODE" = "403" ]; then
  error "smoke_test_auth_kong.sh" "/auth/v1/login appears gateway-protected (HTTP ${LOGIN_CODE})"
  info "smoke_test_auth_kong.sh" "Body:"
  print_redacted_body "$LOGIN_BODY_FILE"
  rm -f "$LOGIN_BODY_FILE"
  exit 1
fi

if [ "$LOGIN_CODE" = "200" ] || [ "$LOGIN_CODE" = "201" ]; then
  TOKEN=$(jq -r '.token // empty' "$LOGIN_BODY_FILE" 2>/dev/null || true)
  if [ -z "$TOKEN" ]; then
    error "smoke_test_auth_kong.sh" "/auth/v1/login returned 200 but no token was found"
    rm -f "$LOGIN_BODY_FILE"
    exit 1
  fi
  success "smoke_test_auth_kong.sh" "/auth/v1/login returns token (HTTP ${LOGIN_CODE})"
elif [ "$LOGIN_CODE" = "404" ]; then
  DETAIL=$(jq -r '.detail // empty' "$LOGIN_BODY_FILE" 2>/dev/null || true)
  if [ "$DETAIL" = "User not found" ]; then
      success "smoke_test_auth_kong.sh" "/auth/v1/login is public (backend reached; seeded user not found)"
  else
    error "smoke_test_auth_kong.sh" "/auth/v1/login returned unexpected 404 payload"
    print_redacted_body "$LOGIN_BODY_FILE"
    rm -f "$LOGIN_BODY_FILE"
    exit 1
  fi
else
  error "smoke_test_auth_kong.sh" "/auth/v1/login returned unexpected HTTP ${LOGIN_CODE}"
  print_redacted_body "$LOGIN_BODY_FILE"
  rm -f "$LOGIN_BODY_FILE"
  exit 1
fi
rm -f "$LOGIN_BODY_FILE"

info "smoke_test_auth_kong.sh" "=============================================="
success "smoke_test_auth_kong.sh" "PASS: Kong public auth smoke checks passed"
info "smoke_test_auth_kong.sh" "=============================================="
