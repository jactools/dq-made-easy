#!/usr/bin/env bash
set -euo pipefail


# Purpose: Restart OTLP collector/services and validate the trace pipeline via Tempo.
#
# What it does:
# - Restarts otel-collector and key services so env changes are picked up.
# - Sends a few profiling enqueue requests.
# - Queries Tempo for returned trace IDs and tails relevant logs.
#
# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
init_root_env_file "$ROOT_DIR"

my_name="restart_otlp_validate.sh"

if [ ! -f "$ROOT_ENV_FILE" ]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

info "$my_name" "Starting OTLP collector and recreating api + profiling-worker..."
docker_compose up -d otel-collector
# recreate api and profiling-worker so they pick up env changes
docker_compose up -d api profiling-worker

info "$my_name" "Waiting for containers to start..."
sleep 6

REQ_BODY='{"type":"etl","payload":{"sourceConfig":{"inlineData":[]}},"dataSourceId":"ds-live","requestedByUserId":"user-live"}'

for i in 1 2 3; do
  info "$my_name" "--- sending request $i ---"
  curl -sS -D "/tmp/headers_$i" -o "/tmp/body_$i" -X POST "http://127.0.0.1:4010/api/v1/profiling/enqueue" \
    -H "Content-Type: application/json" \
    -H "X-Kong-Request-Id: live-kong-$i" \
    -H "X-Correlation-ID: live-cid-$i" \
    -d "$REQ_BODY"
  info "$my_name" "response headers for request $i:"
  sed -n '1,200p' "/tmp/headers_$i"
  info "$my_name" ""
  sleep 1
done

info "$my_name" "Sleeping 5s to allow collector/tempo to process..."
sleep 5

info "$my_name" "Querying Tempo for trace IDs returned by the API (x-trace-id header)..."
for i in 1 2 3; do
  TRACE=$(sed -n '1,200p' /tmp/headers_$i | grep -i '^x-trace-id:' | awk '{print $2}' | tr -d '\r' || true)
  if [ -n "$TRACE" ]; then
    info "$my_name" "Request $i trace: $TRACE"
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:3200/api/traces/$TRACE")
    info "$my_name" "Tempo /api/traces/$TRACE => HTTP $STATUS"
  else
    warning "$my_name" "No x-trace-id header present for request $i"
  fi
done

info "$my_name" "== Last 200 lines: otel collector logs =="
docker logs --tail 200 dq-made-easy-otel-collector || true

info "$my_name" "== Last 200 lines: tempo logs =="
docker logs --tail 200 dq-made-easy-tempo || true

success "$my_name" "Done."
