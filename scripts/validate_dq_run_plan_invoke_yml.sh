#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate that dq-run-plan can replay a validation plan from a YAML file and produce a real GX run.
#
# What it does:
# - Loads the selected repo env file and seeded user credentials.
# - Exports a known run plan to disk, converts the exported JSON validation plan to YAML, and replays it via dq-run-plan invoke --run-plan-file.
# - Confirms the CLI returns run_id and queue_message_id, then polls GET /rulebuilder/v1/gx/runs/{run_id} until the run succeeds.
#
# validate: groups=api,cli,regression
# Version: 1.0.1
# Last modified: 2026-07-01

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
PYTHON_RUNNER="${ROOT_DIR}/scripts/python_arm64.sh"
CLI_MODULE_DIR="${ROOT_DIR}/dq-cli"
MY_NAME="validate_dq_run_plan_invoke_yml.sh"
TMP_DIR=""
RUN_PLAN_ID="${DQ_VALIDATION_RUN_PLAN_ID:-}"
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
Usage: scripts/validate_dq_run_plan_invoke_yml.sh [--run-plan-id ID]

Options:
  --env dev|test|prod
                     Select the root env file using the common repo env selector
  --run-plan-id ID   Run-plan id to export, convert to YAML, and replay
  DQ_VALIDATION_RUN_PLAN_ID
                     Default run-plan id used when --run-plan-id is omitted
  -h, --help         Show this help
EOF
}

cleanup() {
  if [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

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

convert_json_to_yaml() {
  local source_json="$1"
  local target_yaml="$2"
  "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" - "$source_json" "$target_yaml" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

source_json = Path(sys.argv[1])
target_yaml = Path(sys.argv[2])
payload = json.loads(source_json.read_text(encoding="utf-8"))
target_yaml.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")
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

require_cmd curl
require_cmd jq
require_cmd mktemp

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

CLI_BASE_ARGS=(
  --base-url "${DQ_API_LOCAL_URL:-}"
  --issuer-url "$SSO_PUBLIC_ISSUER_URL"
  --client-id "$VITE_KEYCLOAK_CLIENT_ID"
  --username "$KEYCLOAK_JACCLOUD_USERNAME"
  --password "$KEYCLOAK_JACCLOUD_PASSWORD"
)
if [[ -f "$KONG_CA_CERT" ]]; then
  CLI_BASE_ARGS+=(--ca-cert "$KONG_CA_CERT")
fi

if [[ -z "${DQ_API_LOCAL_URL:-}" ]]; then
  error "$MY_NAME" "DQ_API_LOCAL_URL is required"
  exit 2
fi

if [[ -z "$RUN_PLAN_ID" ]]; then
  error "$MY_NAME" "--run-plan-id is required when DQ_VALIDATION_RUN_PLAN_ID is not set"
  exit 2
fi

mkdir -p "$ROOT_DIR/tmp"
TMP_DIR="$(mktemp -d "$ROOT_DIR/tmp/validate_dq_run_plan_invoke_yml.XXXXXX")"
EXPORT_DIR="$TMP_DIR/export"
EXPORT_JSON="$EXPORT_DIR/validation-run-plan.json"
EXPORT_YML="$EXPORT_DIR/validation-run-plan.yml"
mkdir -p "$EXPORT_DIR"

REQUEST_ID="validate-dq-run-plan-invoke-yml-$(date +%s)-$$"
CORRELATION_ID="validate-dq-run-plan-invoke-yml-$(date +%s)-$$"
TOKEN_URL="${SSO_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"
TOKEN="$(dq_keycloak_password_grant_access_token "$TOKEN_URL" "$VITE_KEYCLOAK_CLIENT_ID" "$KEYCLOAK_JACCLOUD_USERNAME" "$KEYCLOAK_JACCLOUD_PASSWORD" "${CURL_TLS_ARGS[@]}")"

info "$MY_NAME" "Exporting run plan ${RUN_PLAN_ID} to ${EXPORT_DIR}"
run_cli \
  "${CLI_BASE_ARGS[@]}" \
  export \
  --run-plan-id "$RUN_PLAN_ID" \
  --output-dir "$EXPORT_DIR" >/dev/null

if [[ ! -f "$EXPORT_JSON" ]]; then
  error "$MY_NAME" "Export did not produce ${EXPORT_JSON}"
  exit 1
fi

convert_json_to_yaml "$EXPORT_JSON" "$EXPORT_YML"

if [[ ! -s "$EXPORT_YML" ]]; then
  error "$MY_NAME" "YAML conversion did not produce ${EXPORT_YML}"
  exit 1
fi

info "$MY_NAME" "Replaying run plan from YAML file ${EXPORT_YML}"
CLI_OUTPUT="$(run_cli \
  "${CLI_BASE_ARGS[@]}" \
  --json \
  invoke \
  --run-plan-file "$EXPORT_YML")"

RETURNED_RUN_PLAN_ID="$(printf '%s' "$CLI_OUTPUT" | jq -r '.run_plan_id // empty')"
QUEUE_MESSAGE_ID="$(printf '%s' "$CLI_OUTPUT" | jq -r '.queue_message_id // empty')"
RUN_ID="$(printf '%s' "$CLI_OUTPUT" | jq -r '.run_id // empty')"

if [[ -z "$RETURNED_RUN_PLAN_ID" ]]; then
  error "$MY_NAME" "CLI output did not include run_plan_id"
  printf '%s\n' "$CLI_OUTPUT" >&2
  exit 1
fi

if [[ "$RETURNED_RUN_PLAN_ID" != "$RUN_PLAN_ID" ]]; then
  error "$MY_NAME" "CLI output returned run_plan_id=${RETURNED_RUN_PLAN_ID}, expected ${RUN_PLAN_ID}"
  printf '%s\n' "$CLI_OUTPUT" >&2
  exit 1
fi

if [[ -z "$QUEUE_MESSAGE_ID" || -z "$RUN_ID" ]]; then
  error "$MY_NAME" "CLI output is missing queue_message_id or run_id"
  printf '%s\n' "$CLI_OUTPUT" >&2
  exit 1
fi

info "$MY_NAME" "Accepted replay for run plan ${RUN_PLAN_ID}; waiting for GX run ${RUN_ID}"
RUN_PAYLOAD="$(poll_gx_run_until_succeeded "$RUN_ID" "$TOKEN")"
FINAL_STATUS="$(printf '%s' "$RUN_PAYLOAD" | jq -r '.status // empty')"
if [[ "$FINAL_STATUS" != "succeeded" ]]; then
  error "$MY_NAME" "GX run ${RUN_ID} did not finish successfully"
  printf '%s\n' "$RUN_PAYLOAD" >&2
  exit 1
fi

info "$MY_NAME" "Replayed DQ run plan ${RUN_PLAN_ID} from YAML file and verified GX run ${RUN_ID} succeeded"
printf '%s\n' "$CLI_OUTPUT"

success "$MY_NAME" "DQ run-plan YAML replay validation passed"
