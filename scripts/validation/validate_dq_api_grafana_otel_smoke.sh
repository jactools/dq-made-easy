#!/usr/bin/env bash
set -euo pipefail

# Purpose: Smoke-test dq-api telemetry visibility in Grafana (Prometheus + Tempo datasources).
#
# What it does:
# - Requires api/kong/otel stack containers to already be running.
# - Generates dq-api traffic.
# - Verifies dq_api_* metrics via Grafana Prometheus datasource.
# - Verifies traces via Grafana Tempo datasource.
#
# validate: groups=api,observability

# Version: 1.4
# Last modified: 2026-05-01

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OBS_COMPOSE="${ROOT_DIR}/docker-compose/"
APP_COMPOSE="${ROOT_DIR}/docker-compose/"

LOG_LEVEL=0
. "$ROOT_DIR/scripts/supporting/setup_env.sh"
# shellcheck disable=SC1091
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
dq_source_seeded_user_credentials --env-file "$ROOT_ENV_FILE" --quiet
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/grafana_oauth_session.sh"

my_name="validate_dq_api_grafana_otel_smoke.sh"

if [[ -n "${ROOT_ENV_FILE:-}" && -f "${ROOT_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "$ROOT_ENV_FILE"
fi

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [ -f "$KONG_CA_CERT" ] && [ -z "${CURL_CA_BUNDLE:-}" ]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

# Canonical host-facing base URLs from the selected env file.
GATEWAY_BASE_URL="${KONG_LOCAL_URL:-${KONG_PUBLIC_URL:-https://kong.jac.dot:9443}}"
GRAFANA_URL="${GRAFANA_PUBLIC_URL:-}"
if [[ -z "$GRAFANA_URL" ]]; then
  error "$my_name" "GRAFANA_PUBLIC_URL or GRAFANA_URL must be set"
  exit 1
fi
GRAFANA_URL="${GRAFANA_URL%/}"
if [[ -z "${GRAFANA_ADMIN_USER:-}" || -z "${GRAFANA_ADMIN_PASSWORD:-}" ]]; then
  error "$my_name" "GRAFANA_ADMIN_USER and GRAFANA_ADMIN_PASSWORD must be set"
  exit 1
fi
GRAFANA_COOKIE_HEADER=""
API_BASE_URL="${GATEWAY_BASE_URL%/}"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: $cmd"
    exit 1
  fi
}

prom_query_value() {
  local uid="$1"
  local query="$2"
  local response
  local value

  if ! response="$(curl -sS -H "Cookie: ${GRAFANA_COOKIE_HEADER}" --get --data-urlencode "query=${query}" "${GRAFANA_URL}/api/datasources/proxy/uid/${uid}/api/v1/query")"; then
    error "$my_name" "Prometheus query request failed for: ${query}"
    return 1
  fi

  if ! value="$(jq -r '.data.result[0].value[1] // "0"' <<<"$response" 2>/dev/null)"; then
    error "$my_name" "Unexpected Prometheus response shape for query: ${query}"
    info "$my_name" "Response: ${response}"
    return 1
  fi

  printf '%s\n' "$value"
}

require_cmd docker
require_cmd curl
require_cmd jq

require_running_service() {
  local service="$1"
  local container_name

  container_name="$(docker ps --filter "label=com.docker.compose.service=${service}" --filter 'status=running' --format '{{.Names}}' | head -1)"
  if [[ -z "$container_name" ]]; then
    error "$my_name" "${service} must already be running; start the stack separately before running this smoke test"
    exit 1
  fi
}

wait_for_healthy_service() {
  local service="$1"
  local attempts="$2"
  local sleep_seconds="$3"
  local container_name
  local health_status

  container_name="$(docker ps --filter "label=com.docker.compose.service=${service}" --filter 'status=running' --format '{{.Names}}' | head -1)"
  if [[ -z "$container_name" ]]; then
    error "$my_name" "${service} must already be running; start the stack separately before running this smoke test"
    exit 1
  fi

  for _ in $(seq 1 "$attempts"); do
    health_status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}' "$container_name" 2>/dev/null || true)"
    if [[ "$health_status" == "healthy" || "$health_status" == "running" ]]; then
      return 0
    fi
    sleep "$sleep_seconds"
  done

  error "$my_name" "${service} container is not healthy (status=${health_status:-unknown})"
  exit 1
}

info "$my_name" "=============================================="
info "$my_name" "DQ API Grafana OTel Smoke Validation"
info "$my_name" "=============================================="
info "$my_name" "Estimated runtime: ~60-90s"

info "$my_name" "[1/7 | est: 10-20s] Verifying observability + API services are already running..."
for service in api kong loki otel-collector prometheus tempo grafana; do
  require_running_service "$service"
done

info "$my_name" "[1.5/7 | est: 5-30s] Waiting for Grafana container health..."
wait_for_healthy_service grafana 30 2

GRAFANA_COOKIE_HEADER="$(grafana_validation_cookie_header "$ROOT_DIR" "$GRAFANA_URL" "$GRAFANA_ADMIN_USER" "$GRAFANA_ADMIN_PASSWORD")"

info "$my_name" "[2/7 | est: 5-60s] Waiting for dq-api health..."
for _ in $(seq 1 10); do
#  curl "${API_BASE_URL}/health"
  code="$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE_URL}/health" || true)"
  if [[ "$code" == "200" ]]; then
    break
  else
    info "$my_name" "code=$code, retrying..."
  fi
  sleep 2
done

health_headers="$(curl -i -s -H "x-correlation-id: smoke-final-health" "${API_BASE_URL}/health")"
if ! grep -qi "x-trace-id:" <<< "$health_headers"; then
  error "$my_name" "dq-api health response is missing x-trace-id"
  exit 1
fi
trace_id="$(grep -i '^x-trace-id:' <<< "$health_headers" | awk '{print $2}' | tr -d '\r')"


info "$my_name" "[3/7 | est: 12-20s] Generating dq-api telemetry traffic..."
for i in $(seq 1 40); do
  curl -s -o /dev/null -H "x-correlation-id: smoke-health-${i}" "${API_BASE_URL}/health" || true
done
for i in $(seq 1 12); do
  curl -s -o /dev/null -H "x-correlation-id: smoke-authfail-${i}" "${API_BASE_URL}/admin/v1/me" || true
done
sleep 12

info "$my_name" "[4/7 | est: 1-3s] Resolving Grafana datasource UIDs..."
prom_uid=""
tempo_uid=""
for _ in $(seq 1 20); do
  prom_uid="$(curl -sS -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/name/Prometheus" | jq -r '.uid')"
  tempo_uid="$(curl -sS -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/name/Tempo" | jq -r '.uid')"
  if [[ -n "$prom_uid" && "$prom_uid" != "null" && -n "$tempo_uid" && "$tempo_uid" != "null" ]]; then
    break
  fi
  sleep 2
done
if [[ -z "$prom_uid" || "$prom_uid" == "null" ]]; then
  error "$my_name" "Could not resolve Prometheus datasource uid"
  exit 1
fi
if [[ -z "$tempo_uid" || "$tempo_uid" == "null" ]]; then
  error "$my_name" "Could not resolve Tempo datasource uid"
  exit 1
fi

info "$my_name" "[5/7 | est: 2-5s] Verifying dq-api metrics via Grafana Prometheus datasource..."
metric_names="$(curl -sS -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/proxy/uid/${prom_uid}/api/v1/label/__name__/values" | jq -r '.data[]' || true)"
if ! grep -q 'dq_api_request_count_total' <<< "$metric_names"; then
  error "$my_name" "dq_api_request_count_total not found via Grafana Prometheus datasource"
  exit 1
fi
if ! grep -q 'dq_api_auth_failures_total' <<< "$metric_names"; then
  error "$my_name" "dq_api_auth_failures_total not found via Grafana Prometheus datasource"
  exit 1
fi
if ! grep -q 'dq_exception_fact_jit_access_requests_total' <<< "$metric_names"; then
  error "$my_name" "dq_exception_fact_jit_access_requests_total not found via Grafana Prometheus datasource"
  exit 1
fi
if ! grep -q 'dq_exception_fact_jit_access_requests_current' <<< "$metric_names"; then
  error "$my_name" "dq_exception_fact_jit_access_requests_current not found via Grafana Prometheus datasource"
  exit 1
fi

req_increase="$(prom_query_value "$prom_uid" 'sum(increase(dq_api_request_count_total[10m]))')"
auth_fail_increase="$(prom_query_value "$prom_uid" 'sum(increase(dq_api_auth_failures_total[10m]))')"
req_grouped_series="$(prom_query_value "$prom_uid" 'count(sum by (endpoint_group, api_version) (rate(dq_api_request_count_total{api_version=~"v[0-9]+"}[10m])))')"
if [[ "$req_grouped_series" == "0" || -z "$req_grouped_series" ]]; then
  error "$my_name" "Grouped request rate query returned no series for endpoint_group/api_version"
  exit 1
fi
latency_grouped_series="$(prom_query_value "$prom_uid" 'count(histogram_quantile(0.95, sum by (le, endpoint_group, api_version) (rate(dq_api_operation_latency_ms_milliseconds_bucket{api_version=~"v[0-9]+"}[10m]))))')"
if [[ "$latency_grouped_series" == "0" || -z "$latency_grouped_series" ]]; then
  error "$my_name" "Grouped latency query returned no series for endpoint_group/api_version"
  exit 1
fi

info "$my_name" "[6/7 | est: 2-8s] Verifying dq-api traces via Grafana Tempo datasource..."
now="$(date +%s)"
start="$((now - 1800))"
tempo_response="$(curl -sS -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/proxy/uid/${tempo_uid}/api/search?start=${start}&end=${now}&limit=20")"
if ! trace_count="$(jq -r '.traces | length' <<<"$tempo_response" 2>/dev/null)"; then
  error "$my_name" "Unexpected Tempo search response shape"
  info "$my_name" "Response: ${tempo_response}"
  exit 1
fi
if [[ "${trace_count}" == "0" || -z "${trace_count}" ]]; then
  error "$my_name" "No traces returned from Grafana Tempo datasource"
  exit 1
fi

info "$my_name" "[7/7 | est: <1s] Validation summary"
success "$my_name" "dq-api telemetry is visible in Grafana datasources"
info "$my_name" "- x-trace-id header observed: ${trace_id}"
info "$my_name" "- sum(increase(dq_api_request_count_total[10m])) = ${req_increase}"
info "$my_name" "- sum(increase(dq_api_auth_failures_total[10m])) = ${auth_fail_increase}"
info "$my_name" "- grouped request rate series: ${req_grouped_series}"
info "$my_name" "- grouped latency series: ${latency_grouped_series}"
info "$my_name" "- Tempo search traces returned: ${trace_count}"
info "$my_name" "=============================================="
