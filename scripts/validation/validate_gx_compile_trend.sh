#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate GX compile success and failure events appear in Grafana Execution Monitoring.
#
# What it does:
# - Requires the API, Kong, Grafana, Prometheus, and OTel collector containers to already be running.
# - Mints a seeded user JWT through the shared auth helper.
# - Posts one valid GX suite save request and one deliberate overwrite conflict to emit compile success and failure events.
# - Verifies Grafana's Prometheus datasource sees the compile event counters increase.
#
# validate: groups=api,observability
# Version: 1.0
# Last modified: 2026-05-10

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/grafana_oauth_session.sh"

my_name="validate_gx_compile_trend.sh"

dq_source_seeded_user_credentials --quiet

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

build_suite_payload() {
  local suite_id="$1"
  local scenario="$2"

  jq -nc \
    --arg suite_id "$suite_id" \
    --arg scenario "$scenario" \
    --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{
      suiteId: $suite_id,
      suiteVersion: 1,
      artifactVersion: "v1",
      assignmentScope: {
        dataObjectId: "data-object-compile-trend"
      },
      resolvedExecutionScope: {
        dataObjectVersionIds: ["dov-compile-trend-001"]
      },
      gxSuite: {
        expectations: [
          {
            expectationType: "expect_column_values_to_not_be_null",
            kwargs: {
              column: "id"
            }
          }
        ],
        meta: {
          scenario: $scenario
        }
      },
      compiledFrom: {
        ruleIds: ["rule-compile-trend"],
        compilerVersion: "dq-compiler-compile-trend",
        generatedAt: $generated_at
      },
      executionHints: {
        recommendedEngine: "pyspark",
        primaryKeyFields: ["id"]
      },
      sourcePipeline: "compile_trend_validation"
    }'
}

post_suite() {
  local payload="$1"
  local expected_http_code="$2"
  local label="$3"
  local response_file
  local headers_file
  local response
  local http_code
  local curl_rc

  response_file="$(mktemp)"
  headers_file="$(mktemp)"

  set +e
  response="$(curl -sS \
    -D "$headers_file" \
    -o "$response_file" \
    -w '%{http_code}' \
    -X POST "${KONG_PUBLIC_URL%/}/rulebuilder/v1/gx/suites" \
    "${AUTH_HEADER[@]}" \
    -H 'Content-Type: application/json' \
    -d "$payload")"
  curl_rc=$?
  set -e

  if [ "$curl_rc" -ne 0 ]; then
    error "$my_name" "HTTP POST ${label} request failed with rc=${curl_rc}"
    cat "$headers_file" >&2 || true
    cat "$response_file" >&2 || true
    rm -f "$response_file" "$headers_file"
    exit "$curl_rc"
  fi

  http_code="$response"
  if [[ "$http_code" != "$expected_http_code" ]]; then
    error "$my_name" "${label} returned HTTP ${http_code}; expected ${expected_http_code}"
    cat "$headers_file" >&2 || true
    cat "$response_file" >&2 || true
    rm -f "$response_file" "$headers_file"
    exit 1
  fi

  printf '%s\n' "$response_file"
  rm -f "$headers_file"
}

if [[ -z "${KONG_PUBLIC_URL:-}" ]]; then
  error "$my_name" "KONG_PUBLIC_URL must be set to the public Kong URL used by the UI"
  exit 1
fi
if [[ -z "${GRAFANA_PUBLIC_URL:-}" ]]; then
  error "$my_name" "GRAFANA_PUBLIC_URL must be set"
  exit 1
fi
if [[ -z "${GRAFANA_ADMIN_USER:-}" || -z "${GRAFANA_ADMIN_PASSWORD:-}" ]]; then
  error "$my_name" "GRAFANA_ADMIN_USER and GRAFANA_ADMIN_PASSWORD must be set"
  exit 1
fi
if [[ -z "${SSO_PUBLIC_ISSUER_URL:-}" ]]; then
  error "$my_name" "SSO_PUBLIC_ISSUER_URL must be set"
  exit 1
fi
if [[ -z "${KEYCLOAK_JACCLOUD_USERNAME:-}" || -z "${KEYCLOAK_JACCLOUD_PASSWORD:-}" ]]; then
  error "$my_name" "KEYCLOAK_JACCLOUD_USERNAME and KEYCLOAK_JACCLOUD_PASSWORD must be set"
  exit 1
fi
if [[ -z "${VITE_KEYCLOAK_CLIENT_ID:-}" ]]; then
  error "$my_name" "VITE_KEYCLOAK_CLIENT_ID must be set"
  exit 1
fi

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [[ -f "$KONG_CA_CERT" && -z "${CURL_CA_BUNDLE:-}" ]]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

require_cmd curl
require_cmd docker
require_cmd jq

for service_name in api kong prometheus grafana otel-collector; do
  require_running_service "$service_name"
done

wait_for_http_200 "${KONG_PUBLIC_URL%/}/health" "api health"

TOKEN_ENDPOINT="${SSO_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"
ACCESS_TOKEN="$(dq_keycloak_password_grant_access_token "$TOKEN_ENDPOINT" "$VITE_KEYCLOAK_CLIENT_ID" "$KEYCLOAK_JACCLOUD_USERNAME" "$KEYCLOAK_JACCLOUD_PASSWORD")"
AUTH_HEADER=( -H "Authorization: Bearer ${ACCESS_TOKEN}" )

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

success_query='sum(increase(dq_execution_compile_events_total{operation="compile_artifact",result="succeeded"}[5m]))'
failure_query='sum(increase(dq_execution_compile_events_total{operation="compile_artifact",result="failed"}[5m]))'

baseline_succeeded="$(prom_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$success_query")"
baseline_failed="$(prom_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$failure_query")"

suite_id="compile-trend-${RUN_ENVIRONMENT:-dev}-$(date -u +%Y%m%d%H%M%S)-${RANDOM}${RANDOM}"
success_payload="$(build_suite_payload "$suite_id" "success")"
failure_payload="$(build_suite_payload "$suite_id" "failure")"

info "$my_name" "Saving GX suite once to emit compile success"
success_response_file="$(post_suite "$success_payload" "201" "GX suite save success")"

info "$my_name" "Saving the same GX suite with a changed payload to emit compile failure"
failure_response_file="$(post_suite "$failure_payload" "409" "GX suite save conflict")"

rm -f "$success_response_file" "$failure_response_file"

info "$my_name" "Waiting for Grafana Prometheus to observe compile event increments"
compile_succeeded="0"
compile_failed="0"
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
  compile_succeeded="$(prom_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$success_query")"
  compile_failed="$(prom_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$failure_query")"
  if awk -v current="$compile_succeeded" -v baseline="$baseline_succeeded" 'BEGIN { exit !(current > baseline) }' \
    && awk -v current="$compile_failed" -v baseline="$baseline_failed" 'BEGIN { exit !(current > baseline) }'; then
    break
  fi
  info "$my_name" "Compile counters not observed yet; retrying (${attempt}/12)"
  sleep 5
done

if ! awk -v current="$compile_succeeded" -v baseline="$baseline_succeeded" 'BEGIN { exit !(current > baseline) }'; then
  error "$my_name" "Compile success trend did not increase (baseline=${baseline_succeeded}, current=${compile_succeeded})"
  exit 1
fi
if ! awk -v current="$compile_failed" -v baseline="$baseline_failed" 'BEGIN { exit !(current > baseline) }'; then
  error "$my_name" "Compile failure trend did not increase (baseline=${baseline_failed}, current=${compile_failed})"
  exit 1
fi

success "$my_name" "GX compile success and failure events were emitted and observed in Grafana"
info "$my_name" "- save success: ${baseline_succeeded} -> ${compile_succeeded}"
info "$my_name" "- save failure: ${baseline_failed} -> ${compile_failed}"
