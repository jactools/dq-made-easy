#!/usr/bin/env bash
set -euo pipefail

# Purpose: Smoke-test Zammad SSO login initiation through HTTPS Keycloak.
# What it does:
# - Calls Zammad's sign-in discovery endpoint over the configured HTTPS URL.
# - Verifies the Zammad config advertises OpenID Connect over HTTPS.
# - Verifies Keycloak issues a JWT for the seeded smoke user over HTTPS.
# validate: groups=support,auth
# Version: 1.0.0
# Last modified: 2026-05-23

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_zammad_sso_login.sh"

init_root_env_file "$ROOT_DIR"
validate_selected_root_env_file "$ROOT_DIR" full

if ! source_selected_root_env_file; then
  exit 1
fi

dq_source_seeded_user_credentials --quiet

SUPPORT_URL="${ZAMMAD_PUBLIC_URL:?ZAMMAD_PUBLIC_URL must be set}"
SSO_ISSUER_URL="${SSO_PUBLIC_ISSUER_URL:?SSO_PUBLIC_ISSUER_URL must be set to the public Keycloak issuer URL}"
LOGIN_EMAIL="${KEYCLOAK_JACCLOUD_USERNAME:?KEYCLOAK_JACCLOUD_USERNAME must be set}"
LOGIN_PASSWORD="${KEYCLOAK_JACCLOUD_PASSWORD:?KEYCLOAK_JACCLOUD_PASSWORD must be set}"
CLIENT_ID="${KEYCLOAK_CLIENT_ID:?KEYCLOAK_CLIENT_ID must be set}"

SUPPORT_ORIGIN="${SUPPORT_URL%/}"
KEYCLOAK_TOKEN_URL="${SSO_ISSUER_URL%/}/protocol/openid-connect/token"
EXPECTED_AUTH_PREFIX="${SSO_ISSUER_URL%/}/protocol/openid-connect/auth"
EXPECTED_CALLBACK_URL="${SUPPORT_ORIGIN%/}/auth/openid_connect/callback"

if [[ "$SUPPORT_ORIGIN" != https://* ]]; then
  error "$my_name" "Support origin must use https:// (got ${SUPPORT_ORIGIN})"
  exit 1
fi

if [[ "$SUPPORT_ORIGIN" == *":443"* ]]; then
  error "$my_name" "Zammad HTTPS must not use port 443"
  exit 1
fi

if [[ "$SSO_ISSUER_URL" != https://* ]]; then
  error "$my_name" "SSO_PUBLIC_ISSUER_URL must use https:// (got ${SSO_ISSUER_URL})"
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  error "$my_name" "curl is required"
  exit 127
fi

info "$my_name" "=============================================="
info "$my_name" "Zammad SSO Login Smoke Test"
info "$my_name" "=============================================="
info "$my_name" "SUPPORT_ORIGIN=${SUPPORT_ORIGIN}"
info "$my_name" "SSO_PUBLIC_ISSUER_URL=${SSO_ISSUER_URL}"
info "$my_name" "LOGIN_EMAIL=${LOGIN_EMAIL}"

signshow_body_file="$(mktemp)"
browser_page_file="$(mktemp)"
browser_headers_file="$(mktemp)"
browser_cookie_file="$(mktemp)"
cleanup() {
  rm -f "$signshow_body_file"
  rm -f "$browser_page_file"
  rm -f "$browser_headers_file"
  rm -f "$browser_cookie_file"
}
trap cleanup EXIT

set +e
signshow_code="$(curl -k -sS -o "$signshow_body_file" -w '%{http_code}' "$SUPPORT_ORIGIN/api/v1/signshow")"
signshow_rc=$?
set -e

if [ "$signshow_rc" -ne 0 ]; then
  error "$my_name" "Zammad signshow request failed with rc=$signshow_rc"
  exit "$signshow_rc"
fi

if [ "$signshow_code" != "200" ]; then
  error "$my_name" "Expected Zammad signshow to return 200, got ${signshow_code}"
  cat "$signshow_body_file" >&2 || true
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  error "$my_name" "jq is required"
  exit 1
fi

config_http_type="$(jq -r '.config.http_type // empty' "$signshow_body_file")"
config_oidc_enabled="$(jq -r '.config.auth_openid_connect // empty' "$signshow_body_file")"
config_oidc_display_name="$(jq -r '.config.auth_openid_connect_display_name // empty' "$signshow_body_file")"

if [ "$config_http_type" != "https" ]; then
  error "$my_name" "Expected Zammad config http_type to be https, got ${config_http_type}"
  exit 1
fi

if [ "$config_oidc_enabled" != "true" ]; then
  error "$my_name" "Expected auth_openid_connect to be enabled"
  exit 1
fi

if [ -z "$config_oidc_display_name" ]; then
  error "$my_name" "Expected auth_openid_connect_display_name to be set"
  exit 1
fi

success "$my_name" "Zammad exposes OpenID Connect config over HTTPS"

set +e
curl -k -sS -c "$browser_cookie_file" "$SUPPORT_ORIGIN/" -o "$browser_page_file"
browser_page_rc=$?
set -e

if [ "$browser_page_rc" -ne 0 ]; then
  error "$my_name" "Failed to load Zammad homepage for browser-style SSO initiation"
  exit "$browser_page_rc"
fi

browser_csrf_token="$(sed -n 's/.*meta name="csrf-token" content="\([^"]*\)".*/\1/p' "$browser_page_file" | head -n 1)"
if [ -z "$browser_csrf_token" ]; then
  error "$my_name" "Unable to extract Zammad CSRF token from the homepage"
  exit 1
fi

set +e
browser_post_code="$(curl -k -sS -b "$browser_cookie_file" -c "$browser_cookie_file" -D "$browser_headers_file" -o /dev/null -w '%{http_code}' \
  -X POST "$SUPPORT_ORIGIN/auth/openid_connect" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "authenticity_token=$browser_csrf_token" \
  --data-urlencode 'utf8=✓' \
  --data-urlencode 'commit=Sign in')"
browser_post_rc=$?
set -e

if [ "$browser_post_rc" -ne 0 ]; then
  error "$my_name" "Browser-style Zammad SSO initiation failed with rc=$browser_post_rc"
  exit "$browser_post_rc"
fi

browser_location_header="$(awk 'BEGIN { IGNORECASE=1 } /^location:/ { sub(/^location:[[:space:]]*/, "", $0); print; exit }' "$browser_headers_file")"
if [ "$browser_post_code" != "302" ] && [ "$browser_post_code" != "303" ]; then
  error "$my_name" "Expected browser-style Zammad SSO initiation to redirect, got HTTP ${browser_post_code}"
  if [ -s "$browser_headers_file" ]; then
    sed 's/^/[browser-post] /' "$browser_headers_file" >&2 || true
  fi
  exit 1
fi

if [[ "$browser_location_header" == /auth/failure* ]] || [[ "$browser_location_header" == *"/auth/failure?"* ]]; then
  error "$my_name" "Browser-style Zammad SSO initiation failed: ${browser_location_header}"
  exit 1
fi

if [[ "$browser_location_header" != "$EXPECTED_AUTH_PREFIX"* ]]; then
  error "$my_name" "Expected browser-style Zammad SSO initiation to redirect to ${EXPECTED_AUTH_PREFIX}, got ${browser_location_header}"
  exit 1
fi

success "$my_name" "Zammad browser-style SSO initiation redirects to Keycloak over HTTPS"

access_token="$(dq_keycloak_password_grant_access_token "$KEYCLOAK_TOKEN_URL" "$CLIENT_ID" "$LOGIN_EMAIL" "$LOGIN_PASSWORD" -k)"
if [ -z "$access_token" ]; then
  error "$my_name" "Keycloak password grant did not return an access token"
  exit 1
fi

if [[ "$access_token" != *.*.* ]]; then
  error "$my_name" "Keycloak returned a non-JWT access token"
  exit 1
fi

success "$my_name" "Keycloak returns a JWT for the seeded login user over HTTPS"
success "$my_name" "PASS: Zammad SSO login smoke checks passed"