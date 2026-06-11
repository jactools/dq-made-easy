#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate profiling worker failure path end-to-end.
#
# What it does:
# - Enqueues a profiling request through the internal API service designed to fail.
# - Polls Postgres for failed status and non-empty error_message.
# - Verifies the worker logs show the job.
#
# validate: groups=profiling
# validate: include=false

# Version: 1.0
# Last modified: 2026-04-07

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/../supporting/profiling_validation_common.sh"

my_name="validate_profiling_worker_failure.sh"

DATA_SOURCE_ID="${DATA_SOURCE_ID:-}"
REQUESTED_BY_USER_ID="${REQUESTED_BY_USER_ID:-}"
WAIT_SECONDS="${WAIT_SECONDS:-12}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-1}"
FAILURE_TRIGGER_VALUE="${FAILURE_TRIGGER_VALUE:-filter}"

print_usage() {
  cat <<'EOF'
Usage: validate_profiling_worker_failure.sh

Environment overrides:
  DQ_API_LOCAL_URL         Host-local API base URL used to derive the enqueue endpoint
  DB_CONTAINER             Postgres container name
  WORKER_CONTAINER         Profiling worker container name
  DATABASE_NAME            Postgres database name
  DATABASE_USER            Postgres user name
  DATA_SOURCE_ID           Existing FK-safe data source id
  REQUESTED_BY_USER_ID     Existing FK-safe user id
  WAIT_SECONDS             Max seconds to wait for failed status
  POLL_INTERVAL_SECONDS    Poll interval while waiting for DB status
  FAILURE_TRIGGER_VALUE    Invalid transformSpec value that forces ETL failure
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  print_usage
  exit 0
fi

require_cmd curl
require_cmd docker
require_cmd jq

resolve_fk_defaults

unique="$("$PYTHON_RUNNER" --python-bin python3 - <<'PY'
import secrets
print(secrets.token_hex(6))
PY
)"
profiling_request_id="pr-live-fail-${unique}"
job_id="job-live-fail-${unique}"
correlation_id="kong-fail-correlation-${unique}"
request_id="kong-fail-request-${unique}"
tmp_dir="$(mktemp -d /tmp/profiling-worker-failure.XXXXXX)"
headers_file="${tmp_dir}/headers.txt"
body_file="${tmp_dir}/body.json"

cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

info "$my_name" "=== Profiling Worker Failure Validation ==="
info "$my_name" "Internal API URL: ${PROFILING_API_URL}"
info "$my_name" "Profiling request ID: ${profiling_request_id}"
info "$my_name" "Job ID: ${job_id}"
info "$my_name" "Correlation ID: ${correlation_id}"
info "$my_name" "Data source ID: ${DATA_SOURCE_ID}"
info "$my_name" "Requested by user ID: ${REQUESTED_BY_USER_ID}"

payload="$(jq -cn \
  --arg failure_trigger "$FAILURE_TRIGGER_VALUE" \
  --arg data_source_id "$DATA_SOURCE_ID" \
  --arg requested_by_user_id "$REQUESTED_BY_USER_ID" \
  --arg job_id "$job_id" \
  --arg profiling_request_id "$profiling_request_id" \
  '{
    type: "etl",
    payload: {
      sourceConfig: {
        inlineData: [
          { id: "1" }
        ]
      },
      transformSpec: $failure_trigger
    },
    data_source_id: $data_source_id,
    requested_by_user_id: $requested_by_user_id,
    job_id: $job_id,
    profiling_request_id: $profiling_request_id
  }')"

info "$my_name" "[1/4] Sending internal profiling enqueue request..."
curl -sS \
  -D "$headers_file" \
  -o "$body_file" \
  -X POST "$PROFILING_API_URL" \
  -H 'Content-Type: application/json' \
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
  error "$my_name" "Unexpected enqueue response body"
  sed -n '1,40p' "$body_file" >&2
  exit 1
fi

info "$my_name" "[2/4] Polling Postgres for failed worker status..."
db_row=""
attempts=$(( WAIT_SECONDS / POLL_INTERVAL_SECONDS ))
if (( attempts < 1 )); then
  attempts=1
fi

for _ in $(seq 1 "$attempts"); do
  db_row="$(db_psql_query "select id, status, started_at is not null, completed_at is not null, job_id, coalesce(error_message,'') from data_source_profiling_requests where id = '$profiling_request_id';")"
  if [[ -n "$db_row" ]]; then
    IFS='|' read -r row_id row_status row_started row_completed row_job_id row_error <<< "$db_row"
    if [[ "$row_status" == "failed" && "$row_started" == "t" && "$row_completed" == "t" && "$row_job_id" == "$job_id" && -n "$row_error" ]]; then
      break
    fi
  fi
  sleep "$POLL_INTERVAL_SECONDS"
done

if [[ -z "$db_row" ]]; then
  error "$my_name" "No profiling request row was created for ${profiling_request_id}"
  exit 1
fi

IFS='|' read -r row_id row_status row_started row_completed row_job_id row_error <<< "$db_row"
if [[ "$row_status" != "failed" || "$row_started" != "t" || "$row_completed" != "t" || "$row_job_id" != "$job_id" || -z "$row_error" ]]; then
  error "$my_name" "Profiling request row did not reach the expected failed state"
  echo "$db_row" >&2
  exit 1
fi

info "$my_name" "[3/4] Checking profiling worker logs for the same job ID..."
worker_log_matches="$(profiling_worker_logs "$((WAIT_SECONDS + 15))" | grep -F "$job_id" || true)"
if [[ -z "$worker_log_matches" ]]; then
  error "$my_name" "Worker logs do not contain ${job_id}"
  exit 1
fi

info "$my_name" "[4/4] Validation summary"
info "$my_name" "HTTP status: ${http_status}"
info "$my_name" "Trace ID: $(awk 'tolower($1)=="x-trace-id:" {gsub("\r", "", $2); print $2}' "$headers_file" | tail -1)"
info "$my_name" "DB row: ${db_row}"
info "$my_name" "Worker log excerpt:"
printf '%s\n' "$worker_log_matches" | tail -n 5
success "$my_name" "The internal API accepted the request and the worker marked it failed with an error message."