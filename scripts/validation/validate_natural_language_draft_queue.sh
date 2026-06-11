#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate natural-language draft queue backlog and events appear in Grafana.
#
# What it does:
# - Requires the API, Kong, Redis, Grafana, and Prometheus containers to already be running.
# - Uses the shared auth helper to mint a seeded user token and Grafana cookie.
# - Queues an LLM-backed preview, then enqueues a burst of LLM-backed draft requests through Kong.
# - Verifies each returned request can be read back by request id and checks the enqueue event counter.
#
# validate: groups=api,observability
# Version: 1.1
# Last modified: 2026-05-11

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/grafana_oauth_session.sh"

my_name="validate_natural_language_draft_queue.sh"

dq_source_seeded_user_credentials --quiet

REQUESTER_EMAIL="${KEYCLOAK_JACCLOUD_USERNAME:?KEYCLOAK_JACCLOUD_USERNAME must be set}"
REQUESTER_PASSWORD="${KEYCLOAK_JACCLOUD_PASSWORD:?KEYCLOAK_JACCLOUD_PASSWORD must be set}"

: "${KONG_PUBLIC_URL:?KONG_PUBLIC_URL must be set to the public Kong URL used by the UI}"
: "${GRAFANA_PUBLIC_URL:?GRAFANA_PUBLIC_URL must be set}"
: "${GRAFANA_ADMIN_USER:?GRAFANA_ADMIN_USER must be set}"
: "${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD must be set}"
: "${SSO_PUBLIC_ISSUER_URL:?SSO_PUBLIC_ISSUER_URL must be set}"
: "${VITE_KEYCLOAK_CLIENT_ID:?VITE_KEYCLOAK_CLIENT_ID must be set}"

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [[ -f "$KONG_CA_CERT" && -z "${CURL_CA_BUNDLE:-}" ]]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: ${cmd}"
    exit 2
  fi
}

require_running_service() {
  local service_name="$1"
  local container_name

  container_name="$(docker ps --filter "label=com.docker.compose.service=${service_name}" --filter 'status=running' --format '{{.Names}}' | head -1)"
  if [[ -z "$container_name" ]]; then
    error "$my_name" "${service_name} must already be running; start the stack separately before running this validation"
    exit 1
  fi
}

wait_for_http_200() {
  local url="$1"
  local label="$2"
  local attempt
  local code

  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" || true)"
    if [[ "$code" == "200" ]]; then
      return 0
    fi
    info "$my_name" "Waiting for ${label} to report HTTP 200 (current=${code:-unknown})"
    sleep 2
  done

  error "$my_name" "${label} did not report HTTP 200 at ${url}"
  exit 1
}

api_request_with_token() {
  local token="$1"
  local method="$2"
  local endpoint="$3"
  local body="${4-}"
  local response_file
  local headers_file
  local response_code
  local curl_rc

  response_file="$(mktemp)"
  headers_file="$(mktemp)"

  set +e
  if [[ -n "$body" ]]; then
    response_code="$(curl -sS \
      -D "$headers_file" \
      -o "$response_file" \
      -w '%{http_code}' \
      -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" \
      -H "Authorization: Bearer ${token}" \
      -H 'Content-Type: application/json' \
      -d "$body")"
  else
    response_code="$(curl -sS \
      -D "$headers_file" \
      -o "$response_file" \
      -w '%{http_code}' \
      -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" \
      -H "Authorization: Bearer ${token}")"
  fi
  curl_rc=$?
  set -e

  if [[ "$curl_rc" -ne 0 ]]; then
    error "$my_name" "HTTP ${method} ${endpoint} failed with rc=${curl_rc}"
    cat "$headers_file" >&2 || true
    cat "$response_file" >&2 || true
    rm -f "$response_file" "$headers_file"
    exit "$curl_rc"
  fi

  HTTP_CODE="$response_code"
  HTTP_BODY="$(cat "$response_file")"
  rm -f "$response_file" "$headers_file"
}

prom_query_value() {
  local grafana_url="$1"
  local cookie_header="$2"
  local datasource_uid="$3"
  local query="$4"
  local response

  if ! response="$(curl -sS -H "Cookie: ${cookie_header}" --get --data-urlencode "query=${query}" "${grafana_url}/api/datasources/proxy/uid/${datasource_uid}/api/v1/query")"; then
    error "$my_name" "Prometheus query request failed for: ${query}"
    return 1
  fi

  if ! jq -e '.status == "success"' >/dev/null 2>&1 <<<"$response"; then
    error "$my_name" "Unexpected Prometheus response for query: ${query}"
    printf '%s\n' "$response" >&2
    return 1
  fi

  jq -r '.data.result[0].value[1] // "0"' <<<"$response"
}

wait_for_metric_increase() {
  local grafana_url="$1"
  local cookie_header="$2"
  local datasource_uid="$3"
  local query="$4"
  local baseline_value="$5"
  local label="$6"
  local current_value
  local attempt

  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
    current_value="$(prom_query_value "$grafana_url" "$cookie_header" "$datasource_uid" "$query")"
    if awk -v baseline="$baseline_value" -v current="$current_value" 'BEGIN { exit !((current + 0) > (baseline + 0)) }'; then
      printf '%s\n' "$current_value"
      return 0
    fi
    sleep 1
  done

  error "$my_name" "${label} did not increase"
  return 1
}

wait_for_positive_metric() {
  local grafana_url="$1"
  local cookie_header="$2"
  local datasource_uid="$3"
  local query="$4"
  local label="$5"
  local current_value
  local attempt

  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
    current_value="$(prom_query_value "$grafana_url" "$cookie_header" "$datasource_uid" "$query")"
    if awk -v value="$current_value" 'BEGIN { exit !((value + 0) > 0) }'; then
      printf '%s\n' "$current_value"
      return 0
    fi
    sleep 1
  done

  error "$my_name" "${label} did not become positive"
  return 1
}

build_preview_payload() {
  local prompt="$1"

  jq -nc \
    --arg prompt "$prompt" \
    --arg current_workspace_id "retail-banking" \
    '{
      prompt: $prompt,
      search_scope: "current",
      current_workspace_id: $current_workspace_id,
      analysis_provider: "llm"
    }'
}

build_create_payload() {
  local prompt="$1"
  local selected_attribute_ids_json="$2"

  jq -nc \
    --arg prompt "$prompt" \
    --arg current_workspace_id "retail-banking" \
    --argjson selected_attribute_ids "$selected_attribute_ids_json" \
    '{
      prompt: $prompt,
      search_scope: "current",
      current_workspace_id: $current_workspace_id,
      analysis_provider: "llm",
      selected_attribute_ids: $selected_attribute_ids
    }'
}

require_cmd docker
require_cmd curl
require_cmd jq

for service_name in api kong redis grafana prometheus; do
  require_running_service "$service_name"
done

wait_for_http_200 "${KONG_PUBLIC_URL%/}/health" "api health"

TOKEN_ENDPOINT="${SSO_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"
ACCESS_TOKEN="$(dq_keycloak_password_grant_access_token "$TOKEN_ENDPOINT" "$VITE_KEYCLOAK_CLIENT_ID" "$REQUESTER_EMAIL" "$REQUESTER_PASSWORD")"

GRAFANA_URL="${GRAFANA_PUBLIC_URL%/}"
GRAFANA_COOKIE_HEADER="$(grafana_validation_cookie_header "$ROOT_DIR" "$GRAFANA_URL" "$GRAFANA_ADMIN_USER" "$GRAFANA_ADMIN_PASSWORD")"

prometheus_uid=""
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  prometheus_uid="$(curl -sS -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/name/Prometheus" | jq -r '.uid // empty')"
  if [[ -n "$prometheus_uid" ]]; then
    break
  fi
  info "$my_name" "Waiting for Grafana Prometheus datasource UID"
  sleep 2
done

if [[ -z "$prometheus_uid" ]]; then
  error "$my_name" "Could not resolve Grafana Prometheus datasource uid"
  exit 1
fi

run_token="$(date -u +%Y%m%d%H%M%S)-${RANDOM}${RANDOM}"

preview_prompt="Suggest the most appropriate DQ rule for customer_id ${run_token}"
preview_payload="$(build_preview_payload "$preview_prompt")"

api_request_with_token "$ACCESS_TOKEN" POST "/data-catalog/v1/suggestions/natural-language-rule-previews" "$preview_payload"
if [[ "$HTTP_CODE" != "200" ]]; then
  error "$my_name" "Preview request returned HTTP ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

if [[ "$(jq -r '.success // false' <<<"$HTTP_BODY")" != "true" ]]; then
  error "$my_name" "Preview response did not report success"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

if [[ "$(jq -r '.queued // false' <<<"$HTTP_BODY")" != "true" ]]; then
  error "$my_name" "LLM preview request was not queued"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

if [[ -z "$(jq -r '.request_id // empty' <<<"$HTTP_BODY")" ]]; then
  error "$my_name" "LLM preview request did not return a request id"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

selected_attribute_ids_json='["attr-retail-customer-id"]'

events_query='sum(increase(dq_natural_language_draft_request_events_total{stage="enqueue",result="success",analysis_provider="llm"}[5m]))'
baseline_events="$(prom_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$events_query")"

request_prompt_prefix="Suggest the most appropriate DQ rule for customer_id ${run_token}"
request_count=10
request_ids=()
info "$my_name" "Creating ${request_count} natural-language draft requests"
for request_index in $(seq 1 "$request_count"); do
  request_prompt="${request_prompt_prefix} #${request_index}"
  create_payload="$(build_create_payload "$request_prompt" "$selected_attribute_ids_json")"

  api_request_with_token "$ACCESS_TOKEN" POST "/data-catalog/v1/suggestions/natural-language-rule-previews/create-suggestion" "$create_payload"
  if [[ "$HTTP_CODE" != "200" ]]; then
    error "$my_name" "Create-suggestion request ${request_index} returned HTTP ${HTTP_CODE}"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi

  if [[ "$(jq -r '.success // false' <<<"$HTTP_BODY")" != "true" ]]; then
    error "$my_name" "Create-suggestion request ${request_index} did not report success"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi

  if [[ "$(jq -r '.queued // false' <<<"$HTTP_BODY")" != "true" ]]; then
    error "$my_name" "Create-suggestion request ${request_index} was not queued"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi

  request_id="$(jq -r '.request_id // empty' <<<"$HTTP_BODY")"
  if [[ -z "$request_id" ]]; then
    error "$my_name" "Create-suggestion request ${request_index} did not return a request id"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi
  request_ids+=("$request_id")
done

for request_id in "${request_ids[@]}"; do
  api_request_with_token "$ACCESS_TOKEN" GET "/data-catalog/v1/suggestions/natural-language-rule-previews/requests/${request_id}/status"
  if [[ "$HTTP_CODE" != "200" ]]; then
    error "$my_name" "Request status lookup for ${request_id} returned HTTP ${HTTP_CODE}"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi

  if [[ "$(jq -r '.success // false' <<<"$HTTP_BODY")" != "true" ]]; then
    error "$my_name" "Request status lookup for ${request_id} did not report success"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi

  if [[ "$(jq -r '.request.prompt // empty' <<<"$HTTP_BODY")" != "${request_prompt_prefix}"* ]]; then
    error "$my_name" "Request status lookup for ${request_id} did not return the expected prompt prefix"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi
done

post_events="$(wait_for_metric_increase "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$events_query" "$baseline_events" "Natural-language draft enqueue events")"

info "$my_name" "Final Grafana evidence"
info "$my_name" "- enqueue_events_5m=${post_events}"
info "$my_name" "- matching_requests=${request_count}"

success "$my_name" "Natural-language draft queue validation passed"
