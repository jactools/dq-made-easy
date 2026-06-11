#!/usr/bin/env bash
set -euo pipefail

# Purpose: Smoke-test OpenMetadata OpenTelemetry export into Tempo.
#
# What it does:
# - Requires collector/tempo, Grafana, and OpenMetadata containers to already be running.
# - Generates traffic and confirms service.name=dq-openmetadata in Tempo traces.
#
# validate: groups=openmetadata,observability

# Version: 1.4
# Last modified: 2026-05-01

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
dq_source_seeded_user_credentials --env-file "$ROOT_ENV_FILE" --quiet
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/grafana_oauth_session.sh"

my_name="validate_openmetadata_otel_smoke.sh"

if [[ -n "${ROOT_ENV_FILE:-}" && -f "${ROOT_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "$ROOT_ENV_FILE"
fi

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

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: $cmd"
    exit 1
  fi
}

wait_for_http() {
  local url="$1"
  local max_attempts="$2"
  local sleep_seconds="$3"

  for _ in $(seq 1 "$max_attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$sleep_seconds"
  done

  return 1
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

info "$my_name" "=============================================="
info "$my_name" "OpenMetadata OpenTelemetry Smoke Validation"
info "$my_name" "=============================================="
info "$my_name" "Estimated runtime: ~90-180s"

info "$my_name" "[1/5 | est: 10-30s] Verifying observability stack is already running..."
for service in loki prometheus otel-collector tempo grafana; do
  require_running_service "$service"
done

info "$my_name" "[2/5 | est: 20-90s] Verifying OpenMetadata services are already running..."
for service in openmetadata-db openmetadata-search-v9 openmetadata-server; do
  require_running_service "$service"
done

OPENMETADATA_VERSION_URL="https://openmetadata.jac.dot:8585/metadata/api/v1/system/version"

if ! wait_for_http "$OPENMETADATA_VERSION_URL" 60 2; then
  error "$my_name" "OpenMetadata server did not become ready in time"
  docker logs --tail=120 "$(docker ps --filter 'label=com.docker.compose.service=openmetadata-server' --filter 'status=running' --format '{{.Names}}' | head -1)" >&2 || true
  exit 1
fi

info "$my_name" "[3/5 | est: 2-8s] Verifying Java agent activation..."
OPENMETADATA_CONTAINER="$(docker ps --filter 'label=com.docker.compose.service=openmetadata-server' --filter 'status=running' --format '{{.ID}}' | head -1)"
if [[ -z "$OPENMETADATA_CONTAINER" ]]; then
  error "$my_name" "Could not resolve openmetadata-server container id"
  exit 1
fi

if ! docker inspect "$OPENMETADATA_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -q '^JAVA_TOOL_OPTIONS=-javaagent:/otel/agent/opentelemetry-javaagent.jar$'; then
  error "$my_name" "JAVA_TOOL_OPTIONS does not include expected javaagent path"
  docker inspect "$OPENMETADATA_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^JAVA_TOOL_OPTIONS=' >&2 || true
  exit 1
fi

if ! docker exec "$OPENMETADATA_CONTAINER" sh -lc 'test -s /otel/agent/opentelemetry-javaagent.jar'; then
  error "$my_name" "Java agent file missing or empty at /otel/agent/opentelemetry-javaagent.jar"
  exit 1
fi

info "$my_name" "[4/5 | est: 5-15s] Generating trace traffic against OpenMetadata API..."
for _ in $(seq 1 40); do
  curl -fsS "$OPENMETADATA_VERSION_URL" >/dev/null || true
done

info "$my_name" "[5/5 | est: 15-120s] Validating Tempo traces include service.name=dq-openmetadata..."
GRAFANA_COOKIE_HEADER="$(grafana_validation_cookie_header "$ROOT_DIR" "$GRAFANA_URL" "$GRAFANA_ADMIN_USER" "$GRAFANA_ADMIN_PASSWORD")"
tempo_uid="$(curl -sS -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/name/Tempo" | jq -r '.uid')"
if [[ -z "$tempo_uid" || "$tempo_uid" == "null" ]]; then
  error "$my_name" "Could not resolve Tempo datasource uid"
  exit 1
fi

trace_seen="false"
matched_trace_id=""
for _ in $(seq 1 24); do
  # Keep emitting traffic while we poll to avoid timing races in async exports.
  curl -fsS "https://openmetadata.jac.dot:8585/api/v1/system/version" >/dev/null || true
  sleep 2

  now="$(date +%s)"
  start="$((now - 1800))"
  trace_ids="$(curl -sS -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/proxy/uid/${tempo_uid}/api/search?start=${start}&end=${now}&limit=200" | jq -r '.traces[]? | .traceID // .traceId // .id')"

  while IFS= read -r trace_id; do
    [[ -z "$trace_id" ]] && continue
    trace_json="$(curl -sS -H 'Accept: application/json' -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/proxy/uid/${tempo_uid}/api/traces/${trace_id}")"
    if tempo_trace_has_service "$trace_json" "dq-openmetadata"; then
      trace_seen="true"
      matched_trace_id="$trace_id"
      break
    fi
  done <<< "$trace_ids"

  if [[ "$trace_seen" == "true" ]]; then
    break
  fi

  sleep 3
done

if [[ "$trace_seen" != "true" ]]; then
  error "$my_name" "No dq-openmetadata trace evidence found in Tempo traces"
  echo "Recent collector logs:" >&2
  docker logs --tail=200 "$(docker ps --filter 'label=com.docker.compose.service=otel-collector' --filter 'status=running' --format '{{.Names}}' | head -1)" >&2 || true
  echo "Recent openmetadata-server logs:" >&2
  docker logs --tail=200 "$OPENMETADATA_CONTAINER" >&2 || true
  exit 1
fi

info "$my_name" "[done | est: <1s] Final health confirmation..."
curl -fsS "$OPENMETADATA_VERSION_URL" >/dev/null

success "$my_name" "OpenMetadata OTel smoke validation passed"
info "$my_name" "- Java agent active"
info "$my_name" "- OpenMetadata endpoint reachable"
info "$my_name" "- Tempo trace includes service.name=dq-openmetadata"
info "$my_name" "- Matched trace id: ${matched_trace_id}"
info "$my_name" "=============================================="
