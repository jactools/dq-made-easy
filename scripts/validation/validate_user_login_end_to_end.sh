#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate that a seeded user can authenticate directly with Keycloak and use Kong-protected APIs.
#
# What it does:
# - Obtains a real Keycloak access token for a seeded user.
# - Calls /admin/v1/me through Kong with that token.
# - Calls /rulebuilder/v1/rules through Kong with that token and verifies data is returned.
#
# validate: groups=api,ui
#
# Version: 1.3
# Last modified: 2026-05-01

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
dq_source_seeded_user_credentials --quiet

KONG_PUBLIC_URL="${KONG_PUBLIC_URL:?KONG_PUBLIC_URL must be set to the real HTTPS Kong URL used by the UI}"
FRONTEND_ORIGIN="${UI_NGINX_LOCAL_URL:?UI_NGINX_LOCAL_URL must be set to the frontend origin used by the UI}"
LOGIN_EMAIL="${KEYCLOAK_JACCLOUD_USERNAME:?KEYCLOAK_JACCLOUD_USERNAME must be set}"
LOGIN_PASSWORD="${KEYCLOAK_JACCLOUD_PASSWORD:?KEYCLOAK_JACCLOUD_PASSWORD must be set}"
EXPECTED_EMAIL="$LOGIN_EMAIL"
KEYCLOAK_ISSUER_URL="${SSO_PUBLIC_ISSUER_URL:?SSO_PUBLIC_ISSUER_URL must be set to the real Keycloak issuer URL used by the UI}"
KEYCLOAK_CLIENT_ID="${VITE_KEYCLOAK_CLIENT_ID:?VITE_KEYCLOAK_CLIENT_ID must be set}"

if [[ "$KONG_PUBLIC_URL" != https://* ]]; then
  error "validate_user_login_end_to_end.sh" "KONG_PUBLIC_URL must use https:// (got ${KONG_PUBLIC_URL})"
  exit 1
fi

if [[ "$FRONTEND_ORIGIN" != https://* ]]; then
  error "validate_user_login_end_to_end.sh" "Frontend origin must use https:// (got ${FRONTEND_ORIGIN})"
  exit 1
fi

if [[ "$KEYCLOAK_ISSUER_URL" != https://* ]]; then
  error "validate_user_login_end_to_end.sh" "SSO_PUBLIC_ISSUER_URL must use https:// (got ${KEYCLOAK_ISSUER_URL})"
  exit 1
fi

KEYCLOAK_TOKEN_URL="${KEYCLOAK_ISSUER_URL%/}/protocol/openid-connect/token"
ME_URL="${KONG_PUBLIC_URL%/}/admin/v1/me"
RULES_URL="${KONG_PUBLIC_URL%/}/rulebuilder/v1/rules?page=1&limit=1"

TMP_DIR="$(mktemp -d)"
ME_BODY_FILE="${TMP_DIR}/me.json"
RULES_BODY_FILE="${TMP_DIR}/rules.json"

cleanup() {
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "validate_user_login_end_to_end.sh" "Missing required command: ${cmd}"
    exit 1
  fi
}

print_body() {
  local file_path="$1"
  if command -v jq >/dev/null 2>&1 && jq -e . "$file_path" >/dev/null 2>&1; then
    jq . "$file_path"
    return 0
  fi
  cat "$file_path"
}

require_cmd curl
require_cmd jq
require_cmd docker

refresh_kong_bootstrap() {
  local bootstrap_src="${ROOT_DIR}/dq-kong/scripts/bootstrap_kong.sh"
  local kong_container_id
  kong_container_id="$(docker ps -q -f name=^kong-gateway$ | tr -d '[:space:]' || true)"

  if [ -z "$kong_container_id" ]; then
    error "validate_user_login_end_to_end.sh" "Kong gateway container is not running; cannot refresh Kong bootstrap"
    exit 1
  fi

  if [ ! -f "$bootstrap_src" ]; then
    error "validate_user_login_end_to_end.sh" "Kong bootstrap script not found at ${bootstrap_src}"
    exit 1
  fi

  if ! docker cp "$bootstrap_src" "${kong_container_id}:/tmp/dq-bootstrap_kong.sh" >/dev/null 2>&1 \
    || ! docker exec "$kong_container_id" bash -lc "bash /tmp/dq-bootstrap_kong.sh"; then
    error "validate_user_login_end_to_end.sh" "Kong bootstrap refresh failed before login validation"
    exit 1
  fi
}

info "validate_user_login_end_to_end.sh" "=============================================="
info "validate_user_login_end_to_end.sh" "Alice Login End-to-End Validation"
info "validate_user_login_end_to_end.sh" "=============================================="
info "validate_user_login_end_to_end.sh" "KONG_PUBLIC_URL=${KONG_PUBLIC_URL}"
info "validate_user_login_end_to_end.sh" "SSO_PUBLIC_ISSUER_URL=${KEYCLOAK_ISSUER_URL}"
info "validate_user_login_end_to_end.sh" "FRONTEND_ORIGIN=${FRONTEND_ORIGIN}"
info "validate_user_login_end_to_end.sh" "LOGIN_EMAIL=${LOGIN_EMAIL}"

info "validate_user_login_end_to_end.sh" "Refreshing Kong bootstrap from the current Keycloak realm..."
refresh_kong_bootstrap

info "validate_user_login_end_to_end.sh" "[1/3] Requesting a Keycloak access token for ${LOGIN_EMAIL}..."
LOGIN_TOKEN="$(dq_keycloak_password_grant_access_token "$KEYCLOAK_TOKEN_URL" "$KEYCLOAK_CLIENT_ID" "$LOGIN_EMAIL" "$LOGIN_PASSWORD")"

case "$LOGIN_TOKEN" in
  *.*.*) ;;
  *)
    error "validate_user_login_end_to_end.sh" "Keycloak returned a non-JWT access token"
    exit 1
    ;;
esac

success "validate_user_login_end_to_end.sh" "Keycloak returned a JWT for ${LOGIN_EMAIL}"

info "validate_user_login_end_to_end.sh" "[2/3] Calling /admin/v1/me through Kong with the Keycloak token..."
ME_CODE="$(curl -sS -H "Authorization: Bearer ${LOGIN_TOKEN}" -o "$ME_BODY_FILE" -w "%{http_code}" "$ME_URL")"
if [ "$ME_CODE" != "200" ]; then
  error "validate_user_login_end_to_end.sh" "/admin/v1/me returned HTTP ${ME_CODE} when called through Kong with the Keycloak token"
  print_body "$ME_BODY_FILE"
  exit 1
fi

ME_ID="$(jq -r '.id // empty' "$ME_BODY_FILE")"
ME_EMAIL="$(jq -r '.email // empty' "$ME_BODY_FILE")"
if [ -z "$ME_ID" ] || [ "$ME_ID" = "null" ]; then
  error "validate_user_login_end_to_end.sh" "/admin/v1/me response did not include a user id"
  print_body "$ME_BODY_FILE"
  exit 1
fi
if [ "$ME_EMAIL" != "$EXPECTED_EMAIL" ]; then
  error "validate_user_login_end_to_end.sh" "/admin/v1/me returned email ${ME_EMAIL} (expected ${EXPECTED_EMAIL})"
  print_body "$ME_BODY_FILE"
  exit 1
fi

success "validate_user_login_end_to_end.sh" "/admin/v1/me resolved ${ME_ID} for ${ME_EMAIL} through Kong"

info "validate_user_login_end_to_end.sh" "[3/3] Calling /rulebuilder/v1/rules through Kong with the Keycloak token..."
RULES_CODE="$(curl -sS -H "Authorization: Bearer ${LOGIN_TOKEN}" -o "$RULES_BODY_FILE" -w "%{http_code}" "$RULES_URL")"
if [ "$RULES_CODE" != "200" ]; then
  error "validate_user_login_end_to_end.sh" "/rulebuilder/v1/rules returned HTTP ${RULES_CODE} when called through Kong with the Keycloak token"
  print_body "$RULES_BODY_FILE"
  exit 1
fi

RULES_COUNT="$(jq -r '(.data // []) | length' "$RULES_BODY_FILE" 2>/dev/null || echo 0)"
if [ -z "$RULES_COUNT" ] || [ "$RULES_COUNT" = "0" ]; then
  error "validate_user_login_end_to_end.sh" "/rulebuilder/v1/rules did not return any data for ${LOGIN_EMAIL}"
  print_body "$RULES_BODY_FILE"
  exit 1
fi

success "validate_user_login_end_to_end.sh" "/rulebuilder/v1/rules returned ${RULES_COUNT} row(s) for ${LOGIN_EMAIL} through Kong"
info "validate_user_login_end_to_end.sh" "=============================================="
success "validate_user_login_end_to_end.sh" "Alice login end-to-end validation succeeded"
info "validate_user_login_end_to_end.sh" "=============================================="