#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate that a global admin can see workspace JIT access requests in the admin API.
# What it does:
# - Loads the selected root env and seeded credentials for requester and global admin users.
# - Creates a new exception-fact access request in a target workspace as the requester.
# - Verifies the global admin can list that pending request through /admin/v1/exception-fact-access-requests.
# - Cleans up by rejecting the created request so repeated runs remain stable.
# validate: groups=api,regression
# Version: 1.0
# Last modified: 2026-06-01

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MY_NAME="validate_global_admin_access_request_visibility.sh"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

print_usage() {
  cat <<'EOF'
Usage: scripts/validate_global_admin_access_request_visibility.sh [--workspace-id ID]

Options:
  --workspace-id ID   Workspace id to validate (default: retail-banking)
  -h, --help          Show this help

Environment selection flags (forwarded):
  --env dev|test|prod
  --env-file PATH
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "$MY_NAME" "Missing required command: ${cmd}"
    exit 127
  fi
}

api_request_with_token() {
  local token="$1"
  local method="$2"
  local endpoint="$3"
  local body="${4-}"
  local response
  local curl_rc

  set +e
  if [[ -n "$body" ]]; then
    response="$(curl -sS -w $'\n%{http_code}' -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" \
      -H "Authorization: Bearer ${token}" \
      -H 'Content-Type: application/json' \
      -d "$body")"
  else
    response="$(curl -sS -w $'\n%{http_code}' -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" \
      -H "Authorization: Bearer ${token}")"
  fi
  curl_rc=$?
  set -e

  if [[ "$curl_rc" -ne 0 ]]; then
    error "$MY_NAME" "HTTP ${method} ${endpoint} failed with rc=${curl_rc}"
    exit "$curl_rc"
  fi

  HTTP_CODE="$(printf '%s' "$response" | tail -n1)"
  HTTP_BODY="$(printf '%s' "$response" | sed '$d')"
}

mint_access_token() {
  local username="$1"
  local password="$2"
  local token_endpoint

  token_endpoint="${SSO_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"
  dq_keycloak_password_grant_access_token "$token_endpoint" "$VITE_KEYCLOAK_CLIENT_ID" "$username" "$password"
}

WORKSPACE_ID="retail-banking"

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 2
fi

set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace-id)
      if [[ $# -lt 2 ]]; then
        error "$MY_NAME" "--workspace-id requires a value"
        exit 2
      fi
      WORKSPACE_ID="$2"
      shift 2
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      error "$MY_NAME" "Unknown argument: $1"
      print_usage
      exit 2
      ;;
  esac
done

validate_selected_root_env_file "$ROOT_DIR" full
if ! source_selected_root_env_file; then
  exit 1
fi

dq_source_seeded_user_credentials --env-file "$ROOT_ENV_FILE" --quiet

require_cmd curl
require_cmd jq

: "${KONG_PUBLIC_URL:?KONG_PUBLIC_URL must be set}"
: "${SSO_PUBLIC_ISSUER_URL:?SSO_PUBLIC_ISSUER_URL must be set}"
: "${VITE_KEYCLOAK_CLIENT_ID:?VITE_KEYCLOAK_CLIENT_ID must be set}"
: "${KEYCLOAK_JACCLOUD_USERNAME:?KEYCLOAK_JACCLOUD_USERNAME must be set}"
: "${KEYCLOAK_JACCLOUD_PASSWORD:?KEYCLOAK_JACCLOUD_PASSWORD must be set}"
: "${SMOKE_LOGIN_EMAIL:?SMOKE_LOGIN_EMAIL must be set}"
: "${SMOKE_LOGIN_PASSWORD:?SMOKE_LOGIN_PASSWORD must be set}"

if [[ "$KEYCLOAK_JACCLOUD_USERNAME" == "$SMOKE_LOGIN_EMAIL" ]]; then
  error "$MY_NAME" "Requester and admin credentials must differ"
  exit 1
fi

REQUESTER_TOKEN="$(mint_access_token "$KEYCLOAK_JACCLOUD_USERNAME" "$KEYCLOAK_JACCLOUD_PASSWORD")"
ADMIN_TOKEN="$(mint_access_token "$SMOKE_LOGIN_EMAIL" "$SMOKE_LOGIN_PASSWORD")"

REQUEST_ID=""
cleanup() {
  if [[ -z "$REQUEST_ID" ]]; then
    return 0
  fi

  local cleanup_payload
  cleanup_payload="$(jq -nc '{status: "rejected", comments: "validation cleanup"}')"
  set +e
  api_request_with_token "$ADMIN_TOKEN" PUT "/admin/v1/exception-fact-access-requests/${REQUEST_ID}" "$cleanup_payload"
  set -e
}
trap cleanup EXIT

REQUEST_COMMENTS="global-admin-visibility-validation-$(date +%s)"
CREATE_PAYLOAD="$(jq -nc \
  --arg workspace_id "$WORKSPACE_ID" \
  --arg role_id "exception-fact-reader" \
  --arg comments "$REQUEST_COMMENTS" \
  '{workspace_id: $workspace_id, role_id: $role_id, requested_duration_minutes: 30, comments: $comments}')"

info "$MY_NAME" "Creating request in workspace=${WORKSPACE_ID} as ${KEYCLOAK_JACCLOUD_USERNAME}"
api_request_with_token "$REQUESTER_TOKEN" POST "/admin/v1/exception-fact-access-requests" "$CREATE_PAYLOAD"
if [[ "$HTTP_CODE" != "200" ]]; then
  error "$MY_NAME" "POST /admin/v1/exception-fact-access-requests returned HTTP ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

REQUEST_ID="$(printf '%s' "$HTTP_BODY" | jq -r '.id // empty')"
if [[ -z "$REQUEST_ID" ]]; then
  error "$MY_NAME" "Created request response did not include id"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

info "$MY_NAME" "Listing requests as global admin ${SMOKE_LOGIN_EMAIL}"
api_request_with_token "$ADMIN_TOKEN" GET "/admin/v1/exception-fact-access-requests?workspaceId=${WORKSPACE_ID}"
if [[ "$HTTP_CODE" != "200" ]]; then
  error "$MY_NAME" "GET /admin/v1/exception-fact-access-requests returned HTTP ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

FOUND_ID="$(printf '%s' "$HTTP_BODY" | jq -r --arg request_id "$REQUEST_ID" '.[] | select(.id == $request_id) | .id' | tail -1)"
FOUND_STATUS="$(printf '%s' "$HTTP_BODY" | jq -r --arg request_id "$REQUEST_ID" '.[] | select(.id == $request_id) | .status' | tail -1)"

if [[ -z "$FOUND_ID" ]]; then
  error "$MY_NAME" "Global admin could not see the newly created request ${REQUEST_ID} in workspace ${WORKSPACE_ID}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

if [[ "$FOUND_STATUS" != "pending" ]]; then
  error "$MY_NAME" "Request ${REQUEST_ID} is ${FOUND_STATUS:-missing} instead of pending"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

success "$MY_NAME" "Global admin visibility confirmed for request ${REQUEST_ID} in workspace ${WORKSPACE_ID}"
