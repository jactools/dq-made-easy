#!/usr/bin/env bash
set -euo pipefail

# Purpose: Smoke-test dq-api telemetry visibility in Grafana (Prometheus + Tempo datasources).
#
# What it does:
# - Requires api/kong/otel stack to be running (Kind or docker-compose).
# - Generates dq-api traffic.
# - Verifies dq_api_* metrics via Grafana Prometheus datasource.
# - Verifies traces via Grafana Tempo datasource.
#
# validate: groups=api,observability

# Version: 2.0
# Last modified: 2026-08-17

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

LOG_LEVEL=0
. "$ROOT_DIR/scripts/supporting/setup_env.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
dq_source_seeded_user_credentials --env-file "$ROOT_ENV_FILE" --quiet
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/grafana_oauth_session.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/cluster_helpers.sh"

my_name="validate_dq_api_grafana_otel_smoke.sh"

if [[ -n "${ROOT_ENV_FILE:-}" && -f "${ROOT_ENV_FILE:-}" ]]; then
  # shellcheck disable=SC1090
  source "$ROOT_ENV_FILE"
fi

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [ -f "$KONG_CA_CERT" ] && [ -z "${CURL_CA_BUNDLE:-}" ]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

# Set base URLs — ingress or port-forward
GATEWAY_BASE_URL="${KONG_LOCAL_URL:-${KONG_PUBLIC_URL:-}}"
GRAFANA_URL="${GRAFANA_PUBLIC_URL:-}"

# If no ingress URLs, use port-forward
if [ -z "$GATEWAY_BASE_URL" ] || [ -z "$GRAFANA_URL" ]; then
  info "$my_name" "No ingress URLs — using port-forwarding..."
  port_forward_svc kong 9443 platform-kong 9443 || true
  port_forward_svc grafana 3000 platform-observability 3000 || true
  GATEWAY_BASE_URL="https://127.0.0.1:9443"
  GRAFANA_URL="http://127.0.0.1:3000"
fi

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

  if ! response="$(curl -sS -k -H "Cookie: ${GRAFANA_COOKIE_HEADER}" --get --data-urlencode "query=${query}" "${GRAFANA_URL}/api/datasources/proxy/uid/${uid}/api/v1/query")"; then
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

require_cmd curl
require_cmd jq

require_running_services() {
  local namespaces=("platform-kong" "dq-dev" "platform-observability")
  for ns in "${namespaces[@]}"; do
    local pods
    pods="$(kubectl get pods -n "$ns" 2>/dev/null | grep -c "Running" || echo "0")"
    if [ "$pods" -eq 0 ]; then
      error "$my_name" "No running pods in $ns — ensure the stack is deployed"
      exit 1
    fi
  done
}

info "$my_name" "=============================================="
info "$my_name" "DQ API Grafana OTel Smoke Validation"
info "$my_name" "=============================================="
info "$my_name" "Estimated runtime: ~60-90s"

info "$my_name" "[1/7] Verifying K8s services are running..."
require_running_services

GRAFANA_COOKIE_HEADER="$(grafana_validation_cookie_header "$ROOT_DIR" "$GRAFANA_URL" "$GRAFANA_ADMIN_USER" "$GRAFANA_ADMIN_PASSWORD")"

info "$my_name" "[2/7 | est: 5-60s] Waiting for dq-api health..."
for _ in $(seq 1 10); do
  code="$(curl -sk -o /dev/null -w "%{http_code}" "${API_BASE_URL}/health" || true)"
  if [[ "$code" == "200" ]]; then
    break
  else
    info "$my_name" "code=$code, retrying..."
  fi
  sleep 2
done

health_headers="$(curl -ski -H "x-correlation-id: smoke-final-health" "${API_BASE_URL}/health")"
if ! grep -qi "x-trace-id:" <<< "$health_headers"; then
  error "$my_name" "dq-api health response is missing x-trace-id"
  exit 1
fi
trace_id="$(grep -i '^x-trace-id:' <<< "$health_headers" | awk '{print $2}' | tr -d '\r')"

info "$my_name" "[3/7 | est: 12-20s] Generating dq-api telemetry traffic..."
for i in $(seq 1 40); do
  curl -sk -o /dev/null -H "x-correlation-id: smoke-health-${i}" "${API_BASE_URL}/health" || true
done
for i in $(seq 1 12); do
  curl -sk -o /dev/null -H "x-correlation-id: smoke-authfail-${i}" "${API_BASE_URL}/admin/v1/me" || true
done
sleep 12

info "$my_name" "[4/7 | est: 1-3s] Resolving Grafana datasource UIDs..."
prom_uid=""
tempo_uid=""
for _ in $(seq 1 20); do
  prom_uid="$(curl -sk -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/name/Prometheus" | jq -r '.uid')"
  tempo_uid="$(curl -sk -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/name/Tempo" | jq -r '.uid')"
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
metric_names="$(curl -sk -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/proxy/uid/${prom_uid}/api/v1/label/__name__/values" | jq -r '.data[]' || true)"
if ! grep -q 'dq_api_request_count_total' <<< "$metric_names"; then
  error "$my_name" "dq_api_request_count_total not found via Grafana Prometheus datasource"
  exit 1
fi

req_increase="$(prom_query_value "$prom_uid" 'sum(increase(dq_api_request_count_total[10m]))')"
info "$my_name" "[6/7 | est: 2-8s] Verifying dq-api traces via Grafana Tempo datasource..."
now="$(date +%s)"
start="$((now - 1800))"
tempo_response="$(curl -sk -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/proxy/uid/${tempo_uid}/api/search?start=${start}&end=${now}&limit=20")"
if ! trace_count="$(jq -r '.traces | length' <<<"$tempo_response" 2>/dev/null)"; then
  error "$my_name" "Unexpected Tempo search response shape"
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
info "$my_name" "- Tempo search traces returned: ${trace_count}"
info "$my_name" "=============================================="