#!/usr/bin/env bash
set -euo pipefail

# Purpose: Smoke-test WS10-AC04 outbound webhook dispatch end-to-end.
# What it does:
# - Starts a local webhook receiver on a random port.
# - Calls POST /agent/v1/integrations/dispatches with a Mistral AI webhook
#   payload pointing at the local receiver.
# - Verifies the dispatch response carries delivery status "delivered".
# - Verifies the webhook receiver got the envelope with correct structure.
# - Optionally tests retry on 5xx then 200.
# - Cleans up the temp server.
#
# Prerequisites:
# - A live dq-api stack with SSO (Keycloak).
# - curl, jq, python3 on PATH.
# - Agent access policy allows the test agent identity.
#
# Usage:
#   scripts/validation/smoke_test_webhook_dispatch.sh [--env dev|test|prod] [--env-file PATH]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

my_name="smoke_test_webhook_dispatch.sh"
agent_type="mcp"
agent_source="smoke-test-webhook"
CONFIG_TOKEN=""
ORIGINAL_AGENT_ACCESS_POLICY=""
WEBHOOK_PID=""

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
  if ! command -v "$1" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: $1"
    exit 2
  fi
}

require_cmd curl
require_cmd jq
require_cmd python3

mkdir -p "$ROOT_DIR/tmp"

# --------------------------------------------------------------------------
# Local webhook receiver (tiny Python HTTP server)
# --------------------------------------------------------------------------

WEBHOOK_STATE_FILE="$ROOT_DIR/tmp/webhook_dispatch_state.json"

start_webhook_receiver() {
  local port="$1"
  local status_code="${2:-200}"
  local retry_count="${3:-0}"

  # Reset state file
  echo '{"requests":[],"port":'$port',"target_status":'$status_code',"retry_count":'$retry_count'}' > "$WEBHOOK_STATE_FILE"

  python3 - "$port" "$status_code" "$retry_count" "$WEBHOOK_STATE_FILE" <<'PYEOF'
import sys, json, threading, http.server, os

PORT = int(sys.argv[1])
TARGET_STATUS = int(sys.argv[2])
RETRY_COUNT = int(sys.argv[3])
STATE_FILE = sys.argv[4]

lock = threading.Lock()
call_count = 0

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence default logging

    def do_POST(self):
        global call_count
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        headers = dict(self.headers)

        with lock:
            call_count += 1
            current = call_count

        # For retry testing: fail first N times
        if RETRY_COUNT > 0 and current <= RETRY_COUNT:
            status = 500
            resp = json.dumps({"error": "simulated failure", "attempt": current}).encode()
        else:
            status = TARGET_STATUS
            resp = json.dumps({"ok": True, "attempt": current}).encode()

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(resp)

        # Append request to state file
        with lock:
            try:
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
            except Exception:
                state = {"requests": [], "port": PORT}
            state["requests"].append({
                "attempt": current,
                "status": status,
                "path": self.path,
                "headers": {k: v for k, v in headers.items()},
                "body": json.loads(body.decode()) if body else None,
            })
            with open(STATE_FILE, "w") as f:
                json.dump(state, f)

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        with lock:
            try:
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
            except Exception:
                state = {"requests": [], "port": PORT}
        self.wfile.write(json.dumps({"received": len(state.get("requests", []))}).encode())

httpd = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
print(f"WEBHOOK_LISTENING:{PORT}", flush=True)
httpd.serve_forever()
PYEOF

  WEBHOOK_PID=$!
  # Wait until server is ready
  local output
  output="$(wait_for_webhook_ready "$WEBHOOK_PID" 10)"
  echo "$output"
}

wait_for_webhook_ready() {
  local pid="$1"
  local timeout="$2"
  local elapsed=0
  while (( elapsed < timeout )); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "WEBHOOK_DEAD"
      return 1
    fi
    if curl -sf "http://127.0.0.1:0/" >/dev/null 2>&1; then
      echo "WEBHOOK_READY"
      return 0
    fi
    sleep 0.2
    elapsed=$((elapsed + 1))
  done
  echo "WEBHOOK_TIMEOUT"
  return 1
}

stop_webhook_receiver() {
  if [[ -n "$WEBHOOK_PID" ]] && kill -0 "$WEBHOOK_PID" 2>/dev/null; then
    kill "$WEBHOOK_PID" 2>/dev/null || true
    wait "$WEBHOOK_PID" 2>/dev/null || true
    WEBHOOK_PID=""
  fi
}

cleanup() {
  set +e
  stop_webhook_receiver
  restore_agent_access_policy 2>/dev/null || true
  set -e
}

trap cleanup EXIT

# --------------------------------------------------------------------------
# Step 0 — Start webhook receiver
# --------------------------------------------------------------------------

WEBHOOK_PORT=18090
info "$my_name" "Starting local webhook receiver on port ${WEBHOOK_PORT}"
start_webhook_receiver "$WEBHOOK_PORT" 200 0 &>/dev/null &
WEBHOOK_PID=$!

# Wait for the server to be ready by polling
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${WEBHOOK_PORT}/" >/dev/null 2>&1; then
    info "$my_name" "Webhook receiver ready on port ${WEBHOOK_PORT}"
    break
  fi
  if (( i == 30 )); then
    error "$my_name" "Webhook receiver failed to start within 6s"
    exit 1
  fi
  sleep 0.2
done

WEBHOOK_URL="http://127.0.0.1:${WEBHOOK_PORT}/webhook"

# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

mint_access_token() {
  local username="$1"
  local password="$2"
  local token_endpoint="${SSO_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"
  dq_keycloak_password_grant_access_token "$token_endpoint" "$VITE_KEYCLOAK_CLIENT_ID" "$username" "$password"
}

api_call() {
  local token="$1" method="$2" endpoint="$3"
  local body="${4-}"
  local response_file headers_file code

  response_file="$(mktemp "$ROOT_DIR/tmp/dispatch_resp_XXXXXX.json")"
  headers_file="$(mktemp "$ROOT_DIR/tmp/dispatch_hdr_XXXXXX.txt")"

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
      -H "X-Request-Id: dispatch-smoke-$(date +%s)" \
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
      -H "X-Request-Id: dispatch-smoke-$(date +%s)")"
  fi
  set -e

  HTTP_CODE="$code"
  HTTP_BODY="$(cat "$response_file")"
  rm -f "$response_file" "$headers_file"
}

set_agent_access_policy() {
  local payload
  payload="$(jq -nc --argjson agent_access_policy "$1" '{agent_access_policy: $agent_access_policy}')"
  api_call "$CONFIG_TOKEN" PUT "/system/v1/app-config" "$payload"
  if [[ "$HTTP_CODE" != "200" ]]; then
    error "$my_name" "PUT /system/v1/app-config returned HTTP ${HTTP_CODE}"
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
  fi
}

restore_agent_access_policy() {
  if [[ -z "$CONFIG_TOKEN" || -z "$ORIGINAL_AGENT_ACCESS_POLICY" ]]; then
    return 0
  fi
  set_agent_access_policy "$ORIGINAL_AGENT_ACCESS_POLICY" 2>/dev/null || true
}

info "$my_name" "Minting auth tokens"
rw_token="$(mint_access_token "$SMOKE_LOGIN_EMAIL" "$SMOKE_LOGIN_PASSWORD")"
admin_email="${KEYCLOAK_JACCLOUD_USERNAME:-$SMOKE_LOGIN_EMAIL}"
admin_password="${KEYCLOAK_JACCLOUD_PASSWORD:-$SMOKE_LOGIN_PASSWORD}"
admin_token="$(mint_access_token "$admin_email" "$admin_password")"

# Grab app-config and set agent access policy
for candidate_token in "$rw_token" "$admin_token"; do
  api_call "$candidate_token" GET "/system/v1/app-config"
  if [[ "$HTTP_CODE" == "200" ]]; then
    CONFIG_TOKEN="$candidate_token"
    ORIGINAL_AGENT_ACCESS_POLICY="$(printf '%s' "$HTTP_BODY" | jq -c '.agent_access_policy // null')"
    break
  fi
done

if [[ -z "$CONFIG_TOKEN" ]]; then
  error "$my_name" "Could not read /system/v1/app-config"
  exit 1
fi

if [[ "$ORIGINAL_AGENT_ACCESS_POLICY" == "null" ]]; then
  ORIGINAL_AGENT_ACCESS_POLICY='{"default_action":"deny","allowed_agents":[]}'
fi

temp_policy="$(jq -nc \
  --argjson original "$ORIGINAL_AGENT_ACCESS_POLICY" \
  --arg agent_type "$agent_type" \
  --arg agent_source "$agent_source" '
    ($original // {"default_action":"deny","allowed_agents":[]}) as $p |
    {
      default_action: ($p.default_action // "deny"),
      allowed_agents: (($p.allowed_agents // []) + [{agent_type: $agent_type, agent_source: $agent_source}])
        | unique_by([.agent_type, .agent_source])
    }
  ')"

set_agent_access_policy "$temp_policy"

# --------------------------------------------------------------------------
# Test 1 — Successful webhook delivery
# --------------------------------------------------------------------------

info "$my_name" "Test 1: Successful webhook delivery"

dispatch_payload="$(jq -nc \
  --arg webhook_url "$WEBHOOK_URL" \
  '{
    platform: "mistral_ai",
    dispatch_mode: "webhook",
    event_type: "dq.alert.created",
    webhook_url: $webhook_url,
    webhook_headers: {"x-test": "smoke"},
    payload: {"delivery_id": "delivery-smoke-001", "alert_kind": "sla_breach", "rule_id": "rule-smoke-001"}
  }')"

api_call "$rw_token" POST "/agent/v1/integrations/dispatches" "$dispatch_payload"

if [[ "$HTTP_CODE" != "200" ]]; then
  error "$my_name" "Dispatch returned HTTP ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

dispatch_status="$(printf '%s' "$HTTP_BODY" | jq -r '.status // empty')"
if [[ "$dispatch_status" != "delivered" ]]; then
  error "$my_name" "Expected status 'delivered', got '${dispatch_status}'"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

delivery_result="$(printf '%s' "$HTTP_BODY" | jq -c '.delivery_result // empty')"
if [[ -z "$delivery_result" || "$delivery_result" == "null" ]]; then
  error "$my_name" "delivery_result missing from response"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

http_status="$(printf '%s' "$HTTP_BODY" | jq -r '.delivery_result.http_status_code // empty')"
if [[ "$http_status" != "200" ]]; then
  error "$my_name" "Expected delivery http_status_code=200, got '${http_status}'"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

delivered_at="$(printf '%s' "$HTTP_BODY" | jq -r '.delivered_at // empty')"
if [[ -z "$delivered_at" ]]; then
  error "$my_name" "delivered_at missing from response"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

info "$my_name" "Dispatch status=delivered, http_status=${http_status} — PASS"

# --------------------------------------------------------------------------
# Test 2 — Verify webhook receiver got the envelope
# --------------------------------------------------------------------------

info "$my_name" "Test 2: Verify webhook receiver got the envelope"

# Read the state file to check what the receiver captured
sleep 0.5  # give the file system a moment
if [[ ! -f "$WEBHOOK_STATE_FILE" ]]; then
  error "$my_name" "Webhook state file not found"
  exit 1
fi

request_count="$(jq '.requests | length' "$WEBHOOK_STATE_FILE")"
if [[ "$request_count" -lt 1 ]]; then
  error "$my_name" "Webhook receiver got 0 requests"
  exit 1
fi

# Verify envelope structure
envelope_metadata="$(jq -r '.requests[0].body.metadata // empty' "$WEBHOOK_STATE_FILE")"
if [[ -z "$envelope_metadata" || "$envelope_metadata" == "null" ]]; then
  error "$my_name" "Webhook payload missing metadata envelope"
  exit 1
fi

envelope_platform="$(jq -r '.requests[0].body.metadata.platform // empty' "$WEBHOOK_STATE_FILE")"
if [[ "$envelope_platform" != "mistral_ai" ]]; then
  error "$my_name" "Expected envelope platform 'mistral_ai', got '${envelope_platform}'"
  exit 1
fi

envelope_source="$(jq -r '.requests[0].body.metadata.source // empty' "$WEBHOOK_STATE_FILE")"
if [[ "$envelope_source" != "dq-made-easy" ]]; then
  error "$my_name" "Expected envelope source 'dq-made-easy', got '${envelope_source}'"
  exit 1
fi

envelope_event="$(jq -r '.requests[0].body.event.type // empty' "$WEBHOOK_STATE_FILE")"
if [[ "$envelope_event" != "dq.alert.created" ]]; then
  error "$my_name" "Expected envelope event.type 'dq.alert.created', got '${envelope_event}'"
  exit 1
fi

envelope_data="$(jq -r '.requests[0].body.data.delivery_id // empty' "$WEBHOOK_STATE_FILE")"
if [[ "$envelope_data" != "delivery-smoke-001" ]]; then
  error "$my_name" "Expected data.delivery_id 'delivery-smoke-001', got '${envelope_data}'"
  exit 1
fi

info "$my_name" "Envelope structure verified (platform=${envelope_platform}, source=${envelope_source}, event=${envelope_event}) — PASS"

# --------------------------------------------------------------------------
# Test 3 — Audit trail records delivery result
# --------------------------------------------------------------------------

info "$my_name" "Test 3: Verify audit trail carries delivery result"

api_call "$admin_token" GET "/agent/v1/audit/events?limit=20&offset=0"
if [[ "$HTTP_CODE" != "200" ]]; then
  error "$my_name" "GET /agent/v1/audit/events returned HTTP ${HTTP_CODE}"
  exit 1
fi

audit_count="$(printf '%s' "$HTTP_BODY" | jq '[.events[] | select(.action == "dispatch_platform_integration")] | length')"
if [[ "$audit_count" -lt 1 ]]; then
  error "$my_name" "No dispatch_platform_integration audit events found"
  exit 1
fi

# Check the last dispatch event has delivery_status
last_dispatch="$(printf '%s' "$HTTP_BODY" | jq '.events | [ .[] | select(.action == "dispatch_platform_integration") ] | last')"
audit_delivery_status="$(printf '%s' "$last_dispatch" | jq -r '.details.delivery_status // empty')"
if [[ "$audit_delivery_status" != "delivered" ]]; then
  error "$my_name" "Expected audit delivery_status 'delivered', got '${audit_delivery_status}'"
  exit 1
fi

info "$my_name" "Audit trail records delivery_status=delivered — PASS"

# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Test 4 — MCP client connects and processes webhook event
# --------------------------------------------------------------------------

info "$my_name" "Test 4: MCP client processes webhook event"

# Write the webhook payload to a file for the MCP client
WEBHOOK_EVENT_FILE="$ROOT_DIR/tmp/webhook_dispatch_event.json"
jq -nc \
  --arg webhook_url "$WEBHOOK_URL" \
  '{
    metadata: {
      dispatch_id: "smoke-mcp-dispatch",
      platform: "mistral_ai",
      source: "dq-made-easy",
      contract_version: "1.0",
      sent_at: (now | todate)
    },
    event: {
      type: "dq.alert.created",
      timestamp: (now | todate)
    },
    data: {
      delivery_id: "delivery-smoke-001",
      alert_kind: "sla_breach",
      rule_id: "rule-smoke-001",
      workspace: "smoke-test-workspace"
    }
  }' > "$WEBHOOK_EVENT_FILE"

# Build MCP server command
MCP_SERVER_CMD="python3 -m dq_cli.mcp_server --base-url ${KONG_PUBLIC_URL%/} --timeout-seconds 30"
if [[ -n "$rw_token" ]]; then
  MCP_SERVER_CMD="$MCP_SERVER_CMD --token $rw_token"
fi

# Run the MCP test client
MCP_OUTPUT_FILE="$ROOT_DIR/tmp/mcp_dispatch_test_output.json"
python3 -m dq_cli.mcp_test_client \
  --server-cmd "$MCP_SERVER_CMD" \
  --scenario webhook_dispatch \
  --webhook-file "$WEBHOOK_EVENT_FILE" \
  --output-file "$MCP_OUTPUT_FILE" \
  --timeout-seconds 30

mcp_rc=$?
if [[ $mcp_rc -ne 0 ]]; then
  error "$my_name" "MCP test client failed (rc=${mcp_rc})"
  cat "$MCP_OUTPUT_FILE" >&2 2>/dev/null || true
  exit 1
fi

# Verify MCP test results
if [[ -f "$MCP_OUTPUT_FILE" ]]; then
  mcp_success=$(jq -r '.success // "false"' "$MCP_OUTPUT_FILE")
  if [[ "$mcp_success" == "true" ]]; then
    info "$my_name" "MCP client processed webhook event successfully — PASS"
  else
    error "$my_name" "MCP client test did not pass"
    cat "$MCP_OUTPUT_FILE" >&2
    exit 1
  fi
fi

# --------------------------------------------------------------------------
# Done
# --------------------------------------------------------------------------

info "$my_name" "============================================"
success "$my_name" "Webhook dispatch smoke test passed — outbound delivery is operational"
