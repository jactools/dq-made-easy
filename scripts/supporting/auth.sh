# Purpose: Canonical entrypoint for shared shell auth helpers.
#
# What it does:
# - Sources seeded user credentials into the current shell on request.
# - Mints Keycloak access tokens for validation scripts and seeded-user automation.
# - Fails fast when auth dependencies or credentials are missing.
#
# Version: 1.1
# Last modified: 2026-06-11

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/env/selection.sh"

dq_source_seeded_user_credentials() {
  # shellcheck disable=SC1090
  source "$ROOT_DIR/scripts/load_seeded_user_credentials.sh" "$@"
}

dq_keycloak_seeded_user_access_token() {
  local token_url="$1"
  local client_id="$2"
  local username="$3"
  local password="$4"

  if [ -z "$token_url" ] || [ -z "$client_id" ] || [ -z "$username" ] || [ -z "$password" ]; then
    error "auth.sh" "token_url, client_id, username, and password are required"
    return 1
  fi

  dq_keycloak_password_grant_access_token "$token_url" "$client_id" "$username" "$password"
}

dq_keycloak_password_grant_access_token() {
  local token_url="$1"
  local client_id="$2"
  local username="$3"
  local password="$4"
  shift 4

  local curl_cmd=(curl)
  if [ "$#" -gt 0 ]; then
    curl_cmd+=("$@")
  fi
  local response_file
  local http_code
  local curl_rc
  local access_token

  if ! command -v curl >/dev/null 2>&1; then
    error "auth.sh" "curl is required"
    return 127
  fi

  if ! command -v jq >/dev/null 2>&1; then
    error "auth.sh" "jq is required"
    return 127
  fi

  response_file="$(mktemp)"

  set +e
  http_code=$("${curl_cmd[@]}" \
    -sS \
    -o "$response_file" \
    -w '%{http_code}' \
    -X POST "$token_url" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'grant_type=password' \
    --data-urlencode "client_id=$client_id" \
    --data-urlencode "username=$username" \
    --data-urlencode "password=$password")
  curl_rc=$?
  set -e

  if [ "$curl_rc" -ne 0 ]; then
    error "auth.sh" "Keycloak token request failed with rc=$curl_rc"
    cat "$response_file" >&2 || true
    rm -f "$response_file"
    return "$curl_rc"
  fi

  if [ "$http_code" -ge 400 ]; then
    error "auth.sh" "Keycloak token request returned HTTP $http_code"
    cat "$response_file" >&2 || true
    rm -f "$response_file"
    return 1
  fi

  access_token="$(jq -r '.access_token // empty' "$response_file" 2>/dev/null || true)"
  rm -f "$response_file"

  if [ -z "$access_token" ]; then
    error "auth.sh" "Keycloak token response did not include access_token"
    return 1
  fi

  printf '%s' "$access_token"
}

dq_keycloak_client_credentials_access_token() {
  local token_url="$1"
  local client_id="$2"
  local client_secret="$3"
  shift 3

  local curl_cmd=(curl)
  if [ "$#" -gt 0 ]; then
    curl_cmd+=("$@")
  fi
  local response_file
  local http_code
  local curl_rc
  local access_token

  if ! command -v curl >/dev/null 2>&1; then
    error "auth.sh" "curl is required"
    return 127
  fi

  if ! command -v jq >/dev/null 2>&1; then
    error "auth.sh" "jq is required"
    return 127
  fi

  response_file="$(mktemp)"

  set +e
  http_code=$("${curl_cmd[@]}" \
    -sS \
    -o "$response_file" \
    -w '%{http_code}' \
    -X POST "$token_url" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'grant_type=client_credentials' \
    --data-urlencode "client_id=$client_id" \
    --data-urlencode "client_secret=$client_secret")
  curl_rc=$?
  set -e

  if [ "$curl_rc" -ne 0 ]; then
    error "auth.sh" "Keycloak token request failed with rc=$curl_rc"
    cat "$response_file" >&2 || true
    rm -f "$response_file"
    return "$curl_rc"
  fi

  if [ "$http_code" -ge 400 ]; then
    error "auth.sh" "Keycloak token request returned HTTP $http_code"
    cat "$response_file" >&2 || true
    rm -f "$response_file"
    return 1
  fi

  access_token="$(jq -r '.access_token // empty' "$response_file" 2>/dev/null || true)"
  rm -f "$response_file"

  if [ -z "$access_token" ]; then
    error "auth.sh" "Keycloak token response did not include access_token"
    return 1
  fi

  printf '%s' "$access_token"
}
