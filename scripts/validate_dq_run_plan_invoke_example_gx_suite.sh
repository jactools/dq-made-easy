#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate that dq-run-plan can replay the repo-provided GX suite YAML and produce a real GX run.
#
# What it does:
# - Loads the selected repo env file and seeded user credentials.
# - Invokes dq-run-plan invoke with validation-data/example_gx_suite.yml.
# - Confirms the CLI returns run_id and queue_message_id, then polls GET /rulebuilder/v1/gx/runs/{run_id} until the run succeeds.
#
# validate: groups=api,cli,regression
# Version: 1.0.1
# Last modified: 2026-07-01

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
PYTHON_RUNNER="${ROOT_DIR}/scripts/python_arm64.sh"
CLI_MODULE_DIR="${ROOT_DIR}/dq-cli"
MY_NAME="validate_dq_run_plan_invoke_example_gx_suite.sh"
EXAMPLE_GX_SUITE_YML="${ROOT_DIR}/validation-data/example_gx_suite.yml"
POLL_TIMEOUT_SECONDS="${DQ_VALIDATION_RUN_TIMEOUT_SECONDS:-900}"
POLL_INTERVAL_SECONDS="${DQ_VALIDATION_RUN_POLL_INTERVAL_SECONDS:-5}"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

print_usage() {
  cat <<'EOF'
Usage: scripts/validate_dq_run_plan_invoke_example_gx_suite.sh

Options:
  --env dev|test|prod
                     Select the root env file using the common repo env selector
  -h, --help         Show this help
EOF
}

require_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    error "$MY_NAME" "Missing required command: $name"
    exit 2
  fi
}

run_cli() {
  local -a cli_args=("$@")
  local cli_output
  set +e
  cli_output="$(PYTHONPATH="$CLI_MODULE_DIR${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m dq_cli.run_plan "${cli_args[@]}")"
  local cli_rc=$?
  set -e
  if [[ "$cli_rc" -ne 0 ]]; then
    printf '%s\n' "$cli_output" >&2
    exit "$cli_rc"
  fi
  printf '%s' "$cli_output"
}

login_dq_api_session() {
  local cookie_jar="$1"
  local response_file
  local headers_file
  local http_code
  local curl_rc
  local login_payload
  local login_token
  local session_cookie_line
  local session_cookie_value

  login_payload="$(jq -n --arg email "$KEYCLOAK_JACCLOUD_USERNAME" '{email: $email, sso: false}')"
  response_file="$(mktemp)"
  headers_file="$(mktemp)"

  set +e
  http_code="$(curl -sS "${CURL_TLS_ARGS[@]}" -D "$headers_file" -c "$cookie_jar" -o "$response_file" -w '%{http_code}' \
    -X POST \
    -H 'Content-Type: application/json' \
    -H "X-Kong-Request-Id: ${REQUEST_ID}" \
    -H "X-Correlation-ID: ${CORRELATION_ID}" \
    --data "$login_payload" \
    "${DQ_API_LOCAL_URL%/}/auth/v1/login")"
  curl_rc=$?
  set -e

  if [[ "$curl_rc" -ne 0 ]]; then
    error "$MY_NAME" "DQ API login request failed"
    cat "$response_file" >&2 || true
    cat "$headers_file" >&2 || true
    rm -f "$response_file"
    rm -f "$headers_file"
    exit "$curl_rc"
  fi

  if [[ "$http_code" -ne 200 ]]; then
    error "$MY_NAME" "DQ API login returned HTTP ${http_code}"
    cat "$response_file" >&2 || true
    cat "$headers_file" >&2 || true
    rm -f "$response_file"
    rm -f "$headers_file"
    exit 1
  fi

  login_token="$(jq -r '.token // empty' "$response_file")"
  if [[ -z "$login_token" ]]; then
    error "$MY_NAME" "DQ API login did not return a token"
    cat "$response_file" >&2 || true
    cat "$headers_file" >&2 || true
    rm -f "$response_file"
    rm -f "$headers_file"
    exit 1
  fi

  if [[ ! -s "$cookie_jar" ]] || ! grep -q 'dq_session' "$cookie_jar"; then
    error "$MY_NAME" "DQ API login did not set the dq_session cookie"
    cat "$response_file" >&2 || true
    cat "$headers_file" >&2 || true
    rm -f "$response_file"
    rm -f "$headers_file"
    exit 1
  fi

  session_cookie_line="$(grep -i '^set-cookie: dq_session=' "$headers_file" | tail -n 1 || true)"
  session_cookie_value="${session_cookie_line#*dq_session=}"
  session_cookie_value="${session_cookie_value%%;*}"
  session_cookie_value="${session_cookie_value%%$'\r'}"

  if [[ -z "$session_cookie_value" ]]; then
    error "$MY_NAME" "DQ API login did not return a dq_session cookie value"
    cat "$response_file" >&2 || true
    cat "$headers_file" >&2 || true
    rm -f "$response_file"
    rm -f "$headers_file"
    exit 1
  fi

  DQ_SESSION_COOKIE_VALUE="$session_cookie_value"
  DQ_API_LOGIN_TOKEN="$login_token"

  rm -f "$response_file"
  rm -f "$headers_file"
}

bootstrap_example_gx_suite_source() {
  local source_csv_path
  local engine_stage_container_id
  local helper_container_path
  local container_csv_path
  local stage_output_json
  local output_uri
  local output_format
  local escaped_version_id

  source_csv_path="$ROOT_DIR/data_sources/teller_machine/customer_atm_transactions.csv"
  if [[ ! -f "$source_csv_path" ]]; then
    error "$MY_NAME" "Missing teller machine source CSV: $source_csv_path"
    exit 1
  fi

  engine_stage_container_id="$(docker compose ps -q dq-engine-test-data-worker | head -n 1 | tr -d '[:space:]')"
  redis_container_id="$(docker compose ps -q redis | head -n 1 | tr -d '[:space:]')"
  if [[ -z "$engine_stage_container_id" || -z "$redis_container_id" ]]; then
    error "$MY_NAME" "Required redis and dq-engine-test-data-worker containers must already be running for local CSV parquet staging"
    exit 1
  fi

  helper_container_path="/var/tmp/stage_local_csv_to_s3_parquet.py"
  container_csv_path="/var/tmp/example_gx_suite_customer_atm_transactions.csv"

  docker exec "$engine_stage_container_id" mkdir -p /var/tmp >/dev/null
  docker cp "$ROOT_DIR/scripts/stage_local_csv_to_s3_parquet.py" "${engine_stage_container_id}:${helper_container_path}" >/dev/null
  docker cp "$source_csv_path" "${engine_stage_container_id}:${container_csv_path}" >/dev/null

  stage_output_json="$(docker exec "$engine_stage_container_id" python "$helper_container_path" \
    --workspace-id "$WORKSPACE_ID" \
    --case-id "example_gx_suite" \
    --role "source" \
    --version-id "$DATA_OBJECT_VERSION_ID" \
    --input-csv "$container_csv_path" \
    --transform "teller_machine_gx_suite" \
    --output-uri "s3://dq-test-data/data_object_version_id=${DATA_OBJECT_VERSION_ID}/attr_hash=all/sample_count=1000/format=parquet")"

  output_uri="$(printf '%s' "$stage_output_json" | jq -r '.output_uri // empty')"
  output_format="$(printf '%s' "$stage_output_json" | jq -r '.output_format // empty')"
  if [[ -z "$output_uri" || -z "$output_format" ]]; then
    error "$MY_NAME" "Example GX source staging did not return output_uri/output_format"
    printf '%s\n' "$stage_output_json" >&2
    exit 1
  fi

  escaped_version_id="${DATA_OBJECT_VERSION_ID//\'/\'\'}"
  docker compose exec -T db psql -U postgres -d dq -v ON_ERROR_STOP=1 \
    -c "UPDATE data_object_versions SET storage_uri = 's3a://${output_uri#s3://}', storage_format = '${output_format}' WHERE id = '${escaped_version_id}';" >/dev/null

  info "$MY_NAME" "Bootstrapped example GX source ${DATA_OBJECT_VERSION_ID} to ${output_uri} (${output_format})"
}


extract_example_gx_suite_context() {
  "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" - "$EXAMPLE_GX_SUITE_YML" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

suite_path = Path(sys.argv[1])
payload = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
if not isinstance(payload, dict):
    raise SystemExit(f"{suite_path} did not contain a YAML object")

execution_contract = payload.get("executionContract")
if not isinstance(execution_contract, dict):
    raise SystemExit(f"{suite_path} did not include executionContract")

traceability = execution_contract.get("traceability")
if not isinstance(traceability, dict):
    raise SystemExit(f"{suite_path} did not include executionContract.traceability")

suite_id = str(traceability.get("gxSuiteId") or traceability.get("gx_suite_id") or "").strip()
suite_version_raw = traceability.get("gxSuiteVersion") or traceability.get("gx_suite_version")
if not suite_id:
    raise SystemExit(f"{suite_path} did not include executionContract.traceability.gxSuiteId")

workspace_id = str(payload.get("gxSuite", {}).get("meta", {}).get("workspace_id") or "").strip()
assignment_scope = payload.get("assignmentScope")
resolved_execution_scope = payload.get("resolvedExecutionScope")
data_object_ids = resolved_execution_scope.get("dataObjectVersionIds") if isinstance(resolved_execution_scope, dict) else None
if not isinstance(data_object_ids, list) or not data_object_ids:
  raise SystemExit(f"{suite_path} did not include resolvedExecutionScope.dataObjectVersionIds")

data_object_id = str(assignment_scope.get("dataObjectId") or "").strip() if isinstance(assignment_scope, dict) else ""
dataset_id = str(assignment_scope.get("datasetId") or "").strip() if isinstance(assignment_scope, dict) else ""
data_product_id = str(assignment_scope.get("dataProductId") or "").strip() if isinstance(assignment_scope, dict) else ""
data_object_version_id = str(data_object_ids[0] or "").strip()
if not workspace_id:
  raise SystemExit(f"{suite_path} did not include gxSuite.meta.workspace_id")
if not data_object_id or not dataset_id or not data_product_id or not data_object_version_id:
  raise SystemExit(f"{suite_path} did not include the required assignment scope identifiers")

print(json.dumps({
  "suite_id": suite_id,
  "suite_version": int(suite_version_raw),
  "workspace_id": workspace_id,
  "data_object_id": data_object_id,
  "data_object_version_id": data_object_version_id,
  "dataset_id": dataset_id,
  "data_product_id": data_product_id,
}, sort_keys=True))
PY
}

poll_gx_run_until_succeeded() {
  local run_id="$1"
  local token="$2"
  local deadline=$(( $(date +%s) + POLL_TIMEOUT_SECONDS ))
  local run_url="${KONG_PUBLIC_URL%/}/rulebuilder/v1/gx/runs/${run_id}"

  while true; do
    local response_file http_code curl_rc run_payload status
    response_file="$(mktemp)"
    set +e
    http_code="$(curl -sS "${CURL_TLS_ARGS[@]}" -o "$response_file" -w '%{http_code}' \
      -H "Authorization: Bearer ${token}" \
      -H "X-Kong-Request-Id: ${REQUEST_ID}" \
      -H "X-Correlation-ID: ${CORRELATION_ID}" \
      "$run_url")"
    curl_rc=$?
    set -e

    if [[ "$curl_rc" -ne 0 ]]; then
      error "$MY_NAME" "GX run lookup failed for ${run_id}"
      cat "$response_file" >&2 || true
      rm -f "$response_file"
      exit "$curl_rc"
    fi

    if [[ "$http_code" -ne 200 ]]; then
      error "$MY_NAME" "GX run lookup returned HTTP ${http_code} for ${run_id}"
      cat "$response_file" >&2 || true
      rm -f "$response_file"
      exit 1
    fi

    run_payload="$(cat "$response_file")"
    rm -f "$response_file"
    status="$(printf '%s' "$run_payload" | jq -r '.status // empty')"

    if [[ "$status" == "succeeded" ]]; then
      printf '%s' "$run_payload"
      return 0
    fi

    if [[ "$status" == "failed" || "$status" == "cancelled" ]]; then
      error "$MY_NAME" "GX run ${run_id} ended with status=${status}"
      printf '%s\n' "$run_payload" >&2
      exit 1
    fi

    if [[ $(date +%s) -ge "$deadline" ]]; then
      error "$MY_NAME" "Timed out waiting for GX run ${run_id} to succeed"
      printf '%s\n' "$run_payload" >&2
      exit 1
    fi

    sleep "$POLL_INTERVAL_SECONDS"
  done
}

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      print_usage
      exit 0
      ;;
  esac
done

validate_selected_root_env_file "$ROOT_DIR" full

if ! source_selected_root_env_file; then
  exit 1
fi

dq_source_seeded_user_credentials --env-file "$ROOT_ENV_FILE" --quiet

if [[ ! -f "$EXAMPLE_GX_SUITE_YML" ]]; then
  error "$MY_NAME" "Missing required GX suite fixture: $EXAMPLE_GX_SUITE_YML"
  exit 2
fi

require_cmd curl
require_cmd jq
require_cmd mktemp
require_cmd docker

if [[ ! -x "$PYTHON_BIN" ]]; then
  error "$MY_NAME" "Missing required Python interpreter: $PYTHON_BIN"
  exit 2
fi

if [[ ! -x "$PYTHON_RUNNER" ]]; then
  error "$MY_NAME" "Missing required Python launcher: $PYTHON_RUNNER"
  exit 2
fi

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
CURL_TLS_ARGS=()
if [[ -f "$KONG_CA_CERT" ]]; then
  CURL_TLS_ARGS=(--cacert "$KONG_CA_CERT")
fi

if [[ -z "${DQ_API_LOCAL_URL:-}" ]]; then
  error "$MY_NAME" "DQ_API_LOCAL_URL is required"
  exit 2
fi

REQUEST_ID="validate-dq-run-plan-invoke-example-gx-suite-$(date +%s)-$$"
CORRELATION_ID="validate-dq-run-plan-invoke-example-gx-suite-$(date +%s)-$$"
TOKEN_URL="${SSO_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"
DQ_SESSION_COOKIE_JAR="$(mktemp)"
trap 'rm -f "$DQ_SESSION_COOKIE_JAR"' EXIT

login_dq_api_session "$DQ_SESSION_COOKIE_JAR"
DQ_API_POLL_TOKEN="$(dq_keycloak_seeded_user_access_token "$TOKEN_URL" "$VITE_KEYCLOAK_CLIENT_ID" "$KEYCLOAK_JACCLOUD_USERNAME" "$KEYCLOAK_JACCLOUD_PASSWORD")"

GX_CONTEXT_JSON="$(extract_example_gx_suite_context)"
SUITE_ID="$(printf '%s' "$GX_CONTEXT_JSON" | jq -r '.suite_id')"
SUITE_VERSION="$(printf '%s' "$GX_CONTEXT_JSON" | jq -r '.suite_version')"
WORKSPACE_ID="$(printf '%s' "$GX_CONTEXT_JSON" | jq -r '.workspace_id')"
DATA_OBJECT_ID="$(printf '%s' "$GX_CONTEXT_JSON" | jq -r '.data_object_id')"
DATA_OBJECT_VERSION_ID="$(printf '%s' "$GX_CONTEXT_JSON" | jq -r '.data_object_version_id')"
DATASET_ID="$(printf '%s' "$GX_CONTEXT_JSON" | jq -r '.dataset_id')"
DATA_PRODUCT_ID="$(printf '%s' "$GX_CONTEXT_JSON" | jq -r '.data_product_id')"

bootstrap_example_gx_suite_source

info "$MY_NAME" "Invoking run plan from GX suite fixture ${EXAMPLE_GX_SUITE_YML}"
CLI_BASE_ARGS=(
  --base-url "$DQ_API_LOCAL_URL"
  --issuer-url "$SSO_PUBLIC_ISSUER_URL"
  --client-id "$VITE_KEYCLOAK_CLIENT_ID"
  --token "$DQ_API_LOGIN_TOKEN"
)
if [[ -f "$KONG_CA_CERT" ]]; then
  CLI_BASE_ARGS+=(--ca-cert "$KONG_CA_CERT")
fi

CLI_OUTPUT="$(run_cli \
  "${CLI_BASE_ARGS[@]}" \
  --json \
  invoke \
  --run-plan-file "$EXAMPLE_GX_SUITE_YML")"

RETURNED_RUN_PLAN_ID="$(printf '%s' "$CLI_OUTPUT" | jq -r '.run_plan_id // empty')"
QUEUE_MESSAGE_ID="$(printf '%s' "$CLI_OUTPUT" | jq -r '.queue_message_id // empty')"
RUN_ID="$(printf '%s' "$CLI_OUTPUT" | jq -r '.run_id // empty')"

if [[ -z "$RETURNED_RUN_PLAN_ID" ]]; then
  error "$MY_NAME" "CLI output did not include run_plan_id"
  printf '%s\n' "$CLI_OUTPUT" >&2
  exit 1
fi

if [[ -z "$QUEUE_MESSAGE_ID" || -z "$RUN_ID" ]]; then
  error "$MY_NAME" "CLI output is missing queue_message_id or run_id"
  printf '%s\n' "$CLI_OUTPUT" >&2
  exit 1
fi

info "$MY_NAME" "Accepted replay for run plan ${RETURNED_RUN_PLAN_ID}; waiting for GX run ${RUN_ID}"
RUN_PAYLOAD="$(poll_gx_run_until_succeeded "$RUN_ID" "$DQ_API_POLL_TOKEN")"
FINAL_STATUS="$(printf '%s' "$RUN_PAYLOAD" | jq -r '.status // empty')"
if [[ "$FINAL_STATUS" != "succeeded" ]]; then
  error "$MY_NAME" "GX run ${RUN_ID} did not finish successfully"
  printf '%s\n' "$RUN_PAYLOAD" >&2
  exit 1
fi

info "$MY_NAME" "Replayed DQ run plan ${RETURNED_RUN_PLAN_ID} from GX suite file and verified GX run ${RUN_ID} succeeded"
printf '%s\n' "$CLI_OUTPUT"

success "$MY_NAME" "DQ run-plan GX suite replay validation passed"