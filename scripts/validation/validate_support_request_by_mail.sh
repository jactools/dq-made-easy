#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate that an operations assistance request can be sent by email.
#
# What it does:
# - Obtains a Keycloak access token with the password grant.
# - Posts a support request through the configured API/Kong endpoint.
# - Captures and prints the HTTP status, curl rc, and response body.
#
# validate: groups=api

# Version: 1.0.0
# Last modified: 2026-04-14

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
dq_source_seeded_user_credentials --quiet

: "${KONG_PUBLIC_URL:?KONG_PUBLIC_URL must be set to the public Kong URL used by the UI}"
: "${SSO_PUBLIC_ISSUER_URL:?SSO_PUBLIC_ISSUER_URL must be set to the public Keycloak issuer URL}"
: "${VITE_KEYCLOAK_CLIENT_ID:?VITE_KEYCLOAK_CLIENT_ID must be set}"
: "${KEYCLOAK_JACCLOUD_USERNAME:?KEYCLOAK_JACCLOUD_USERNAME must be set}"
: "${KEYCLOAK_JACCLOUD_PASSWORD:?KEYCLOAK_JACCLOUD_PASSWORD must be set}"

KEYCLOAK_TOKEN_URL="${SSO_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"
SUPPORT_REQUEST_URL="${KONG_PUBLIC_URL%/}/api/system/v1/support/requests"
KEYCLOAK_USERNAME="$KEYCLOAK_JACCLOUD_USERNAME"
KEYCLOAK_PASSWORD="$KEYCLOAK_JACCLOUD_PASSWORD"
KEYCLOAK_CLIENT_ID="$VITE_KEYCLOAK_CLIENT_ID"
REQUEST_TITLE="${REQUEST_TITLE:-Operations assistance request by mail}"
REQUEST_MESSAGE="${REQUEST_MESSAGE:-Please assist with the current operations assistance scenario.}"
REQUEST_SOURCE="${REQUEST_SOURCE:-copilot}"
REQUEST_REFERENCE_ID="${REQUEST_REFERENCE_ID:-SUP-COPILOT-$(date -u +%Y%m%d%H%M%S)}"
KONG_REQUEST_ID="${KONG_REQUEST_ID:-copilot-$(date -u +%Y%m%d%H%M%S%6N)}"
CORRELATION_ID="${CORRELATION_ID:-copilot-$(date -u +%Y%m%d%H%M%S%6N)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [ -f "$KONG_CA_CERT" ] && [ -z "${CURL_CA_BUNDLE:-}" ]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

if [ -z "${KONG_PUBLIC_URL:-}" ]; then
  error "validate_support_request_by_mail.sh" "KONG_PUBLIC_URL must be set to the public Kong URL used by the UI"
  exit 1
fi

python_bin=${PYTHON_BIN:-$ROOT_DIR/venv/bin/python}

if ! command -v curl >/dev/null 2>&1; then
  error "validate_support_request_by_mail.sh" "curl is required"
  exit 127
fi

if [ ! -x "$python_bin" ]; then
  error "validate_support_request_by_mail.sh" "Python executable not found: $python_bin"
  exit 127
fi

request_response_file=$(mktemp)
trap 'rm -f "$request_response_file"' EXIT

access_token="$(dq_keycloak_password_grant_access_token "$KEYCLOAK_TOKEN_URL" "$KEYCLOAK_CLIENT_ID" "$KEYCLOAK_USERNAME" "$KEYCLOAK_PASSWORD" -k)"

support_payload=$(
  REQUEST_TITLE_VALUE="$REQUEST_TITLE" \
  REQUEST_MESSAGE_VALUE="$REQUEST_MESSAGE" \
  REQUEST_SOURCE_VALUE="$REQUEST_SOURCE" \
  REQUEST_REFERENCE_ID_VALUE="$REQUEST_REFERENCE_ID" \
  "$PYTHON_RUNNER" --python-bin "$python_bin" -c '
import json
import os

print(
    json.dumps(
        {
            "title": os.environ["REQUEST_TITLE_VALUE"],
            "message": os.environ["REQUEST_MESSAGE_VALUE"],
            "source": os.environ["REQUEST_SOURCE_VALUE"],
            "reference_id": os.environ["REQUEST_REFERENCE_ID_VALUE"],
        },
        ensure_ascii=False,
    )
)
'
)

set +e
request_http_code=$(curl -sS \
  -o "$request_response_file" \
  -w '%{http_code}' \
  -X POST "$SUPPORT_REQUEST_URL" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $access_token" \
  -H "X-Kong-Request-Id: $KONG_REQUEST_ID" \
  -H "X-Correlation-ID: $CORRELATION_ID" \
  --data "$support_payload")
request_curl_rc=$?
set -e

response_body=$(cat "$request_response_file")

info "validate_support_request_by_mail.sh" "Reference ID: $REQUEST_REFERENCE_ID"
info "validate_support_request_by_mail.sh" "Kong request ID: $KONG_REQUEST_ID"
info "validate_support_request_by_mail.sh" "Correlation ID: $CORRELATION_ID"
info "validate_support_request_by_mail.sh" "HTTP status: $request_http_code"
info "validate_support_request_by_mail.sh" "Curl rc: $request_curl_rc"
info "validate_support_request_by_mail.sh" "Response:"
printf '%s\n' "$response_body"

if [ "$request_curl_rc" -ne 0 ]; then
  error "validate_support_request_by_mail.sh" "support request curl failed with rc=$request_curl_rc"
  exit "$request_curl_rc"
fi

if [ "$request_http_code" -ge 400 ]; then
  error "validate_support_request_by_mail.sh" "support request returned HTTP $request_http_code"
  exit 1
fi

success "validate_support_request_by_mail.sh" "operations assistance email validation passed"