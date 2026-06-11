#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate end-to-end trace propagation from UI through Kong to API (Tempo).
#
# What it does:
# - Requires the UI, gateway, and observability services to already be running.
# - Configures Kong CORS plugin for UI origins (dev convenience).
# - Performs requests and verifies the trace is present in Tempo.
#
# validate: groups=ui

# Version: 1.4
# Last modified: 2026-05-01

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OBS_COMPOSE="${ROOT_DIR}/docker-compose.yml"
APP_COMPOSE="${ROOT_DIR}/docker-compose.yml"

# Load repo defaults when available so hostnames/ports match local stack.
# (Do not source setup_env.sh here; it may perform docker login and other side-effects.)
if [ -f "${ROOT_DIR}/.env" ]; then
  set +u
  # shellcheck disable=SC1091
  . "${ROOT_DIR}/.env"
  set -u
fi

# shellcheck disable=SC1091
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
dq_source_seeded_user_credentials --env-file "$ROOT_ENV_FILE" --quiet

my_name="validate_ui_api_trace_propagation.sh"

if [[ -n "${ROOT_ENV_FILE:-}" && -f "${ROOT_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "$ROOT_ENV_FILE"
fi

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [ -f "$KONG_CA_CERT" ] && [ -z "${CURL_CA_BUNDLE:-}" ]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

if [ -z "${KEYCLOAK_PUBLIC_HOSTNAME:-}" ] && [ -n "${KEYCLOAK_PUBLIC_URL:-}" ]; then
  KEYCLOAK_PUBLIC_HOSTNAME="$(printf '%s' "$KEYCLOAK_PUBLIC_URL" | sed -E 's#^https?://([^/:]+).*$#\1#')"
fi
export KEYCLOAK_PUBLIC_HOSTNAME

if [ -z "${OTEL_EXPORTER_OTLP_ENDPOINT:-}" ]; then
  OTEL_EXPORTER_OTLP_ENDPOINT="http://dq-otel-collector:4317"
fi
export OTEL_EXPORTER_OTLP_ENDPOINT

# Canonical hostnames from the selected env file.
GATEWAY_HOSTNAME="${DQ_GATEWAY_HOSTNAME:-dq-made-easy.jac.dot}"
KONG_ADMIN_HOSTNAME="${DQ_KONG_ADMIN_HOSTNAME:-dq-kong.jac.dot}"
UI_HOSTNAME="${DQ_UI_HOSTNAME:-dq-made-easy.jac.dot}"

# Prefer the host-facing gateway URL for validation runs executed from the host.
GATEWAY_BASE_URL="${GATEWAY_BASE_URL:-${KONG_LOCAL_URL:-${KONG_PUBLIC_URL:-https://kong.jac.dot:9443}}}"
KONG_ADMIN_BIND_HOST="${KONG_ADMIN_HOST_BIND:-127.0.0.1}"
if [ "$KONG_ADMIN_BIND_HOST" = "0.0.0.0" ] || [ "$KONG_ADMIN_BIND_HOST" = "::" ]; then
  KONG_ADMIN_BIND_HOST="127.0.0.1"
fi
KONG_ADMIN_PORT="${KONG_ADMIN_HOST_PORT:-8001}"
KONG_ADMIN_URL="http://${KONG_ADMIN_BIND_HOST}:${KONG_ADMIN_PORT}"
GRAFANA_URL="${GRAFANA_PUBLIC_URL:-}"
if [[ -z "$GRAFANA_URL" ]]; then
  error "validate_ui_api_trace_propagation.sh" "GRAFANA_PUBLIC_URL or GRAFANA_URL must be set"
  exit 1
fi
GRAFANA_URL="${GRAFANA_URL%/}"
source "$ROOT_DIR/scripts/supporting/grafana_oauth_session.sh"

if [[ -z "${GRAFANA_ADMIN_USER:-}" || -z "${GRAFANA_ADMIN_PASSWORD:-}" ]]; then
  error "validate_ui_api_trace_propagation.sh" "GRAFANA_ADMIN_USER and GRAFANA_ADMIN_PASSWORD must be set"
  exit 1
fi
GRAFANA_COOKIE_HEADER=""
UI_ORIGIN_PRIMARY="${UI_ORIGIN_PRIMARY:-${UI_NGINX_LOCAL_URL:-http://${UI_HOSTNAME}:5173}}"
UI_ORIGIN_SECONDARY="${UI_ORIGIN_SECONDARY:-${UI_VITE_LOCAL_URL:-http://${UI_HOSTNAME}:5174}}"
UI_ORIGIN="${UI_ORIGIN:-${UI_ORIGIN_PRIMARY}}"
TRACE_ATTEMPTS="${TRACE_ATTEMPTS:-24}"
TEMPO_SEARCH_POLLS="${TEMPO_SEARCH_POLLS:-36}"
TEMPO_SEARCH_SLEEP_SECONDS="${TEMPO_SEARCH_SLEEP_SECONDS:-4}"
TEMPO_SEARCH_LOOKBACK_SECONDS="${TEMPO_SEARCH_LOOKBACK_SECONDS:-3600}"
TEMPO_TRACE_FETCH_POLLS="${TEMPO_TRACE_FETCH_POLLS:-18}"
TEMPO_TRACE_FETCH_SLEEP_SECONDS="${TEMPO_TRACE_FETCH_SLEEP_SECONDS:-2}"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: ${cmd}"
    exit 1
  fi
}

wait_http_code() {
  local url="$1"
  local expected_code="$2"
  local attempts="$3"
  local sleep_seconds="$4"

  echo -n "Checking ${url} for HTTP ${expected_code}... "
  for _ in $(seq 1 "$attempts"); do
    echo -n "."
    local code
    code="$(curl -sS --connect-timeout 2 --max-time 5 -o /dev/null -w "%{http_code}" "$url" || true)"
    if [[ "$code" == "$expected_code" ]]; then
      echo "OK"
      return 0
    fi
    sleep "$sleep_seconds"
  done

  return 1
}

extract_header() {
  local header_name="$1"
  local headers_blob="$2"
  local needle
  needle="$(printf '%s' "$header_name" | tr '[:upper:]' '[:lower:]')"
  awk -F': ' -v name="$needle" 'tolower($1)==name {gsub("\r", "", $2); print $2}' <<< "$headers_blob" | tail -1
}

normalize_hex() {
  tr '[:upper:]' '[:lower:]' <<< "$1"
}

tempo_trace_has_service() {
  local trace_json="$1"
  local service_name="$2"
  jq -er --arg service "$service_name" '
    [
      (
        .. | objects
        | select(.key? == "service.name")
        | (.value.stringValue // .value // .stringValue // empty)
      ),
      (
        .. | objects
        | .serviceName?
        | select(type == "string")
      )
    ]
    | map(tostring)
    | any(. == $service)
  ' <<< "$trace_json" >/dev/null
}

tempo_trace_payload_present() {
  local trace_json="$1"
  jq -e '
    [
      .resourceSpans[]?,
      .batches[]?,
      .trace.resourceSpans[]?,
      .trace.batches[]?,
      .data.resourceSpans[]?,
      .data.batches[]?,
      .data.trace.resourceSpans[]?,
      .data.trace.batches[]?
    ]
    | length > 0
  ' >/dev/null 2>&1 <<< "$trace_json"
}

tempo_trace_service_names() {
  local trace_json="$1"
  jq -r '
    [
      (
        .. | objects
        | select(.key? == "service.name")
        | (.value.stringValue // .value // .stringValue // empty)
      ),
      (
        .. | objects
        | .serviceName?
        | select(type == "string")
      )
    ]
    | map(select(type == "string" and length > 0))
    | unique
    | .[]?
  ' <<< "$trace_json"
}

tempo_trace_correlation_ids() {
  local trace_json="$1"
  jq -r '
    .. | objects
    | select(.key? == "correlation_id")
    | (.value.stringValue // .value // .stringValue // empty)
  ' <<< "$trace_json" | awk 'NF { print }' | sort -u
}

header_contains_token() {
  local value="$1"
  local token="$2"
  local needle
  needle="$(printf '%s' "$token" | tr '[:upper:]' '[:lower:]')"
  tr ',' '\n' <<< "$value" | tr -d ' ' | tr '[:upper:]' '[:lower:]' | rg -q "^${needle}$"
}

require_cmd docker
require_cmd curl
require_cmd jq
require_cmd rg

require_running_service() {
  local service="$1"
  local container_name

  container_name="$(docker ps --filter "label=com.docker.compose.service=${service}" --filter 'status=running' --format '{{.Names}}' | head -1)"
  if [[ -z "$container_name" ]]; then
    error "$my_name" "${service} must already be running; start the stack separately before running this smoke test"
    exit 1
  fi
}

info "$my_name" "=============================================="
info "$my_name" "UI -> Gateway -> API Trace Propagation Check"
info "$my_name" "=============================================="
info "$my_name" "Estimated runtime: ~90-180s"

info "$my_name" "[1/7 | est: 10-30s] Verifying API + gateway + observability services are already running..."
for service in api kong loki otel-collector prometheus tempo grafana; do
  require_running_service "$service"
done

info "$my_name" "[1.5/7 | est: 5-30s] Enforcing Kong CORS trace/correlation header policy..."
if ! wait_http_code "${KONG_ADMIN_URL}/" "200" 40 2; then
  error "$my_name" "Kong Admin API did not become ready at ${KONG_ADMIN_URL}"
  exit 1
fi

cors_plugin_id="$(curl -sS "${KONG_ADMIN_URL}/services/dq-api/plugins" | jq -r '.data[]? | select(.name=="cors") | .id' | head -1)"
if [[ -z "$cors_plugin_id" || "$cors_plugin_id" == "null" ]]; then
  error "$my_name" "Could not resolve dq-api CORS plugin in Kong Admin API"
  exit 1
fi

patched="false"
cors_payload="{\"config\":{\"origins\":[\"${UI_ORIGIN_PRIMARY}\",\"${UI_ORIGIN_SECONDARY}\"],\"methods\":[\"GET\",\"POST\",\"PUT\",\"DELETE\",\"PATCH\",\"OPTIONS\"],\"headers\":[\"Content-Type\",\"Authorization\",\"X-Correlation-ID\",\"traceparent\",\"tracestate\"],\"exposed_headers\":[\"X-Kong-Response-Latency\",\"X-Correlation-ID\",\"X-Trace-ID\"],\"credentials\":true,\"max_age\":3600}}"
for _ in $(seq 1 10); do
  if curl -sS --connect-timeout 2 --max-time 10 -X PATCH "${KONG_ADMIN_URL}/plugins/${cors_plugin_id}" \
    -H 'Content-Type: application/json' \
    -d "$cors_payload" >/dev/null; then
    patched="true"
    break
  fi
  sleep 1
done

if [[ "$patched" != "true" ]]; then
  error "$my_name" "Unable to patch Kong CORS plugin after retries"
  exit 1
fi

info "$my_name" "[2/7 | est: 5-60s] Waiting for gateway health..."
if ! wait_http_code "${GATEWAY_BASE_URL}/health" "200" 40 2; then
  error "$my_name" "Gateway did not become healthy at ${GATEWAY_BASE_URL}"
  exit 1
fi

info "$my_name" "[3/7 | est: 2-5s] Validating CORS trace/correlation header propagation rules..."
preflight_headers="$(curl -i -s -X OPTIONS \
  -H "Origin: ${UI_ORIGIN}" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: traceparent,tracestate,x-correlation-id,authorization,content-type" \
  "${GATEWAY_BASE_URL}/health")"

allow_headers="$(extract_header "access-control-allow-headers" "$preflight_headers")"
if [[ -z "$allow_headers" ]]; then
  error "$my_name" "CORS preflight response missing access-control-allow-headers"
  exit 1
fi
for required in traceparent tracestate x-correlation-id; do
  if ! header_contains_token "$allow_headers" "$required"; then
    error "$my_name" "CORS allow headers missing ${required}. current=${allow_headers}"
    info "$my_name" "Hint: ensure Kong CORS plugin includes trace/correlation headers (rebuild/rebootstrap Kong if needed)."
    exit 1
  fi
done

info "$my_name" "[4/7 | est: 10-30s] Sending traced UI-like requests via gateway (attempts=${TRACE_ATTEMPTS})..."
trace_ids=()
correlation_ids=()
last_trace_id=""
last_resp_trace_id=""
last_cid=""

for i in $(seq 1 "$TRACE_ATTEMPTS"); do
  trace_id="$(openssl rand -hex 16)"
  parent_span_id="$(openssl rand -hex 8)"
  traceparent="00-${trace_id}-${parent_span_id}-01"
  cid="phase5-ui-smoke-${trace_id:0:12}-${i}"

  health_headers="$(curl -i -s \
    -H "traceparent: ${traceparent}" \
    -H "x-correlation-id: ${cid}" \
    -H "Origin: ${UI_ORIGIN}" \
    "${GATEWAY_BASE_URL}/health")"

  resp_cid="$(extract_header "x-correlation-id" "$health_headers")"
  resp_trace_id="$(extract_header "x-trace-id" "$health_headers")"
  expose_headers="$(extract_header "access-control-expose-headers" "$health_headers")"

  if [[ -z "$resp_cid" || -z "$resp_trace_id" ]]; then
    error "$my_name" "Response missing correlation/trace headers on attempt ${i}"
    exit 1
  fi
  if [[ "$resp_cid" != "$cid" ]]; then
    error "$my_name" "x-correlation-id mismatch on attempt ${i}. expected=${cid} actual=${resp_cid}"
    exit 1
  fi

  expected_trace_id="$(normalize_hex "$trace_id")"
  actual_trace_id="$(normalize_hex "$resp_trace_id")"
  if [[ "$actual_trace_id" != "$expected_trace_id" ]]; then
    error "$my_name" "API did not continue incoming trace context on attempt ${i}. expected=${expected_trace_id} got=${actual_trace_id}"
    exit 1
  fi

  if [[ -z "$expose_headers" ]]; then
    error "$my_name" "Response missing access-control-expose-headers"
    exit 1
  fi
  for required in x-correlation-id x-trace-id; do
    if ! header_contains_token "$expose_headers" "$required"; then
      error "$my_name" "CORS expose headers missing ${required}. current=${expose_headers}"
      exit 1
    fi
  done

  trace_ids+=("$expected_trace_id")
  correlation_ids+=("$cid")
  last_trace_id="$expected_trace_id"
  last_resp_trace_id="$actual_trace_id"
  last_cid="$resp_cid"
  sleep 0.25
done

info "$my_name" "[5/7 | est: 1-3s] Resolving Tempo datasource uid..."
GRAFANA_COOKIE_HEADER="$(grafana_validation_cookie_header "$ROOT_DIR" "$GRAFANA_URL" "$GRAFANA_ADMIN_USER" "$GRAFANA_ADMIN_PASSWORD")"
  tempo_uid="$(curl -sS -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/name/Tempo" | jq -r '.uid')"
if [[ -z "$tempo_uid" || "$tempo_uid" == "null" ]]; then
  error "$my_name" "Could not resolve Tempo datasource uid"
  exit 1
fi

info "$my_name" "[6/7 | est: 10-180s] Polling Tempo for at least one emitted trace id. Grafana URL: ${GRAFANA_URL} Tempo UID: ${tempo_uid}"
matched_trace_id=""
trace_json=""
last_trace_json=""

# Stage A: search-index path (fast when Tempo search has indexed the trace).
for _ in $(seq 1 "$TEMPO_SEARCH_POLLS"); do
  now="$(date +%s)"
  start="$((now - TEMPO_SEARCH_LOOKBACK_SECONDS))"
  search_ids="$(curl -sS -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/proxy/uid/${tempo_uid}/api/search?start=${start}&end=${now}&limit=500" | jq -r '.traces[]? | .traceID // .traceId // .id')"

  for candidate in "${trace_ids[@]}"; do
    if rg -q "^${candidate}$" <<< "$search_ids"; then
      trace_api_url="${GRAFANA_URL}/api/datasources/proxy/uid/${tempo_uid}/api/traces/${candidate}"
      candidate_trace_json="$(curl -sS -H 'Accept: application/json' -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "$trace_api_url")"
      if tempo_trace_payload_present "$candidate_trace_json"; then
        last_trace_json="$candidate_trace_json"
      fi
      if tempo_trace_has_service "$candidate_trace_json" "dq-api"; then
        for cid_candidate in "${correlation_ids[@]}"; do
          if rg -q "${cid_candidate}" <<< "$(tempo_trace_correlation_ids "$candidate_trace_json")"; then
            matched_trace_id="$candidate"
            trace_json="$candidate_trace_json"
            break
          fi
        done
      fi
      if [[ -n "$matched_trace_id" ]]; then
        break
      fi
      if tempo_trace_has_service "$candidate_trace_json" "dq-api" && [[ -z "$matched_trace_id" ]]; then
        matched_trace_id="$candidate"
        trace_json="$candidate_trace_json"
        break
      fi
    fi
  done

  if [[ -n "$matched_trace_id" ]]; then
    break
  fi
  sleep "$TEMPO_SEARCH_SLEEP_SECONDS"
done

if [[ -z "$matched_trace_id" ]]; then
  info "$my_name" "Search index did not return propagated trace IDs yet; trying direct trace-by-id retrieval..."

  # Stage B: direct trace fetch fallback (handles delayed search indexing).
  for _ in $(seq 1 "$TEMPO_TRACE_FETCH_POLLS"); do
    for ((idx=${#trace_ids[@]}-1; idx>=0; idx--)); do
      candidate="${trace_ids[idx]}"
      trace_api_url="${GRAFANA_URL}/api/datasources/proxy/uid/${tempo_uid}/api/traces/${candidate}"
      candidate_trace_json="$(curl -sS -H 'Accept: application/json' -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "$trace_api_url")"
      if tempo_trace_payload_present "$candidate_trace_json"; then
        last_trace_json="$candidate_trace_json"
      fi
      if tempo_trace_has_service "$candidate_trace_json" "dq-api"; then
        for cid_candidate in "${correlation_ids[@]}"; do
          if rg -q "${cid_candidate}" <<< "$(tempo_trace_correlation_ids "$candidate_trace_json")"; then
            matched_trace_id="$candidate"
            trace_json="$candidate_trace_json"
            break
          fi
        done
      fi
      if [[ -n "$matched_trace_id" ]]; then
        break
      fi
      if tempo_trace_has_service "$candidate_trace_json" "dq-api" && [[ -z "$matched_trace_id" ]]; then
        matched_trace_id="$candidate"
        trace_json="$candidate_trace_json"
        break
      fi
    done

    if [[ -n "$matched_trace_id" ]]; then
      break
    fi
    sleep "$TEMPO_TRACE_FETCH_SLEEP_SECONDS"
  done
fi

if [[ -z "$matched_trace_id" ]]; then
  error "$my_name" "None of the propagated trace IDs were found/retrieved from Tempo (attempts=${TRACE_ATTEMPTS})"
  info "$my_name" "Hint: collector sampling is probabilistic (10% by default); increase TRACE_ATTEMPTS or temporarily raise sampling."
  if [[ -n "$last_trace_json" ]]; then
    services="$(tempo_trace_service_names "$last_trace_json" | tr '\n' ',' | sed 's/,$//')"
    if [[ -n "$services" ]]; then
      info "$my_name" "Hint: last retrieved trace only exposed these services: ${services}"
    fi
  fi
  exit 1
fi

if [[ -z "$trace_json" ]]; then
  trace_api_url="${GRAFANA_URL}/api/datasources/proxy/uid/${tempo_uid}/api/traces/${matched_trace_id}"
  trace_json="$(curl -sS -H 'Accept: application/json' -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "$trace_api_url")"
fi
if ! tempo_trace_payload_present "$trace_json"; then
  error "$my_name" "Matched trace ${matched_trace_id} was not retrievable via Tempo trace API"
  exit 1
fi

info "$my_name" "[7/7 | est: 1-3s] Verifying single trace graph includes API spans..."
if ! tempo_trace_has_service "$trace_json" "dq-api"; then
  services="$(tempo_trace_service_names "$trace_json" | tr '\n' ',' | sed 's/,$//')"
  if [[ -n "$services" ]]; then
    error "$my_name" "Tempo trace does not include service.name=dq-api; observed services: ${services}"
  else
    error "$my_name" "Tempo trace does not include service.name=dq-api"
  fi
  exit 1
fi

if tempo_trace_has_service "$trace_json" "dq-kong"; then
  kong_note="yes"
else
  kong_note="no"
fi

info "$my_name" "[7/7 | est: <1s] Validation summary"
success "$my_name" "Phase 5 propagation checks succeeded"
info "$my_name" "- Last request traceparent trace_id: ${last_trace_id}"
info "$my_name" "- Last response x-trace-id: ${last_resp_trace_id}"
info "$my_name" "- Last response x-correlation-id echoed: ${last_cid}"
info "$my_name" "- Tempo matched propagated trace id: ${matched_trace_id}"
info "$my_name" "- Tempo trace includes service.name=dq-api"
info "$my_name" "- Tempo trace includes service.name=dq-kong: ${kong_note}"
info "$my_name" "=============================================="
