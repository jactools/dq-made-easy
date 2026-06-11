#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate JIT access request metrics appear in Grafana.
# What it does:
# - Uses seeded requester and reviewer credentials through the shared auth helper.
# - Creates live JIT access requests through Kong and drives pending, approved, declined, and timed_out states.
# - Temporarily tightens the JIT timeout window through /system/v1/app-config and restores it afterward.
# - Verifies Grafana's Prometheus datasource sees the JIT request counters increase and leaves no pending request behind.
# validate: groups=api,observability
# Version: 1.1
# Last modified: 2026-05-10

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/grafana_oauth_session.sh"

my_name="validate_jit_access_requests.sh"

dq_source_seeded_user_credentials --quiet

REQUESTER_EMAIL="${KEYCLOAK_JACCLOUD_USERNAME:?KEYCLOAK_JACCLOUD_USERNAME must be set}"
REQUESTER_PASSWORD="${KEYCLOAK_JACCLOUD_PASSWORD:?KEYCLOAK_JACCLOUD_PASSWORD must be set}"
REVIEWER_EMAIL="${SMOKE_LOGIN_EMAIL:?SMOKE_LOGIN_EMAIL must be set}"
REVIEWER_PASSWORD="${SMOKE_LOGIN_PASSWORD:?SMOKE_LOGIN_PASSWORD must be set}"

if [[ "$REQUESTER_EMAIL" == "$REVIEWER_EMAIL" ]]; then
  error "$my_name" "Requester and reviewer credentials must differ"
  exit 1
fi

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

mint_access_token() {
  local username="$1"
  local password="$2"
  local token_endpoint

  token_endpoint="${SSO_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"
  dq_keycloak_password_grant_access_token "$token_endpoint" "$VITE_KEYCLOAK_CLIENT_ID" "$username" "$password"
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

grafana_query_value() {
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

build_request_payload() {
  local workspace_id="$1"
  local role_id="$2"
  local requested_duration_minutes="$3"
  local comments="$4"

  jq -nc \
    --arg workspace_id "$workspace_id" \
    --arg role_id "$role_id" \
    --arg comments "$comments" \
    --argjson requested_duration_minutes "$requested_duration_minutes" \
    '{
      workspace_id: $workspace_id,
      role_id: $role_id,
      requested_duration_minutes: $requested_duration_minutes,
      comments: $comments
    }'
}

create_request() {
  local token="$1"
  local workspace_id="$2"
  local role_id="$3"
  local requested_duration_minutes="$4"
  local comments="$5"
  local payload

  payload="$(build_request_payload "$workspace_id" "$role_id" "$requested_duration_minutes" "$comments")"
  api_request_with_token "$token" POST "/rulebuilder/v1/exception-fact-access-requests" "$payload"
  if [[ "$HTTP_CODE" != "200" ]]; then
    error "$my_name" "POST /rulebuilder/v1/exception-fact-access-requests returned HTTP ${HTTP_CODE}"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi

  jq -r '.id' <<<"$HTTP_BODY"
}

review_request() {
  local request_id="$1"
  local status="$2"
  local comments="$3"
  local payload

  payload="$(jq -nc --arg status "$status" --arg comments "$comments" '{status: $status, comments: $comments}')"
  api_request_with_token "$REVIEWER_TOKEN" PUT "/admin/v1/exception-fact-access-requests/${request_id}" "$payload"
  if [[ "$HTTP_CODE" != "200" ]]; then
    error "$my_name" "PUT /admin/v1/exception-fact-access-requests/${request_id} returned HTTP ${HTTP_CODE}"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi
}

get_app_config_timeout_minutes() {
  api_request_with_token "$REVIEWER_TOKEN" GET "/system/v1/app-config"
  if [[ "$HTTP_CODE" != "200" ]]; then
    error "$my_name" "GET /system/v1/app-config returned HTTP ${HTTP_CODE}"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi

  jq -r '.exception_fact_jit_request_timeout_minutes // empty' <<<"$HTTP_BODY"
}

set_app_config_timeout_minutes() {
  local timeout_minutes="$1"
  local payload

  payload="$(jq -nc --argjson timeout_minutes "$timeout_minutes" '{exception_fact_jit_request_timeout_minutes: $timeout_minutes}')"
  api_request_with_token "$REVIEWER_TOKEN" PUT "/system/v1/app-config" "$payload"
  if [[ "$HTTP_CODE" != "200" ]]; then
    error "$my_name" "PUT /system/v1/app-config returned HTTP ${HTTP_CODE}"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi
}

wait_for_request_status() {
  local request_id="$1"
  local expected_status="$2"
  local attempt
  local current_status

  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24; do
    api_request_with_token "$REQUESTER_TOKEN" GET "/rulebuilder/v1/exception-fact-access-requests"
    if [[ "$HTTP_CODE" != "200" ]]; then
      error "$my_name" "GET /rulebuilder/v1/exception-fact-access-requests returned HTTP ${HTTP_CODE}"
      printf '%s\n' "$HTTP_BODY" >&2
      exit 1
    fi

    current_status="$(jq -r --arg request_id "$request_id" '.[] | select(.id == $request_id) | .status' <<<"$HTTP_BODY" | tail -1)"
    if [[ "$current_status" == "$expected_status" ]]; then
      return 0
    fi

    info "$my_name" "Waiting for request ${request_id} to become ${expected_status} (current=${current_status:-missing})"
    sleep 5
  done

  error "$my_name" "Request ${request_id} did not become ${expected_status} in time"
  exit 1
}

wait_for_metric_thresholds() {
  local target_total="$1"
  local target_pending="$2"
  local target_approved="$3"
  local target_declined="$4"
  local target_timed_out="$5"
  local attempt
  local current_total
  local current_pending
  local current_approved
  local current_declined
  local current_timed_out

  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24; do
    current_total="$(grafana_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$PROMETHEUS_UID" 'sum(dq_exception_fact_jit_access_requests_total)')"
    current_pending="$(grafana_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$PROMETHEUS_UID" 'sum(dq_exception_fact_jit_access_requests_current{status="pending"})')"
    current_approved="$(grafana_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$PROMETHEUS_UID" 'sum(dq_exception_fact_jit_access_requests_current{status="approved"})')"
    current_declined="$(grafana_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$PROMETHEUS_UID" 'sum(dq_exception_fact_jit_access_requests_current{status="declined"})')"
    current_timed_out="$(grafana_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$PROMETHEUS_UID" 'sum(dq_exception_fact_jit_access_requests_current{status="timed_out"})')"

    if [[ "$current_total" -ge "$target_total" && "$current_pending" -ge "$target_pending" && "$current_approved" -ge "$target_approved" && "$current_declined" -ge "$target_declined" && "$current_timed_out" -ge "$target_timed_out" ]]; then
      return 0
    fi

    info "$my_name" "Waiting for Grafana JIT request counters to reach total=${target_total}, pending=${target_pending}, approved=${target_approved}, declined=${target_declined}, timed_out=${target_timed_out} (current total=${current_total}, pending=${current_pending}, approved=${current_approved}, declined=${current_declined}, timed_out=${current_timed_out})"
    sleep 5
  done

  error "$my_name" "Grafana JIT request counters did not reach the expected thresholds"
  exit 1
}

RESTORE_APP_CONFIG="false"
ORIGINAL_TIMEOUT_MINUTES=""
REQUESTER_TOKEN=""
REVIEWER_TOKEN=""
GRAFANA_URL=""
GRAFANA_COOKIE_HEADER=""
PROMETHEUS_UID=""

restore_app_config() {
  if [[ "$RESTORE_APP_CONFIG" != "true" || -z "$ORIGINAL_TIMEOUT_MINUTES" ]]; then
    return 0
  fi

  if [[ -z "$REVIEWER_TOKEN" ]]; then
    REVIEWER_TOKEN="$(mint_access_token "$REVIEWER_EMAIL" "$REVIEWER_PASSWORD")"
  fi

  info "$my_name" "Restoring /system/v1/app-config exception_fact_jit_request_timeout_minutes=${ORIGINAL_TIMEOUT_MINUTES}"
  set_app_config_timeout_minutes "$ORIGINAL_TIMEOUT_MINUTES"
  RESTORE_APP_CONFIG="false"
}

cleanup() {
  set +e
  restore_app_config
  set -e
}

trap cleanup EXIT

require_cmd curl
require_cmd docker
require_cmd jq

for service_name in api kong prometheus grafana; do
  require_running_service "$service_name"
done

wait_for_http_200 "${KONG_PUBLIC_URL%/}/health" "api health"

info "$my_name" "Requesting requester JWT for ${REQUESTER_EMAIL}"
REQUESTER_TOKEN="$(mint_access_token "$REQUESTER_EMAIL" "$REQUESTER_PASSWORD")"
info "$my_name" "Requesting reviewer JWT for ${REVIEWER_EMAIL}"
REVIEWER_TOKEN="$(mint_access_token "$REVIEWER_EMAIL" "$REVIEWER_PASSWORD")"

GRAFANA_URL="${GRAFANA_PUBLIC_URL%/}"
GRAFANA_COOKIE_HEADER="$(grafana_validation_cookie_header "$ROOT_DIR" "$GRAFANA_URL" "$GRAFANA_ADMIN_USER" "$GRAFANA_ADMIN_PASSWORD")"

PROMETHEUS_UID=""
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  PROMETHEUS_UID="$(curl -sS -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/name/Prometheus" | jq -r '.uid // empty')"
  if [[ -n "$PROMETHEUS_UID" ]]; then
    break
  fi
  info "$my_name" "Waiting for Grafana Prometheus datasource UID"
  sleep 2
done
if [[ -z "$PROMETHEUS_UID" ]]; then
  error "$my_name" "Could not resolve Grafana Prometheus datasource uid"
  exit 1
fi

baseline_total="$(grafana_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$PROMETHEUS_UID" 'sum(dq_exception_fact_jit_access_requests_total)')"
baseline_pending="$(grafana_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$PROMETHEUS_UID" 'sum(dq_exception_fact_jit_access_requests_current{status="pending"})')"
baseline_approved="$(grafana_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$PROMETHEUS_UID" 'sum(dq_exception_fact_jit_access_requests_current{status="approved"})')"
baseline_declined="$(grafana_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$PROMETHEUS_UID" 'sum(dq_exception_fact_jit_access_requests_current{status="declined"})')"
baseline_timed_out="$(grafana_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$PROMETHEUS_UID" 'sum(dq_exception_fact_jit_access_requests_current{status="timed_out"})')"

info "$my_name" "Creating timed-out JIT request candidate"
timed_out_request_id="$(create_request "$REQUESTER_TOKEN" "retail-banking" "exception-fact-reader" 15 "Grafana JIT validation timed-out candidate")"

ORIGINAL_TIMEOUT_MINUTES="$(get_app_config_timeout_minutes)"
if [[ -z "$ORIGINAL_TIMEOUT_MINUTES" ]]; then
  error "$my_name" "Could not read exception_fact_jit_request_timeout_minutes from /system/v1/app-config"
  exit 1
fi

info "$my_name" "Temporarily reducing JIT request timeout to 1 minute"
set_app_config_timeout_minutes 1
RESTORE_APP_CONFIG="true"

info "$my_name" "Waiting for Grafana to observe the pending timed-out candidate"
wait_for_metric_thresholds "$((baseline_total + 1))" "$((baseline_pending + 1))" "$baseline_approved" "$baseline_declined" "$baseline_timed_out"

wait_for_request_status "$timed_out_request_id" "timed_out"

restore_app_config

info "$my_name" "Creating approved and declined JIT requests"
approved_request_id="$(create_request "$REQUESTER_TOKEN" "retail-banking" "exception-fact-reader" 15 "Grafana JIT validation approved request")"
review_request "$approved_request_id" "approved" "Approved for Grafana JIT validation"
declined_request_id="$(create_request "$REQUESTER_TOKEN" "retail-banking" "exception-fact-reader" 15 "Grafana JIT validation declined request")"
review_request "$declined_request_id" "rejected" "Rejected for Grafana JIT validation"

api_request_with_token "$REQUESTER_TOKEN" GET "/rulebuilder/v1/exception-fact-access-requests"
if [[ "$HTTP_CODE" != "200" ]]; then
  error "$my_name" "GET /rulebuilder/v1/exception-fact-access-requests returned HTTP ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

actual_timed_out_status="$(jq -r --arg request_id "$timed_out_request_id" '.[] | select(.id == $request_id) | .status' <<<"$HTTP_BODY" | tail -1)"
actual_approved_status="$(jq -r --arg request_id "$approved_request_id" '.[] | select(.id == $request_id) | .status' <<<"$HTTP_BODY" | tail -1)"
actual_declined_status="$(jq -r --arg request_id "$declined_request_id" '.[] | select(.id == $request_id) | .status' <<<"$HTTP_BODY" | tail -1)"

if [[ "$actual_timed_out_status" != "timed_out" ]]; then
  error "$my_name" "Timed-out request ${timed_out_request_id} is ${actual_timed_out_status:-missing} instead of timed_out"
  exit 1
fi
if [[ "$actual_approved_status" != "approved" ]]; then
  error "$my_name" "Approved request ${approved_request_id} is ${actual_approved_status:-missing} instead of approved"
  exit 1
fi
if [[ "$actual_declined_status" != "rejected" ]]; then
  error "$my_name" "Declined request ${declined_request_id} is ${actual_declined_status:-missing} instead of rejected"
  exit 1
fi

target_total="$((baseline_total + 3))"
target_pending="$baseline_pending"
target_approved="$((baseline_approved + 1))"
target_declined="$((baseline_declined + 1))"
target_timed_out="$((baseline_timed_out + 1))"

info "$my_name" "Waiting for Grafana to observe the JIT request counters"
wait_for_metric_thresholds "$target_total" "$target_pending" "$target_approved" "$target_declined" "$target_timed_out"

success "$my_name" "Grafana JIT access request counters increased as expected"