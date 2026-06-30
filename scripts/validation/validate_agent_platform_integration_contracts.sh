#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate WS10-AC04 — external agent platform integration contracts
#          are accessible and operational on a live stack.
# What it does:
# - Authenticates as a seeded admin user and a rules-writer user.
# - Calls GET /agent/v1/integrations/contracts and asserts the initial allow-listed
#   platforms (mistral_ai, microsoft_copilot) are present with documented contracts.
# - Calls POST /agent/v1/integrations/dispatches with a Mistral AI webhook payload
#   and asserts a dispatch_id and accepted status are returned.
# - Calls GET /agent/v1/audit/events and confirms the dispatch was audited.
# validate: groups=api,regression
# Version: 1.2
# Last modified: 2026-07-01

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

my_name="validate_agent_platform_integration_contracts.sh"
agent_type="mcp"
agent_source="dq-made-easy-mcp"
CONFIG_TOKEN=""
ORIGINAL_AGENT_ACCESS_POLICY=""

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  echo "Usage: $my_name [--env dev|test|prod] [--env-file PATH]" >&2
  exit 1
fi
set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

validate_selected_root_env_file "$ROOT_DIR" full

if ! source_selected_root_env_file; then
  exit 1
fi

dq_source_seeded_user_credentials --env-file "$ROOT_ENV_FILE" --quiet

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [[ -f "$KONG_CA_CERT" && -z "${CURL_CA_BUNDLE:-}" ]]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi
if [[ -f "$KONG_CA_CERT" && -z "${REQUESTS_CA_BUNDLE:-}" ]]; then
  export REQUESTS_CA_BUNDLE="$KONG_CA_CERT"
fi

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: ${cmd}"
    exit 2
  fi
}

require_cmd curl
require_cmd jq

# --------------------------------------------------------------------------
# Auth helpers
# --------------------------------------------------------------------------

mint_access_token() {
  local username="$1"
  local password="$2"
  local token_endpoint
  token_endpoint="${SSO_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"
  dq_keycloak_password_grant_access_token "$token_endpoint" "$VITE_KEYCLOAK_CLIENT_ID" "$username" "$password"
}

api_call() {
  local token="$1"
  local method="$2"
  local endpoint="$3"
  local body="${4-}"
  local response_file
  local headers_file
  local code
  local curl_rc

  response_file="$(mktemp "$ROOT_DIR/tmp/ac04_resp_XXXXXX.json")"
  headers_file="$(mktemp "$ROOT_DIR/tmp/ac04_hdr_XXXXXX.txt")"

  set +e
  if [[ -n "$body" ]]; then
    code="$(curl -sS \
      -D "$headers_file" \
      -o "$response_file" \
      -w '%{http_code}' \
      -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" \
      -H "Authorization: Bearer ${token}" \
      -H 'Content-Type: application/json' \
        -H "X-Agent-Type: ${agent_type}" \
        -H "X-Agent-Source: ${agent_source}" \
      -H "X-Request-Id: ac04-$(date +%s)" \
      -d "$body")"
  else
    code="$(curl -sS \
      -D "$headers_file" \
      -o "$response_file" \
      -w '%{http_code}' \
      -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" \
      -H "Authorization: Bearer ${token}" \
        -H "X-Agent-Type: ${agent_type}" \
        -H "X-Agent-Source: ${agent_source}" \
      -H "X-Request-Id: ac04-$(date +%s)")"
  fi
  curl_rc=$?
  set -e

  if [[ "$curl_rc" -ne 0 ]]; then
    error "$my_name" "curl failed (rc=${curl_rc}) for ${method} ${endpoint}"
    cat "$headers_file" >&2 || true
    cat "$response_file" >&2 || true
    rm -f "$response_file" "$headers_file"
    exit "$curl_rc"
  fi

  HTTP_CODE="$code"
  HTTP_BODY="$(cat "$response_file")"
  rm -f "$response_file" "$headers_file"
}

set_agent_access_policy() {
  local policy_json="$1"
  local payload

  payload="$(jq -nc --argjson agent_access_policy "$policy_json" '{agent_access_policy: $agent_access_policy}')"
  api_call "$CONFIG_TOKEN" PUT "/system/v1/app-config" "$payload"

  if [[ "$HTTP_CODE" != "200" ]]; then
    error "$my_name" "PUT /system/v1/app-config returned HTTP ${HTTP_CODE} while updating agent_access_policy"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi
}

restore_agent_access_policy() {
  if [[ -z "$CONFIG_TOKEN" || -z "$ORIGINAL_AGENT_ACCESS_POLICY" ]]; then
    return 0
  fi

  info "$my_name" "Restoring original agent_access_policy"
  set_agent_access_policy "$ORIGINAL_AGENT_ACCESS_POLICY"
}

cleanup() {
  set +e
  restore_agent_access_policy
  set -e
}

trap cleanup EXIT

mkdir -p "$ROOT_DIR/tmp"

# --------------------------------------------------------------------------
# Step 1 — Mint tokens
# --------------------------------------------------------------------------

info "$my_name" "Minting rules-writer token for dispatch calls"
rw_token="$(mint_access_token "$SMOKE_LOGIN_EMAIL" "$SMOKE_LOGIN_PASSWORD")"

admin_email="${KEYCLOAK_JACCLOUD_USERNAME:-$SMOKE_LOGIN_EMAIL}"
admin_password="${KEYCLOAK_JACCLOUD_PASSWORD:-$SMOKE_LOGIN_PASSWORD}"
info "$my_name" "Minting admin token for audit read"
admin_token="$(mint_access_token "$admin_email" "$admin_password")"

for candidate_token in "$rw_token" "$admin_token"; do
  api_call "$candidate_token" GET "/system/v1/app-config"
  if [[ "$HTTP_CODE" == "200" ]]; then
    CONFIG_TOKEN="$candidate_token"
    ORIGINAL_AGENT_ACCESS_POLICY="$(printf '%s' "$HTTP_BODY" | jq -c '.agent_access_policy // null')"
    break
  fi
done

if [[ -z "$CONFIG_TOKEN" ]]; then
  error "$my_name" "Could not read /system/v1/app-config with either seeded token"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

if [[ "$ORIGINAL_AGENT_ACCESS_POLICY" == "null" ]]; then
  ORIGINAL_AGENT_ACCESS_POLICY='{"default_action":"deny","allowed_agents":[]}'
fi

temp_allowed_agent_policy="$(jq -nc \
  --argjson original "$ORIGINAL_AGENT_ACCESS_POLICY" \
  --arg agent_type "$agent_type" \
  --arg agent_source "$agent_source" '
    ($original // {"default_action":"deny","allowed_agents":[]}) as $policy |
    {
      default_action: ($policy.default_action // "deny"),
      allowed_agents: (($policy.allowed_agents // []) + [{agent_type: $agent_type, agent_source: $agent_source}])
        | unique_by([.agent_type, .agent_source, .agent_instance_id, .request_origin])
    }
  ')"

set_agent_access_policy "$temp_allowed_agent_policy"

# --------------------------------------------------------------------------
# Step 2 — GET /agent/v1/integrations/contracts
# --------------------------------------------------------------------------

info "$my_name" "GET /agent/v1/integrations/contracts"
api_call "$rw_token" GET "/agent/v1/integrations/contracts"

if [[ "$HTTP_CODE" != "200" ]]; then
  error "$my_name" "GET /agent/v1/integrations/contracts returned HTTP ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

allowlisted_platforms="$(printf '%s' "$HTTP_BODY" | jq -r '.allowlisted_platforms[]')"
for required_platform in mistral_ai microsoft_copilot; do
  if ! printf '%s' "$allowlisted_platforms" | grep -q "^${required_platform}$"; then
    error "$my_name" "Expected platform '${required_platform}' not found in allowlisted_platforms"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi
  info "$my_name" "Platform '${required_platform}' is allowlisted — PASS"
done

contract_count="$(printf '%s' "$HTTP_BODY" | jq '.contracts | length')"
if [[ "$contract_count" -lt 2 ]]; then
  error "$my_name" "Expected at least 2 documented integration contracts, got ${contract_count}"
  exit 1
fi
info "$my_name" "Integration contracts documented: ${contract_count} — PASS"

# --------------------------------------------------------------------------
# Step 3 — POST /agent/v1/integrations/dispatches (Mistral AI webhook)
# --------------------------------------------------------------------------

dispatch_payload='{"platform":"mistral_ai","dispatch_mode":"webhook","event_type":"dq.alert.created","webhook_url":"https://example.invalid/hooks/dq-ac04","payload":{"delivery_id":"delivery-ac04","alert_kind":"sla_breach","rule_id":"rule-ac04"}}'

info "$my_name" "POST /agent/v1/integrations/dispatches (mistral_ai webhook)"
api_call "$rw_token" POST "/agent/v1/integrations/dispatches" "$dispatch_payload"

if [[ "$HTTP_CODE" != "200" ]]; then
  error "$my_name" "POST /agent/v1/integrations/dispatches returned HTTP ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

dispatch_id="$(printf '%s' "$HTTP_BODY" | jq -r '.dispatch_id // empty')"
dispatch_status="$(printf '%s' "$HTTP_BODY" | jq -r '.status // empty')"

if [[ -z "$dispatch_id" ]]; then
  error "$my_name" "dispatch_id missing from dispatch response"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi
if [[ "$dispatch_status" != "accepted" ]]; then
  error "$my_name" "Expected dispatch status 'accepted', got '${dispatch_status}'"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi
info "$my_name" "Dispatch accepted with id=${dispatch_id} — PASS"

# --------------------------------------------------------------------------
# Step 4 — Confirm dispatch was audited
# --------------------------------------------------------------------------

info "$my_name" "GET /agent/v1/audit/events — confirming dispatch audit record"
api_call "$admin_token" GET "/agent/v1/audit/events?limit=50&offset=0"

if [[ "$HTTP_CODE" != "200" ]]; then
  error "$my_name" "GET /agent/v1/audit/events returned HTTP ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

dispatch_audit_count="$(printf '%s' "$HTTP_BODY" | jq '[.events[] | select(.action == "dispatch_platform_integration")] | length')"
if [[ "$dispatch_audit_count" -lt 1 ]]; then
  error "$my_name" "No dispatch_platform_integration audit event found after dispatch"
  exit 1
fi
info "$my_name" "Dispatch audit event found (count=${dispatch_audit_count}) — PASS"

governance_aware="$(printf '%s' "$HTTP_BODY" | jq -r '.governance_metadata.governance_aware // "false"')"
if [[ "$governance_aware" != "true" ]]; then
  error "$my_name" "governance_metadata.governance_aware not true in audit response"
  exit 1
fi
info "$my_name" "Audit response carries governance_metadata.governance_aware=true — PASS"

# --------------------------------------------------------------------------
# Step 5 — Reject unallowlisted platform (negative contract check)
# --------------------------------------------------------------------------

bad_payload='{"platform":"github_copilot","dispatch_mode":"webhook","event_type":"dq.alert.created","webhook_url":"https://example.invalid/hooks/dq","payload":{}}'

info "$my_name" "POST /agent/v1/integrations/dispatches (unallowlisted platform — expecting 403)"
api_call "$rw_token" POST "/agent/v1/integrations/dispatches" "$bad_payload"

if [[ "$HTTP_CODE" != "403" ]]; then
  error "$my_name" "Expected HTTP 403 for unallowlisted platform, got ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi
info "$my_name" "Unallowlisted platform correctly rejected with HTTP 403 — PASS"

# --------------------------------------------------------------------------
# Done
# --------------------------------------------------------------------------

success "$my_name" "WS10-AC04 validation passed — external agent platform integration contracts are operational"
