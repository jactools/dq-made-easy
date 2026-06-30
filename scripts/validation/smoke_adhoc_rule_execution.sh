#!/usr/bin/env bash
set -euo pipefail


# Purpose: Smoke-test ad-hoc rule execution with reusable generated test data.
#
# What it does:
# - Gets a JWT from Keycloak via client_credentials for the seeded engine client.
# - Discovers a seeded data_object_version_id via Kong.
# - Probes for a DOV that has GX suites (without enqueuing runs).
# - Creates/reuses a test-data materialization and waits for completion.
# - Enqueues an ad-hoc GX run using source overrides and waits for completion.
# - Asserts the GX worker reported `storage_uri` == the override output_uri.
#
# Version: 1.4
# Last modified: 2026-07-01

__dq_scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${__dq_scripts_dir}/../.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
set_log_level INFO
my_name="smoke_adhoc_rule_execution.sh"
TMP_DIR="$ROOT_DIR/tmp/smoke_adhoc_rule_execution"
mkdir -p "$TMP_DIR"

PROBE_JSON_PATH="$TMP_DIR/probe_$$.json"
SUITE_SEED_JSON_PATH="$TMP_DIR/suite_seed_$$.json"
SUITE_GET_JSON_PATH="$TMP_DIR/suite_get_$$.json"
RUN_JSON_PATH="$TMP_DIR/run_$$.json"
MATERIALIZATION_CREATE_JSON_PATH="$TMP_DIR/materialization_create_$$.json"

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

validate_selected_root_env_file "$ROOT_DIR" full

if ! source_selected_root_env_file; then
  exit 1
fi

if [[ $# -gt 0 ]]; then
  error "$my_name" "Unknown arg: $1"
  exit 1
fi

require_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: $name"
    exit 2
  fi
}

require_cmd curl
require_cmd jq
require_cmd python3

if ! command -v grep >/dev/null 2>&1; then
  error "$my_name" "Missing required command: grep"
  exit 2
fi

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
dq_source_seeded_user_credentials --quiet

engine_oidc_env=""
case "$(printf '%s' "${ENVIRONMENT:-}" | tr '[:upper:]' '[:lower:]')" in
  dev|development)
    engine_oidc_env="$ROOT_DIR/tmp/dq_engine_oidc.dev.env"
    ;;
  test|testing)
    engine_oidc_env="$ROOT_DIR/tmp/dq_engine_oidc.test.env"
    ;;
  prod|production)
    engine_oidc_env="$ROOT_DIR/tmp/dq_engine_oidc.prod.env"
    ;;
esac

if [ -z "$engine_oidc_env" ]; then
  error "$my_name" "Unable to resolve a stage-specific engine OIDC env file from ENVIRONMENT=${ENVIRONMENT:-<unset>}"
  exit 2
fi

if [ -f "$engine_oidc_env" ]; then
  # shellcheck disable=SC1091
  set +u
  source "$engine_oidc_env"
  set -u
fi

KONG_PUBLIC_URL="${KONG_PUBLIC_URL:?KONG_PUBLIC_URL must be set to the public Kong URL used by the UI}"
KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [ -f "$KONG_CA_CERT" ] && [ -z "${CURL_CA_BUNDLE:-}" ]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

KEYCLOAK_REALM="${KEYCLOAK_REALM:?KEYCLOAK_REALM must be set}"
SSO_ENABLED="${SSO_ENABLED:?SSO_ENABLED must be set}"
SSO_ISSUER="${SSO_PUBLIC_ISSUER_URL:?SSO_PUBLIC_ISSUER_URL must be set}"
DQ_SMOKE_GRANT_TYPE="client_credentials"
DQ_SMOKE_CLIENT_ID="${DQ_ENGINE_OIDC_CLIENT_ID:?DQ_ENGINE_OIDC_CLIENT_ID must be set}"
DQ_SMOKE_CLIENT_SECRET="${DQ_ENGINE_OIDC_CLIENT_SECRET:?DQ_ENGINE_OIDC_CLIENT_SECRET must be set}"
DQ_SMOKE_SAMPLE_COUNT="${DQ_SMOKE_SAMPLE_COUNT:-1000}"
DQ_SMOKE_OUTPUT_FORMAT="${DQ_SMOKE_OUTPUT_FORMAT:-parquet}"
DQ_SMOKE_REFRESH="${DQ_SMOKE_REFRESH:-false}"

DQ_SMOKE_MATERIALIZATION_TIMEOUT_SECONDS="${DQ_SMOKE_MATERIALIZATION_TIMEOUT_SECONDS:-180}"
DQ_SMOKE_GX_TIMEOUT_SECONDS="${DQ_SMOKE_GX_TIMEOUT_SECONDS:-300}"
DQ_SMOKE_GX_ACTIVE_RUN_STALE_SECONDS="${DQ_SMOKE_GX_ACTIVE_RUN_STALE_SECONDS:-120}"

smoke_started_at_epoch="$(date +%s)"

iso8601_to_epoch() {
  local value="$1"
  python3 - "$value" <<'PY'
from datetime import datetime
import sys

value = sys.argv[1].strip()
if value.endswith('Z'):
    value = value[:-1] + '+00:00'
print(int(datetime.fromisoformat(value).timestamp()))
PY
}

case "${DQ_SMOKE_OUTPUT_FORMAT}" in
  parquet|delta) ;;
  *)
    error "$my_name" "Unsupported DQ_SMOKE_OUTPUT_FORMAT: ${DQ_SMOKE_OUTPUT_FORMAT} (expected parquet|delta)"
    exit 2
    ;;
esac

case "${DQ_SMOKE_REFRESH}" in
  true|false) ;;
  *)
    error "$my_name" "DQ_SMOKE_REFRESH must be 'true' or 'false'"
    exit 2
    ;;
esac

if [ "$SSO_ENABLED" = "true" ] && [ -n "$SSO_ISSUER" ]; then
  TOKEN_ENDPOINT="${SSO_ISSUER%/}/protocol/openid-connect/token"
else
  TOKEN_ENDPOINT="${KEYCLOAK_PUBLIC_URL%/}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token"
fi

mint_token() {
  info "$my_name" "Getting JWT from Keycloak: ${TOKEN_ENDPOINT} (grant_type=${DQ_SMOKE_GRANT_TYPE}, client_id=${DQ_SMOKE_CLIENT_ID})"
  info "$my_name" "Using shared client_credentials auth helper"
  TOKEN="$(dq_keycloak_client_credentials_access_token "$TOKEN_ENDPOINT" "$DQ_SMOKE_CLIENT_ID" "$DQ_SMOKE_CLIENT_SECRET")"
  if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    error "$my_name" "Failed to obtain access_token from Keycloak"
    exit 3
  fi

  AUTH_HEADER=( -H "Authorization: Bearer $TOKEN" )
}

mint_token

probe_dov_for_gx_suites() {
  local dov_id="$1"
  local probe_body
  probe_body="$(jq -nc --arg dov "$dov_id" '{data_object_version_id:$dov, target_data_object_version_ids:[$dov], source_override_uri:"probe://noop"}')"

  # Intentionally omit source_override_format so the API will:
  # - return 404 if no suites exist for the selector; or
  # - return 400 missing_source_override_format if suites exist.
  local http_code
  http_code="$(
    curl -sS -o "$PROBE_JSON_PATH" -w "%{http_code}" \
      -X POST "${KONG_PUBLIC_URL%/}/rulebuilder/v1/gx/runs/adhoc" \
      "${AUTH_HEADER[@]}" \
      -H "Content-Type: application/json" \
      -d "$probe_body" || true
  )"

  if [ "$http_code" = "400" ]; then
    if jq -e '.detail.error == "missing_source_override_format"' "$PROBE_JSON_PATH" >/dev/null 2>&1; then
      return 0
    fi
  fi

  return 1
}

info "$my_name" "Discovering a data_object_version_id with GX suites via Kong"
DOV_PAGE_JSON="$(curl -fsS "${KONG_PUBLIC_URL%/}/data-catalog/v1/data-object-versions?page=1&limit=25" "${AUTH_HEADER[@]}")"

DATA_OBJECT_VERSION_ID=""
for candidate in $(printf '%s' "$DOV_PAGE_JSON" | jq -r '.data[]?.id // empty'); do
  if [ -z "$candidate" ]; then
    continue
  fi
  if probe_dov_for_gx_suites "$candidate"; then
    DATA_OBJECT_VERSION_ID="$candidate"
    break
  fi
done

if [ -z "$DATA_OBJECT_VERSION_ID" ]; then
  warning "$my_name" "No GX suites found for any of the first 25 data object versions. Creating a minimal GX suite for smoke testing."

  FIRST_DOV_ID=""
  FIRST_DO_ID=""
  FIRST_COLUMN_NAME=""

  for candidate in $(printf '%s' "$DOV_PAGE_JSON" | jq -r '.data[]?.id // empty'); do
    if [ -z "$candidate" ]; then
      continue
    fi

    candidate_do_id="$(printf '%s' "$DOV_PAGE_JSON" | jq -r --arg id "$candidate" '.data[] | select(.id == $id) | .data_object_id' | head -1)"
    if [ -z "$candidate_do_id" ]; then
      continue
    fi

    ATTR_JSON="$(curl -fsS "${KONG_PUBLIC_URL%/}/data-catalog/v1/attributes-catalog?versionId=${candidate}&page=1&limit=1" "${AUTH_HEADER[@]}")"
    candidate_column_name="$(printf '%s' "$ATTR_JSON" | jq -r '.data[0].name // empty')"
    if [ -n "$candidate_column_name" ]; then
      FIRST_DOV_ID="$candidate"
      FIRST_DO_ID="$candidate_do_id"
      FIRST_COLUMN_NAME="$candidate_column_name"
      break
    fi
  done

  if [ -z "$FIRST_DOV_ID" ] || [ -z "$FIRST_DO_ID" ] || [ -z "$FIRST_COLUMN_NAME" ]; then
    error "$my_name" "Unable to seed GX suite: no attributes found for any data_object_version_id in the first 25 candidates"
    exit 5
  fi

  RULES_PAGE_JSON="$(curl -fsS "${KONG_PUBLIC_URL%/}/rulebuilder/v1/rules?page=1&limit=1" "${AUTH_HEADER[@]}")"
  FIRST_RULE_ID="$(printf '%s' "$RULES_PAGE_JSON" | jq -r '.data[0].id // empty')"
  if [ -z "$FIRST_RULE_ID" ]; then
    error "$my_name" "rulebuilder returned no rules; cannot seed a GX suite"
    exit 5
  fi

  SUITE_ID="smoke_suite_${FIRST_DOV_ID}"
  GENERATED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

  GX_SUITE_ENVELOPE="$(
    jq -nc \
      --arg suite_id "$SUITE_ID" \
      --argjson suite_version 1 \
      --arg data_object_id "$FIRST_DO_ID" \
      --arg dov_id "$FIRST_DOV_ID" \
      --arg rule_id "$FIRST_RULE_ID" \
      --arg generated_at "$GENERATED_AT" \
      --arg column_name "$FIRST_COLUMN_NAME" \
      '(
        {
          suite_id: $suite_id,
          suite_version: $suite_version,
          artifact_version: "v1",
          assignment_scope: { data_object_id: $data_object_id },
          resolved_execution_scope: { data_object_version_ids: [ $dov_id ] },
          gx_suite: {
            expectation_suite_name: ("smoke_" + $dov_id),
            expectations: [
              {
                expectation_type: "expect_column_values_to_not_be_null",
                kwargs: { column: $column_name }
              }
            ],
            meta: {}
          },
          compiled_from: { rule_ids: [ $rule_id ], compiler_version: "smoke", generated_at: $generated_at },
          execution_hints: { recommended_engine: "pyspark", primary_key_fields: [] },
          execution_contract: {
            engine_type: "gx",
            engine_target: "pyspark",
            execution_shape: "single_object",
            traceability: {
              rule_id: $rule_id,
              rule_version_id: ("rulever-" + $rule_id),
              gx_suite_id: $suite_id,
              gx_suite_version: $suite_version,
              data_object_version_id: $dov_id
            }
          }
        }
      )'
  )"

  SUITE_SEED_HTTP_CODE="$({
    curl -sS -o "$SUITE_SEED_JSON_PATH" -w "%{http_code}" -X POST \
      "${KONG_PUBLIC_URL%/}/rulebuilder/v1/gx/suites?status=active&sourcePipeline=smoke" \
      "${AUTH_HEADER[@]}" \
      -H "Content-Type: application/json" \
      -d "$GX_SUITE_ENVELOPE"
  } || true)"

  if [ "$SUITE_SEED_HTTP_CODE" = "409" ]; then
    warning "$my_name" "Smoke GX suite ${SUITE_ID} already exists; reusing existing suite"
    EXISTING_SUITE_HTTP_CODE="$({
      curl -sS -o "$SUITE_GET_JSON_PATH" -w "%{http_code}" \
        "${KONG_PUBLIC_URL%/}/rulebuilder/v1/gx/suites/${SUITE_ID}?status=active" \
        "${AUTH_HEADER[@]}"
    } || true)"
    if [ "$EXISTING_SUITE_HTTP_CODE" != "200" ]; then
      error "$my_name" "Failed to reuse existing GX suite ${SUITE_ID} after 409 conflict"
      cat "$SUITE_SEED_JSON_PATH" >&2 || true
      exit 5
    fi
  elif [ "$SUITE_SEED_HTTP_CODE" != "200" ] && [ "$SUITE_SEED_HTTP_CODE" != "201" ]; then
    error "$my_name" "Failed to seed a minimal GX suite via /rulebuilder/v1/gx/suites"
    cat "$SUITE_SEED_JSON_PATH" >&2 || true
    exit 5
  fi

  DATA_OBJECT_VERSION_ID="$FIRST_DOV_ID"
fi

info "$my_name" "Using data_object_version_id=${DATA_OBJECT_VERSION_ID}"

info "$my_name" "Creating/reusing test-data materialization (refresh=${DQ_SMOKE_REFRESH})"
materialization_create_request_body() {
  local refresh_value="$1"

  jq -nc \
    --arg data_object_version_id "$DATA_OBJECT_VERSION_ID" \
    --arg output_format "$DQ_SMOKE_OUTPUT_FORMAT" \
    --argjson sample_count "$DQ_SMOKE_SAMPLE_COUNT" \
    --argjson refresh "$refresh_value" \
    '{data_object_version_id:$data_object_version_id, sample_count:$sample_count, output_format:$output_format, refresh:$refresh}'
}

materialization_create_refresh="$DQ_SMOKE_REFRESH"
materialization_create_attempt=1
materialization_create_max_attempts=5
while true; do
  MATERIALIZATION_CREATE_BODY="$(materialization_create_request_body "$materialization_create_refresh")"
  MATERIALIZATION_HTTP_CODE="$(
    curl -sS -o "$MATERIALIZATION_CREATE_JSON_PATH" -w "%{http_code}" -X POST "${KONG_PUBLIC_URL%/}/rulebuilder/v1/test-data/materializations" \
      "${AUTH_HEADER[@]}" \
      -H "Content-Type: application/json" \
      -d "$MATERIALIZATION_CREATE_BODY" || true
  )"

  MATERIALIZATION_RESPONSE_ERROR="$(jq -r '.detail.error // empty' "$MATERIALIZATION_CREATE_JSON_PATH" 2>/dev/null || true)"

  if [ "$MATERIALIZATION_HTTP_CODE" = "503" ] && [ "$MATERIALIZATION_RESPONSE_ERROR" = "test_data_output_check_failed" ] && [ "$materialization_create_refresh" = "false" ]; then
    warning "$my_name" "Materialization reuse check is unavailable; retrying with refresh=true"
    materialization_create_refresh="true"
    continue
  fi

  if [ "$MATERIALIZATION_HTTP_CODE" = "503" ] && [ "$materialization_create_attempt" -lt "$materialization_create_max_attempts" ]; then
    warning "$my_name" "Materialization create returned 503; retrying (${materialization_create_attempt}/${materialization_create_max_attempts})"
    materialization_create_attempt=$((materialization_create_attempt + 1))
    sleep 2
    continue
  fi

  break
done

if [ "$MATERIALIZATION_HTTP_CODE" != "200" ] && [ "$MATERIALIZATION_HTTP_CODE" != "201" ] && [ "$MATERIALIZATION_HTTP_CODE" != "202" ]; then
  error "$my_name" "Failed to create/reuse materialization (HTTP ${MATERIALIZATION_HTTP_CODE})"
  cat "$MATERIALIZATION_CREATE_JSON_PATH" >&2 || true
  exit 6
fi

MATERIALIZATION_JSON="$(cat "$MATERIALIZATION_CREATE_JSON_PATH")"
MATERIALIZATION_REQUEST_ID="$(printf '%s' "$MATERIALIZATION_JSON" | jq -r '.request_id // empty')"
if [ -z "$MATERIALIZATION_REQUEST_ID" ]; then
  error "$my_name" "Materialization response missing request_id"
  printf '%s\n' "$MATERIALIZATION_JSON" >&2
  exit 6
fi

materialization_deadline=$(( $(date +%s) + DQ_SMOKE_MATERIALIZATION_TIMEOUT_SECONDS ))
materialization_poll_i=0
while true; do
  materialization_poll_i=$((materialization_poll_i + 1))
  MATERIALIZATION_JSON="$(
    curl -fsS "${KONG_PUBLIC_URL%/}/rulebuilder/v1/test-data/materializations/${MATERIALIZATION_REQUEST_ID}" "${AUTH_HEADER[@]}"
  )"
  MATERIALIZATION_STATUS="$(printf '%s' "$MATERIALIZATION_JSON" | jq -r '.status // empty')"

  if (( materialization_poll_i % 5 == 0 )); then
    info "$my_name" "Waiting for materialization: status=${MATERIALIZATION_STATUS}"
  fi

  if [ "$MATERIALIZATION_STATUS" = "completed" ]; then
    break
  fi
  if [ "$MATERIALIZATION_STATUS" = "failed" ]; then
    error "$my_name" "Materialization failed: $(printf '%s' "$MATERIALIZATION_JSON" | jq -r '.error_message // ""')"
    exit 7
  fi

  now=$(date +%s)
  if [ "$now" -ge "$materialization_deadline" ]; then
    error "$my_name" "Timed out waiting for test-data materialization (status=${MATERIALIZATION_STATUS})"
    error "$my_name" "If it stays pending, ensure the test-data worker is running and Redis is reachable by the API"
    exit 8
  fi

  sleep 1
done

OUTPUT_URI="$(printf '%s' "$MATERIALIZATION_JSON" | jq -r '(.result.output_uri // .output_uri // empty)')"
OUTPUT_FORMAT="$(printf '%s' "$MATERIALIZATION_JSON" | jq -r '(.result.output_format // .output_format // empty)')"
if [ -z "$OUTPUT_URI" ] || [ -z "$OUTPUT_FORMAT" ]; then
  error "$my_name" "Materialization completed but output_uri/output_format missing"
  printf '%s\n' "$MATERIALIZATION_JSON" >&2
  exit 9
fi

info "$my_name" "Materialization completed: ${OUTPUT_URI} (${OUTPUT_FORMAT})"

info "$my_name" "Enqueuing ad-hoc GX run with source override"
ADHOC_BODY="$(
  jq -nc \
    --arg data_object_version_id "$DATA_OBJECT_VERSION_ID" \
    --arg source_override_uri "$OUTPUT_URI" \
    --arg source_override_format "$OUTPUT_FORMAT" \
    '{
      data_object_version_id:$data_object_version_id,
      target_data_object_version_ids:[$data_object_version_id],
      source_override_uri:$source_override_uri,
      source_override_format:$source_override_format
    }'
)"
RUNS_RESPONSE="$({
  curl -sS -w $'\n%{http_code}' -X POST "${KONG_PUBLIC_URL%/}/rulebuilder/v1/gx/runs/adhoc" \
    "${AUTH_HEADER[@]}" \
    -H "Content-Type: application/json" \
    -d "$ADHOC_BODY"
} || true)"
RUNS_HTTP_CODE="$(printf '%s' "$RUNS_RESPONSE" | tail -n1)"
RUNS_JSON="$(printf '%s' "$RUNS_RESPONSE" | sed '$d')"
if [ "$RUNS_HTTP_CODE" = "409" ]; then
  ACTIVE_ERROR="$(printf '%s' "$RUNS_JSON" | jq -r '.detail.error // empty' 2>/dev/null || true)"
  if [ "$ACTIVE_ERROR" = "gx_execution_already_active" ]; then
    RUN_ID="$(printf '%s' "$RUNS_JSON" | jq -r '.detail.active_run_id // empty' 2>/dev/null || true)"
    if [ -z "$RUN_ID" ]; then
      error "$my_name" "Ad-hoc enqueue returned active-run conflict without detail.active_run_id"
      printf '%s\n' "$RUNS_JSON" >&2
      exit 10
    fi
    ACTIVE_RUN_JSON="$({
      curl -sS -f "${KONG_PUBLIC_URL%/}/rulebuilder/v1/gx/runs/${RUN_ID}" \
        "${AUTH_HEADER[@]}"
    } || true)"
    ACTIVE_RUN_STATUS="$(printf '%s' "$ACTIVE_RUN_JSON" | jq -r '(.status // empty) | ascii_downcase' 2>/dev/null || true)"
    ACTIVE_RUN_STARTED_AT="$(printf '%s' "$ACTIVE_RUN_JSON" | jq -r '(.started_at // .startedAt // .submitted_at // .submittedAt // .created_at // .createdAt // empty)' 2>/dev/null || true)"
    if [ -n "$ACTIVE_RUN_STARTED_AT" ] && [ -n "$ACTIVE_RUN_STATUS" ] && [ "$ACTIVE_RUN_STATUS" != "succeeded" ] && [ "$ACTIVE_RUN_STATUS" != "failed" ] && [ "$ACTIVE_RUN_STATUS" != "cancelled" ]; then
      ACTIVE_RUN_STARTED_AT_EPOCH="$(iso8601_to_epoch "$ACTIVE_RUN_STARTED_AT")"
      ACTIVE_RUN_AGE_SECONDS=$((smoke_started_at_epoch - ACTIVE_RUN_STARTED_AT_EPOCH))
      if [ "$ACTIVE_RUN_AGE_SECONDS" -ge "$DQ_SMOKE_GX_ACTIVE_RUN_STALE_SECONDS" ]; then
        error "$my_name" "Detected stale active GX run_id=${RUN_ID} status=${ACTIVE_RUN_STATUS} started_at=${ACTIVE_RUN_STARTED_AT}"
        error "$my_name" "Refusing to reuse a run that was already active before this smoke invocation; cancel it and rerun."
        exit 10
      fi
    fi
    warning "$my_name" "Ad-hoc enqueue already has active run_id=${RUN_ID}; reusing it"
  else
    error "$my_name" "Failed to enqueue ad-hoc GX run (HTTP ${RUNS_HTTP_CODE})"
    printf '%s\n' "$RUNS_JSON" >&2
    exit 10
  fi
elif [ "$RUNS_HTTP_CODE" = "200" ] || [ "$RUNS_HTTP_CODE" = "202" ]; then
  RUN_ID="$(printf '%s' "$RUNS_JSON" | jq -r '.[0].run_id // empty')"
  if [ -z "$RUN_ID" ]; then
    error "$my_name" "Ad-hoc enqueue response missing run_id"
    printf '%s\n' "$RUNS_JSON" >&2
    exit 10
  fi
  info "$my_name" "Enqueued run_id=${RUN_ID}"
else
  error "$my_name" "Failed to enqueue ad-hoc GX run (HTTP ${RUNS_HTTP_CODE})"
  printf '%s\n' "$RUNS_JSON" >&2
  exit 10
fi

run_deadline=$(( $(date +%s) + DQ_SMOKE_GX_TIMEOUT_SECONDS ))
run_poll_i=0
run_started_at_epoch=$(date +%s)
while true; do
  run_poll_i=$((run_poll_i + 1))

  # Poll run status but don't crash on transient gateway errors; handle status codes explicitly.
  RUN_HTTP_CODE="$(
    curl -sS -o "$RUN_JSON_PATH" -w "%{http_code}" \
      "${KONG_PUBLIC_URL%/}/rulebuilder/v1/gx/runs/${RUN_ID}" \
      "${AUTH_HEADER[@]}" || true
  )"

  if [ "$RUN_HTTP_CODE" != "200" ]; then
    if [ "$RUN_HTTP_CODE" = "401" ]; then
      warning "$my_name" "Waiting for GX run: http=401 (token likely expired); refreshing token"
      mint_token
    fi
    if (( run_poll_i % 5 == 0 )); then
      warning "$my_name" "Waiting for GX run: http=${RUN_HTTP_CODE}"
    fi
    now=$(date +%s)
    if [ "$now" -ge "$run_deadline" ]; then
      error "$my_name" "Timed out waiting for GX run completion (last http=${RUN_HTTP_CODE})"
      exit 11
    fi
    sleep 2
    continue
  fi

  RUN_JSON="$(cat "$RUN_JSON_PATH")"
  RUN_STATUS="$(printf '%s' "$RUN_JSON" | jq -r '.status // empty')"

  if (( run_poll_i % 5 == 0 )); then
    now=$(date +%s)
    elapsed=$((now - run_started_at_epoch))
    info "$my_name" "Waiting for GX run: status=${RUN_STATUS} elapsed=${elapsed}s"
  fi

  if [ "$RUN_STATUS" = "succeeded" ] || [ "$RUN_STATUS" = "failed" ] || [ "$RUN_STATUS" = "cancelled" ]; then
    break
  fi

  now=$(date +%s)
  if [ "$now" -ge "$run_deadline" ]; then
    error "$my_name" "Timed out waiting for GX run completion (status=${RUN_STATUS})"
    exit 11
  fi

  sleep 2
done

if [ "$RUN_STATUS" != "succeeded" ]; then
  error "$my_name" "GX run did not succeed (status=${RUN_STATUS})"
  error "$my_name" "failure_code=$(printf '%s' "$RUN_JSON" | jq -r '.failure_code // empty')"
  error "$my_name" "failure_message=$(printf '%s' "$RUN_JSON" | jq -r '.failure_message // empty')"
  exit 12
fi

REPORTED_URIS="$(
  printf '%s' "$RUN_JSON" | jq -r '
    (.result_summary.results // [])
    | map(.storage_uri // empty)
    | map(select(type=="string" and length>0))
    | unique
    | .[]
  '
)"

if ! printf '%s\n' "$REPORTED_URIS" | grep -Fq "$OUTPUT_URI"; then
  error "$my_name" "GX run succeeded but did not report storage_uri matching the source override"
  error "$my_name" "expected to find: $OUTPUT_URI"
  error "$my_name" "reported storage_uris:"
  printf '%s\n' "$REPORTED_URIS" >&2
  exit 13
fi

info "$my_name" "✓ Smoke test succeeded: run used override storage_uri"
