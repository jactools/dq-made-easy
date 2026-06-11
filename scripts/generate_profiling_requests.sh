#!/usr/bin/env bash
set -euo pipefail


# Purpose: Enqueue repeated profiling requests for load/testing.
#
# What it does:
# - Loads generator settings from the repo .env file.
# - Obtains a Keycloak bearer token (password grant).
# - Sends profiling enqueue requests at a configured interval.
#
# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="generate_profiling_requests.sh"

print_usage() {
  cat <<'EOF'
Usage: generate_profiling_requests.sh [OPTIONS]

Enqueues repeated profiling requests without waiting for completion.

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file

Required environment values:
  PROFILING_REQUEST_GENERATOR_COUNT             Number of requests to enqueue
  PROFILING_REQUEST_GENERATOR_INTERVAL_SECONDS  Seconds to wait between requests
  PROFILING_REQUEST_GENERATOR_REQUEST_TYPE      Request type to send in the payload
  PROFILING_REQUEST_GENERATOR_PAYLOAD_KIND      Payload variant label for the generated body
  PROFILING_REQUEST_GENERATOR_DATA_SOURCE_ID    Data source id to include in each request
  PROFILING_REQUEST_GENERATOR_REQUESTED_BY_USER_ID  User id to include in each request
  PROFILING_REQUEST_GENERATOR_TOKEN_USERNAME    Keycloak username used for password-grant authentication
  PROFILING_REQUEST_GENERATOR_TOKEN_PASSWORD    Keycloak password used for password-grant authentication
  PROFILING_REQUEST_GENERATOR_TOKEN_CLIENT_ID   Keycloak client id used for password-grant authentication
EOF
}

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 1
fi

set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      error "$my_name" "Unknown argument: $1"
      print_usage
      exit 1
      ;;
  esac
done

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "$my_name" "Missing ${ROOT_ENV_FILE}. Create the selected canonical env file and set the profiling generator values there."
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

set -a
source "$ROOT_ENV_FILE"
set +a

SESSION_DATABASE_URL="${DQ_DB_LOCAL_URL:?Set DQ_DB_LOCAL_URL in .env or environment}"

: "${PROFILING_REQUEST_GENERATOR_COUNT:?Set PROFILING_REQUEST_GENERATOR_COUNT in .env or environment}"
: "${PROFILING_REQUEST_GENERATOR_INTERVAL_SECONDS:?Set PROFILING_REQUEST_GENERATOR_INTERVAL_SECONDS in .env or environment}"
: "${PROFILING_REQUEST_GENERATOR_REQUEST_TYPE:?Set PROFILING_REQUEST_GENERATOR_REQUEST_TYPE in .env or environment}"
: "${PROFILING_REQUEST_GENERATOR_PAYLOAD_KIND:?Set PROFILING_REQUEST_GENERATOR_PAYLOAD_KIND in .env or environment}"
: "${PROFILING_REQUEST_GENERATOR_DATA_SOURCE_ID:?Set PROFILING_REQUEST_GENERATOR_DATA_SOURCE_ID in .env or environment}"
: "${PROFILING_REQUEST_GENERATOR_REQUESTED_BY_USER_ID:?Set PROFILING_REQUEST_GENERATOR_REQUESTED_BY_USER_ID in .env or environment}"
: "${PROFILING_REQUEST_GENERATOR_TOKEN_USERNAME:?Set PROFILING_REQUEST_GENERATOR_TOKEN_USERNAME in .env or environment}"
: "${PROFILING_REQUEST_GENERATOR_TOKEN_PASSWORD:?Set PROFILING_REQUEST_GENERATOR_TOKEN_PASSWORD in .env or environment}"
: "${PROFILING_REQUEST_GENERATOR_TOKEN_CLIENT_ID:?Set PROFILING_REQUEST_GENERATOR_TOKEN_CLIENT_ID in .env or environment}"
: "${KONG_LOCAL_URL:?Set KONG_LOCAL_URL in .env or environment}"
: "${SSO_PUBLIC_ISSUER_URL:?Set SSO_PUBLIC_ISSUER_URL in .env or environment}"

PROFILING_GATEWAY_LOCAL_URL="${KONG_LOCAL_URL%/}/rulebuilder/v1/profiling/enqueue"
PROFILING_REQUEST_GENERATOR_TOKEN_PUBLIC_URL="${SSO_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: ${cmd}"
    exit 1
  fi
}

require_cmd curl
require_cmd jq
require_cmd psql

if ! [[ "$PROFILING_REQUEST_GENERATOR_COUNT" =~ ^[0-9]+$ ]] || (( PROFILING_REQUEST_GENERATOR_COUNT < 1 )); then
  error "$my_name" "PROFILING_REQUEST_GENERATOR_COUNT must be a positive integer"
  exit 1
fi

if ! [[ "$PROFILING_REQUEST_GENERATOR_INTERVAL_SECONDS" =~ ^[0-9]+$ ]] || (( PROFILING_REQUEST_GENERATOR_INTERVAL_SECONDS < 0 )); then
  error "$my_name" "PROFILING_REQUEST_GENERATOR_INTERVAL_SECONDS must be a non-negative integer"
  exit 1
fi

tmp_dir="$(mktemp -d /tmp/profiling-request-generator.XXXXXX)"
headers_file="${tmp_dir}/headers.txt"
body_file="${tmp_dir}/body.json"
login_headers_file="${tmp_dir}/login-headers.txt"
login_body_file="${tmp_dir}/login-body.json"

cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

info "$my_name" "=== Profiling Request Generator ==="
info "$my_name" "Env file: ${ROOT_ENV_FILE}"
info "$my_name" "Gateway URL: ${PROFILING_GATEWAY_LOCAL_URL}"
info "$my_name" "Count: ${PROFILING_REQUEST_GENERATOR_COUNT}"
info "$my_name" "Interval seconds: ${PROFILING_REQUEST_GENERATOR_INTERVAL_SECONDS}"
info "$my_name" "Request type: ${PROFILING_REQUEST_GENERATOR_REQUEST_TYPE}"
info "$my_name" "Data source ID: ${PROFILING_REQUEST_GENERATOR_DATA_SOURCE_ID:-<auto-resolved>}"
info "$my_name" "Requested by user ID: ${PROFILING_REQUEST_GENERATOR_REQUESTED_BY_USER_ID:-<auto-resolved>}"
info "$my_name" "Token URL: ${PROFILING_REQUEST_GENERATOR_TOKEN_PUBLIC_URL}"
info "$my_name" "Token client ID: ${PROFILING_REQUEST_GENERATOR_TOKEN_CLIENT_ID}"
info "$my_name" "Token username: ${PROFILING_REQUEST_GENERATOR_TOKEN_USERNAME}"

info "$my_name" "Authenticating to obtain bearer token"
curl -sS \
  -D "$login_headers_file" \
  -o "$login_body_file" \
  -X POST "$PROFILING_REQUEST_GENERATOR_TOKEN_PUBLIC_URL" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "grant_type=password" \
  --data-urlencode "client_id=${PROFILING_REQUEST_GENERATOR_TOKEN_CLIENT_ID}" \
  --data-urlencode "username=${PROFILING_REQUEST_GENERATOR_TOKEN_USERNAME}" \
  --data-urlencode "password=${PROFILING_REQUEST_GENERATOR_TOKEN_PASSWORD}"

login_http_status="$(awk 'NR==1 {print $2}' "$login_headers_file")"
if [[ "$login_http_status" != "200" ]]; then
  error "$my_name" "Expected HTTP 200 from login request, got ${login_http_status}"
  sed -n '1,20p' "$login_headers_file" >&2
  sed -n '1,40p' "$login_body_file" >&2
  exit 1
fi

auth_token="$(jq -r '.access_token // empty' "$login_body_file")"
if [[ -z "$auth_token" ]]; then
  error "$my_name" "Login response did not include a token"
  sed -n '1,40p' "$login_body_file" >&2
  exit 1
fi

session_id="$("$PYTHON_RUNNER" --python-bin python3 - "$auth_token" <<'PY'
import base64
import json
import sys

token = sys.argv[1]
parts = token.split('.')
if len(parts) < 2:
    print('')
    raise SystemExit(0)

segment = parts[1]
padding = '=' * ((4 - len(segment) % 4) % 4)
claims = json.loads(base64.urlsafe_b64decode(segment + padding))
print(str(claims.get('sid') or '').strip())
PY
)"

if [[ -z "$session_id" ]]; then
  error "$my_name" "JWT did not include an sid claim"
  sed -n '1,40p' "$login_body_file" >&2
  exit 1
fi

info "$my_name" "Seeding session record for sid ${session_id}"
psql "$SESSION_DATABASE_URL" -v ON_ERROR_STOP=1 -v sid="$session_id" -v user_id="$PROFILING_REQUEST_GENERATOR_REQUESTED_BY_USER_ID" <<'SQL'
INSERT INTO sessions (id, user_id, last_activity)
VALUES (:'sid', :'user_id', NOW())
ON CONFLICT (id) DO UPDATE
SET user_id = EXCLUDED.user_id,
    last_activity = EXCLUDED.last_activity;
SQL

success "$my_name" "Authenticated successfully"

for index in $(seq 1 "$PROFILING_REQUEST_GENERATOR_COUNT"); do
  unique="$("$PYTHON_RUNNER" --python-bin python3 - <<'PY'
import secrets
print(secrets.token_hex(6))
PY
)"
  profiling_request_id="pr-live-gen-${unique}-${index}"
  job_id="job-live-gen-${unique}-${index}"
  correlation_id="kong-gen-correlation-${unique}-${index}"
  request_id="kong-gen-request-${unique}-${index}"

  payload="$(jq -cn \
    --arg payload_kind "$PROFILING_REQUEST_GENERATOR_PAYLOAD_KIND" \
    --arg request_type "$PROFILING_REQUEST_GENERATOR_REQUEST_TYPE" \
    --arg data_source_id "${PROFILING_REQUEST_GENERATOR_DATA_SOURCE_ID:-}" \
    --arg requested_by_user_id "${PROFILING_REQUEST_GENERATOR_REQUESTED_BY_USER_ID:-}" \
    --arg job_id "$job_id" \
    --arg profiling_request_id "$profiling_request_id" \
    '{
      type: $request_type,
      payload: {
        kind: $payload_kind,
        sourceConfig: {
          inlineData: [
            { id: "1", name: "Alice", country: "US" },
            { id: "2", name: "Bob", country: "UK" },
            { id: "3", name: "Carol", country: "US" }
          ]
        },
        transformSpec: {
          filter: {
            field: "country",
            equals: "US"
          },
          selectFields: ["id", "name"]
        }
      },
      data_source_id: $data_source_id,
      requested_by_user_id: $requested_by_user_id,
      job_id: $job_id,
      profiling_request_id: $profiling_request_id
    }')"

  info "$my_name" "[${index}/${PROFILING_REQUEST_GENERATOR_COUNT}] Enqueuing ${job_id}"
  curl -sS \
    -D "$headers_file" \
    -o "$body_file" \
    -X POST "$PROFILING_GATEWAY_LOCAL_URL" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer ${auth_token}" \
    -H "X-Kong-Request-Id: ${request_id}" \
    -H "X-Correlation-ID: ${correlation_id}" \
    -d "$payload"

  http_status="$(awk 'NR==1 {print $2}' "$headers_file")"
  if [[ "$http_status" != "200" ]]; then
    error "$my_name" "Expected HTTP 200 from enqueue request, got ${http_status}"
    sed -n '1,20p' "$headers_file" >&2
    sed -n '1,40p' "$body_file" >&2
    exit 1
  fi

  response_job_id="$(jq -r '.job_id // empty' "$body_file")"
  response_enqueued="$(jq -r '.enqueued // false' "$body_file")"

  if [[ "$response_enqueued" != "true" || "$response_job_id" != "$job_id" ]]; then
    error "$my_name" "Unexpected enqueue response body for ${job_id}"
    sed -n '1,40p' "$body_file" >&2
    exit 1
  fi

  success "$my_name" "accepted: profiling_request_id=${profiling_request_id} job_id=${response_job_id}"

  if (( index < PROFILING_REQUEST_GENERATOR_COUNT )) && (( PROFILING_REQUEST_GENERATOR_INTERVAL_SECONDS > 0 )); then
    sleep "$PROFILING_REQUEST_GENERATOR_INTERVAL_SECONDS"
  fi
done

success "$my_name" "Enqueued ${PROFILING_REQUEST_GENERATOR_COUNT} profiling requests successfully."