#!/usr/bin/env bash

# Purpose: Provide shared OpenMetadata automation helpers.
#
# What it does:
# - Uses the shared auth helper to mint an OM_TOKEN from the selected seeded Keycloak credentials.
# - Validates that the resulting token is authorized against the OpenMetadata API.
# - Fails fast when required OpenMetadata or SSO inputs are missing.
#
# Version: 1.3
# Last modified: 2026-06-30
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/readiness.sh"

wait_for_openmetadata_public_ready() {
  local api_base_url="${OPENMETADATA_PUBLIC_URL:-}"
  local ready_url
  local host
  local port
  local probe_target="127.0.0.1"

  if [ -z "$api_base_url" ]; then
    error "openmetadata.sh" "OPENMETADATA_PUBLIC_URL is required to wait for OpenMetadata readiness"
    return 1
  fi

  info "openmetadata.sh" "Waiting for OpenMetadata public API to become ready at $api_base_url..."
  ready_url="${api_base_url%/}/api/v1/system/version"

  host="$(printf '%s' "$api_base_url" | sed -E 's#^[a-zA-Z][a-zA-Z0-9+.-]*://([^/:]+).*$#\1#')"
  if [ -z "$host" ] || [ "$host" = "$api_base_url" ]; then
    error "openmetadata.sh" "Unable to derive OpenMetadata hostname from OPENMETADATA_PUBLIC_URL=${api_base_url}"
    return 1
  fi

  port="$(printf '%s' "$api_base_url" | sed -nE 's#^[a-zA-Z][a-zA-Z0-9+.-]*://[^/:]+:([0-9]+).*$#\1#p')"
  if [ -z "$port" ]; then
    case "$api_base_url" in
      http://*) port="80" ;;
      https://*) port="443" ;;
      *) port="443" ;;
    esac
  fi

  wait_for_http_ready "OpenMetadata" "$ready_url" "200" 120 1 curl -ks --resolve "${host}:${port}:${probe_target}" -o /dev/null -w '%{http_code}'
}

validate_openmetadata_authorization() {
  local api_base_url="${OPENMETADATA_PUBLIC_URL:-}"
  local probe_url
  local probe_code
  local host
  local port
  local probe_target="127.0.0.1"

  if [ -z "$api_base_url" ]; then
    error "openmetadata.sh" "OPENMETADATA_PUBLIC_URL is required to validate OpenMetadata authorization"
    return 1
  fi

  if [ -z "${OM_TOKEN:-}" ]; then
    error "openmetadata.sh" "OM_TOKEN is required to validate OpenMetadata authorization"
    return 1
  fi

  probe_url="${api_base_url%/}/api/v1/system/version"
  host="$(printf '%s' "$api_base_url" | sed -E 's#^[a-zA-Z][a-zA-Z0-9+.-]*://([^/:]+).*$#\1#')"
  if [ -z "$host" ] || [ "$host" = "$api_base_url" ]; then
    error "openmetadata.sh" "Unable to derive OpenMetadata hostname from OPENMETADATA_PUBLIC_URL=${api_base_url}"
    return 1
  fi

  port="$(printf '%s' "$api_base_url" | sed -nE 's#^[a-zA-Z][a-zA-Z0-9+.-]*://[^/:]+:([0-9]+).*$#\1#p')"
  if [ -z "$port" ]; then
    case "$api_base_url" in
      http://*) port="80" ;;
      https://*) port="443" ;;
      *) port="443" ;;
    esac
  fi

  probe_code="$(curl -ks --resolve "${host}:${port}:${probe_target}" -o /dev/null -w '%{http_code}' "$probe_url" -H "Authorization: Bearer ${OM_TOKEN}" || true)"
  if [ "$probe_code" != "200" ]; then
    error "openmetadata.sh" "Prepared OM_TOKEN was not authorized by OpenMetadata (HTTP ${probe_code})"
    return 1
  fi
}

prepare_openmetadata_access_token() {
  local om_provider="${OM_AUTHENTICATION_PROVIDER:-custom-oidc}"
  # Construct a direct localhost token URL to avoid DNS resolution issues
  # and Kong proxy overhead when running outside containers.
  local kc_host_port="${KEYCLOAK_HTTPS_HOST_PORT:-9444}"
  local token_url="https://127.0.0.1:${kc_host_port}/realms/${KEYCLOAK_REALM:-jaccloud}"
  local client_id="${OM_AUTHENTICATION_CLIENT_ID:-openmetadata}"
  local seed_username="${OPENMETADATA_OIDC_SEED_USERNAME:-}"
  local seed_password="${OPENMETADATA_OIDC_SEED_PASSWORD:-}"

  if [ "$om_provider" != "custom-oidc" ]; then
    return 0
  fi

  if [ -n "${OM_TOKEN:-}" ]; then
    info "openmetadata.sh" "Using preconfigured OM_TOKEN for OpenMetadata automation"
    return 0
  fi

  if ! wait_for_openmetadata_public_ready; then
    error "openmetadata.sh" "OpenMetadata public API did not become ready"
    return 1
  fi

  # Try password grant with seeded user credentials (dq-admin).
  # This creates a token for a real OpenMetadata user that can perform
  # admin operations (create users, seed data) unlike a service account
  # token which has no user entity in OpenMetadata.
  if [ -z "${ROOT_DIR:-}" ] || [ ! -f "$ROOT_DIR/scripts/load_seeded_user_credentials.sh" ]; then
    error "openmetadata.sh" "ROOT_DIR must point at the repo root so seeded OpenMetadata credentials can be refreshed"
    return 1
  fi

  # shellcheck disable=SC1090
  source "$ROOT_DIR/scripts/load_seeded_user_credentials.sh" --quiet || {
    error "openmetadata.sh" "Failed to refresh seeded OpenMetadata credentials"
    return 1
  }

  seed_username="${OPENMETADATA_OIDC_SEED_USERNAME:-}"
  seed_password="${OPENMETADATA_OIDC_SEED_PASSWORD:-}"

  if [ -z "$seed_username" ] || [ -z "$seed_password" ]; then
    error "openmetadata.sh" "OpenMetadata seed credentials are missing; cannot prepare OM_TOKEN"
    return 1
  fi

  info "openmetadata.sh" "Preparing OpenMetadata OM_TOKEN via password grant (fallback)..."
  OM_TOKEN="$(CURL_CA_BUNDLE= SSL_CERT_FILE= REQUESTS_CA_BUNDLE= dq_keycloak_seeded_user_access_token "${token_url%/}/protocol/openid-connect/token" "$client_id" "$seed_username" "$seed_password" -k)" || {
    error "openmetadata.sh" "Failed to prepare OpenMetadata OM_TOKEN"
    return 1
  }

  export OM_TOKEN
  validate_openmetadata_authorization || return 1
  info "openmetadata.sh" "✓ Prepared OpenMetadata OM_TOKEN for $seed_username"
}