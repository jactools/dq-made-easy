#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate end-to-end rule lifecycle for currently GX-executable rule kinds.
#
# What it does:
# - Creates fresh rules for supported rule kinds with two seeded variations per kind.
# - Assigns selected catalog attributes, validates, queues/runs generated-data tests, requests approval, approves, and activates with GX auto-publish.
# - Materializes selected attributes to AIStor-backed test storage and runs ad-hoc GX execution against that materialized data.
# - Can fan selected cases out with bounded case-level parallelism while Spark-backed work waits in Redis-backed worker queues.
# - Loads the supported-case catalog from a dedicated JSON file under validation-data/.
# - Reports unsupported rule kinds explicitly and can fail fast when full all-rule-kind coverage is required.
#
# validate: groups=regression
# Version: 2.8
# Last modified: 2026-05-20
# Changelog:
# - 2.6 (2026-05-20): Added an AIStor row-count assertion for the high-invalid-rows seed case.
# - 2.7 (2026-05-20): Filtered unsupported custom_query_assertion cases out of the supported GX runner.
# - 2.8 (2026-05-20): Reinstated custom_query_assertion cases after the GX bridge learned their expression shapes.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
set_log_level INFO
my_name="validate_rule_lifecycle_gx_supported.sh"
SUPPORTED_CASES_FILE="$ROOT_DIR/validation-data/validate_rule_lifecycle_gx_supported_cases.json"
DEFAULT_PARALLELISM=4

require_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: $name"
    exit 2
  fi
}

require_cmd curl
require_cmd docker
require_cmd jq
require_cmd mktemp

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

if [[ -z "$engine_oidc_env" ]]; then
  error "$my_name" "Unable to resolve a stage-specific engine OIDC env file from ENVIRONMENT=${ENVIRONMENT:-<unset>}"
  exit 2
fi

if [[ -f "$engine_oidc_env" ]]; then
  # shellcheck disable=SC1091
  set +u
  source "$engine_oidc_env"
  set -u
fi

KONG_PUBLIC_URL="${KONG_PUBLIC_URL:?KONG_PUBLIC_URL must be set to the public Kong URL used by the UI}"
KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [[ -f "$KONG_CA_CERT" ]] && [[ -z "${CURL_CA_BUNDLE:-}" ]]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi
KEYCLOAK_REALM="${KEYCLOAK_REALM:?KEYCLOAK_REALM must be set}"
SSO_ENABLED="${SSO_ENABLED:?SSO_ENABLED must be set}"
SSO_ISSUER="${SSO_PUBLIC_ISSUER_URL:?SSO_PUBLIC_ISSUER_URL must be set}"
KEYCLOAK_BASE_URL="${KEYCLOAK_PUBLIC_URL:?KEYCLOAK_PUBLIC_URL must be set}"

DQ_RULE_E2E_GRANT_TYPE="password"
DQ_RULE_E2E_CLIENT_ID="${KEYCLOAK_CLIENT_ID:?KEYCLOAK_CLIENT_ID must be set}"
DQ_RULE_E2E_CLIENT_SECRET=""
DQ_RULE_E2E_USERNAME="${KEYCLOAK_JACCLOUD_USERNAME:?KEYCLOAK_JACCLOUD_USERNAME must be set}"
DQ_RULE_E2E_PASSWORD="${KEYCLOAK_JACCLOUD_PASSWORD:?KEYCLOAK_JACCLOUD_PASSWORD must be set}"
DQ_RULE_E2E_APPROVER_GRANT_TYPE="password"
DQ_RULE_E2E_APPROVER_CLIENT_ID="${DQ_RULE_E2E_CLIENT_ID}"
DQ_RULE_E2E_APPROVER_CLIENT_SECRET=""
DQ_RULE_E2E_APPROVER_USERNAME="${SMOKE_LOGIN_EMAIL:?SMOKE_LOGIN_EMAIL must be set}"
DQ_RULE_E2E_APPROVER_PASSWORD="${SMOKE_LOGIN_PASSWORD:?SMOKE_LOGIN_PASSWORD must be set}"
DQ_RULE_E2E_WORKSPACE_ID="${DQ_RULE_E2E_WORKSPACE_ID:-retail-banking}"
DQ_RULE_E2E_TEST_SAMPLE_COUNT="${DQ_RULE_E2E_TEST_SAMPLE_COUNT:-6}"
DQ_RULE_E2E_MATERIALIZATION_SAMPLE_COUNT="${DQ_RULE_E2E_MATERIALIZATION_SAMPLE_COUNT:-200}"
DQ_RULE_E2E_OUTPUT_FORMAT="${DQ_RULE_E2E_OUTPUT_FORMAT:-parquet}"
DQ_RULE_E2E_REQUIRE_ALL_RULE_KINDS="${DQ_RULE_E2E_REQUIRE_ALL_RULE_KINDS:-false}"
DQ_RULE_E2E_MATERIALIZATION_TIMEOUT_SECONDS="${DQ_RULE_E2E_MATERIALIZATION_TIMEOUT_SECONDS:-180}"
DQ_RULE_E2E_GX_TIMEOUT_SECONDS="${DQ_RULE_E2E_GX_TIMEOUT_SECONDS:-900}"

case "$DQ_RULE_E2E_OUTPUT_FORMAT" in
  parquet|delta) ;;
  *)
    error "$my_name" "Unsupported DQ_RULE_E2E_OUTPUT_FORMAT: ${DQ_RULE_E2E_OUTPUT_FORMAT}"
    exit 2
    ;;
esac

case "$DQ_RULE_E2E_REQUIRE_ALL_RULE_KINDS" in
  true|false) ;;
  *)
    error "$my_name" "DQ_RULE_E2E_REQUIRE_ALL_RULE_KINDS must be true or false"
    exit 2
    ;;
esac

if [[ "$SSO_ENABLED" == "true" && -n "$SSO_ISSUER" ]]; then
  TOKEN_ENDPOINT="${SSO_ISSUER%/}/protocol/openid-connect/token"
else
  TOKEN_ENDPOINT="${KEYCLOAK_BASE_URL%/}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token"
fi

UNSUPPORTED_RULE_KINDS_JSON='[]'

print_usage() {
  cat <<'EOF'
Usage: validate_rule_lifecycle_gx_supported.sh
  validate_rule_lifecycle_gx_supported.sh [--rule-kinds CSV] [--dimensions CSV] [--case-ids CSV] [--parallelism N]

Runs a live end-to-end validation for the rule kinds that are currently
executable through the rule -> compiler -> GX suite -> ad-hoc AIStor path.

Optional filters:
  --rule-kinds CSV                          Only run cases with these rule kinds (comma-separated)
  --dimensions CSV                         Only run cases with these dimensions (comma-separated)
  --case-ids CSV                           Only run these case ids (comma-separated)
  --parallelism N                          Run up to N validation cases concurrently (default: 4)

Notes:
  - This parallelism is case-level orchestration parallelism.
  - Spark-backed materialization and GX execution are performed by queue-backed workers
    and remain serialized by worker consumption; extra requests wait in Redis.

Selection filters are CLI-only on purpose, so the executed subset is explicit in shell history.

Environment overrides:
  KONG_PUBLIC_URL                            Default: https://kong.jac.dot:9443
  DQ_RULE_E2E_WORKSPACE_ID                   Default: retail-banking
  DQ_RULE_E2E_GRANT_TYPE                     Fixed: password
  DQ_RULE_E2E_CLIENT_ID                      Required: canonical Keycloak client id
  DQ_RULE_E2E_CLIENT_SECRET                  Unused
  DQ_RULE_E2E_USERNAME                       Required: seeded requester username
  DQ_RULE_E2E_PASSWORD                       Required: seeded requester password
  DQ_RULE_E2E_APPROVER_GRANT_TYPE            Fixed: password
  DQ_RULE_E2E_APPROVER_CLIENT_ID             Same as requester client id
  DQ_RULE_E2E_APPROVER_CLIENT_SECRET         Unused
  DQ_RULE_E2E_APPROVER_USERNAME              Required: seeded approver username
  DQ_RULE_E2E_APPROVER_PASSWORD              Required: seeded approver password
  DQ_RULE_E2E_TEST_SAMPLE_COUNT              Default: 6
  DQ_RULE_E2E_MATERIALIZATION_SAMPLE_COUNT   Default: 200
  DQ_RULE_E2E_OUTPUT_FORMAT                  Default: parquet
  DQ_RULE_E2E_REQUIRE_ALL_RULE_KINDS         true|false, default false

Requirements:
  - validation-data/validate_rule_lifecycle_gx_supported_cases.json
    must exist and contain a JSON array of supported cases.
  - docker must be available because join_pair cases temporarily bootstrap
    source storage metadata in the running db container before GX dispatch.

When DQ_RULE_E2E_REQUIRE_ALL_RULE_KINDS=true, the script exits non-zero before
execution because several rule kinds are still not covered by this validator,
either due to remaining compiler/GX limits or missing live cross-object test coverage.
EOF
}

normalize_csv_json() {
  local raw_value="$1"
  local mode="$2"

  jq -nc --arg raw "$raw_value" --arg mode "$mode" '
    $raw
    | split(",")
    | map(gsub("^[[:space:]]+|[[:space:]]+$"; ""))
    | map(select(length > 0))
    | map(if $mode == "upper" then ascii_upcase else ascii_downcase end)
    | unique
  '
}

load_supported_cases_json() {
  if [[ ! -f "$SUPPORTED_CASES_FILE" ]]; then
    error "$my_name" "Supported cases file is missing: ${SUPPORTED_CASES_FILE}"
    exit 2
  fi

  if ! SUPPORTED_CASES_JSON="$(jq -c 'if type == "array" then . else error("supported cases root must be an array") end' "$SUPPORTED_CASES_FILE")"; then
    error "$my_name" "Supported cases file is invalid JSON: ${SUPPORTED_CASES_FILE}"
    exit 2
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        print_usage
        exit 0
        ;;
      --rule-kinds)
        if [[ $# -lt 2 ]]; then
          error "$my_name" "--rule-kinds requires a comma-separated value"
          exit 2
        fi
        RULE_KINDS_FILTER_CSV="$2"
        shift 2
        ;;
      --rule-kinds=*)
        RULE_KINDS_FILTER_CSV="${1#*=}"
        shift
        ;;
      --dimensions)
        if [[ $# -lt 2 ]]; then
          error "$my_name" "--dimensions requires a comma-separated value"
          exit 2
        fi
        DIMENSIONS_FILTER_CSV="$2"
        shift 2
        ;;
      --dimensions=*)
        DIMENSIONS_FILTER_CSV="${1#*=}"
        shift
        ;;
      --case-ids)
        if [[ $# -lt 2 ]]; then
          error "$my_name" "--case-ids requires a comma-separated value"
          exit 2
        fi
        CASE_IDS_FILTER_CSV="$2"
        shift 2
        ;;
      --case-ids=*)
        CASE_IDS_FILTER_CSV="${1#*=}"
        shift
        ;;
      --parallelism)
        if [[ $# -lt 2 ]]; then
          error "$my_name" "--parallelism requires a numeric value"
          exit 2
        fi
        PARALLELISM="$2"
        shift 2
        ;;
      --parallelism=*)
        PARALLELISM="${1#*=}"
        shift
        ;;
      *)
        error "$my_name" "Unknown argument: $1"
        print_usage
        exit 2
        ;;
    esac
  done
}

ACCESS_TOKEN=""
APPROVER_ACCESS_TOKEN=""
MINTED_ACCESS_TOKEN=""
AUTH_HEADER=()
API_BODY=""
API_HTTP_CODE=""
CASE_PASSED_COUNT=0
RUN_STAMP="$(date +%Y%m%d%H%M%S)"
DB_CONTAINER_ID=""
ENGINE_STAGE_CONTAINER_ID=""
JOIN_PAIR_RESTORE_SQL_FILE="$(mktemp "${TMPDIR:-/tmp}/dq-rule-e2e-storage-restore.XXXXXX")"
RULE_KINDS_FILTER_CSV=""
DIMENSIONS_FILTER_CSV=""
CASE_IDS_FILTER_CSV=""
PARALLELISM="$DEFAULT_PARALLELISM"
SELECTED_RULE_KINDS_JSON='[]'
SELECTED_DIMENSIONS_JSON='[]'
SELECTED_CASE_IDS_JSON='[]'
SUPPORTED_CASES_JSON='[]'
FILTERED_SUPPORTED_CASES_JSON='[]'
FILTERED_UNSUPPORTED_RULE_KINDS_JSON='[]'
PARALLEL_FAILURE=0
PARALLEL_LOG_DIR=""
CASE_JOB_PIDS=()
CASE_JOB_IDS=()
CASE_JOB_LOGS=()

parse_args "$@"

case "$PARALLELISM" in
  ''|*[!0-9]*)
    error "$my_name" "--parallelism must be a positive integer"
    exit 2
    ;;
  *)
    if [[ "$PARALLELISM" -lt 1 ]]; then
      error "$my_name" "--parallelism must be a positive integer"
      exit 2
    fi
    ;;
esac

load_supported_cases_json

SELECTED_RULE_KINDS_JSON="$(normalize_csv_json "$RULE_KINDS_FILTER_CSV" upper)"
SELECTED_DIMENSIONS_JSON="$(normalize_csv_json "$DIMENSIONS_FILTER_CSV" lower)"
SELECTED_CASE_IDS_JSON="$(normalize_csv_json "$CASE_IDS_FILTER_CSV" lower)"
FILTERED_SUPPORTED_CASES_JSON="$(
  printf '%s' "$SUPPORTED_CASES_JSON" | jq \
    --argjson selected_rule_kinds "$SELECTED_RULE_KINDS_JSON" \
    --argjson selected_dimensions "$SELECTED_DIMENSIONS_JSON" \
    --argjson selected_case_ids "$SELECTED_CASE_IDS_JSON" \
    --argjson unsupported_rule_kinds "$UNSUPPORTED_RULE_KINDS_JSON" '
      map(
        . as $case
        | select(
            (($selected_rule_kinds | length) == 0 or ($selected_rule_kinds | index(($case.dsl.rule.kind // "" | ascii_upcase)) != null))
            and (($selected_dimensions | length) == 0 or ($selected_dimensions | index(($case.dimension // "" | ascii_downcase)) != null))
            and (($selected_case_ids | length) == 0 or ($selected_case_ids | index(($case.case_id // "" | ascii_downcase)) != null))
          )
      )
    '
)"
FILTERED_UNSUPPORTED_RULE_KINDS_JSON="$(
  printf '%s' "$UNSUPPORTED_RULE_KINDS_JSON" | jq \
    --argjson selected_rule_kinds "$SELECTED_RULE_KINDS_JSON" '
      if ($selected_rule_kinds | length) == 0 then
        .
      else
        map(. as $entry | select($selected_rule_kinds | index(($entry.kind // "" | ascii_upcase)) != null))
      end
    '
)"

if [[ "$(printf '%s' "$FILTERED_SUPPORTED_CASES_JSON" | jq 'length')" -eq 0 ]]; then
  error "$my_name" "No supported GX lifecycle cases match the requested filters"
  if [[ -n "$RULE_KINDS_FILTER_CSV" ]]; then
    error "$my_name" "Requested rule kinds: ${RULE_KINDS_FILTER_CSV}"
  fi
  if [[ -n "$DIMENSIONS_FILTER_CSV" ]]; then
    error "$my_name" "Requested dimensions: ${DIMENSIONS_FILTER_CSV}"
  fi
  if [[ -n "$CASE_IDS_FILTER_CSV" ]]; then
    error "$my_name" "Requested case ids: ${CASE_IDS_FILTER_CSV}"
  fi
  exit 2
fi

mint_token() {
  info "$my_name" "Requesting requester JWT for ${DQ_RULE_E2E_USERNAME} from ${TOKEN_ENDPOINT}"
  ACCESS_TOKEN="$(dq_keycloak_password_grant_access_token "$TOKEN_ENDPOINT" "$DQ_RULE_E2E_CLIENT_ID" "$DQ_RULE_E2E_USERNAME" "$DQ_RULE_E2E_PASSWORD")"
  AUTH_HEADER=( -H "Authorization: Bearer ${ACCESS_TOKEN}" )
}

mint_approver_token() {
  if [[ "$DQ_RULE_E2E_APPROVER_USERNAME" == "$DQ_RULE_E2E_USERNAME" ]]; then
    error "$my_name" "Approver username must differ from requester username to avoid self-approval"
    exit 1
  fi

  info "$my_name" "Requesting approver JWT for ${DQ_RULE_E2E_APPROVER_USERNAME} from ${TOKEN_ENDPOINT}"
  APPROVER_ACCESS_TOKEN="$(dq_keycloak_password_grant_access_token "$TOKEN_ENDPOINT" "$DQ_RULE_E2E_APPROVER_CLIENT_ID" "$DQ_RULE_E2E_APPROVER_USERNAME" "$DQ_RULE_E2E_APPROVER_PASSWORD")"
}

api_request_once() {
  local method="$1"
  local endpoint="$2"
  local body="${3-}"
  local response

  if [[ -n "$body" ]]; then
    if ! response="$(curl -sS -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" "${AUTH_HEADER[@]}" -H "Content-Type: application/json" -d "$body" -w $'\n%{http_code}')"; then
      error "$my_name" "HTTP ${method} ${endpoint} failed"
      exit 1
    fi
  else
    if ! response="$(curl -sS -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" "${AUTH_HEADER[@]}" -w $'\n%{http_code}')"; then
      error "$my_name" "HTTP ${method} ${endpoint} failed"
      exit 1
    fi
  fi

  API_HTTP_CODE="${response##*$'\n'}"
  API_BODY="${response%$'\n'*}"
}

api_request() {
  local method="$1"
  local endpoint="$2"
  local body="${3-}"

  api_request_once "$method" "$endpoint" "$body"
  if [[ "$API_HTTP_CODE" == "401" ]]; then
    warning "$my_name" "Received 401 for ${method} ${endpoint}; refreshing token once"
    mint_token
    api_request_once "$method" "$endpoint" "$body"
  fi
}

api_request_as_approver() {
  local method="$1"
  local endpoint="$2"
  local body="${3-}"
  local response

  if [[ -z "$APPROVER_ACCESS_TOKEN" ]]; then
    mint_approver_token
  fi

  if [[ -n "$body" ]]; then
    if ! response="$(curl -sS -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" -H "Authorization: Bearer ${APPROVER_ACCESS_TOKEN}" -H "Content-Type: application/json" -d "$body" -w $'\n%{http_code}')"; then
      error "$my_name" "HTTP ${method} ${endpoint} failed for approver"
      exit 1
    fi
  else
    if ! response="$(curl -sS -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" -H "Authorization: Bearer ${APPROVER_ACCESS_TOKEN}" -w $'\n%{http_code}')"; then
      error "$my_name" "HTTP ${method} ${endpoint} failed for approver"
      exit 1
    fi
  fi

  API_HTTP_CODE="${response##*$'\n'}"
  API_BODY="${response%$'\n'*}"

  if [[ "$API_HTTP_CODE" == "401" ]]; then
    warning "$my_name" "Received 401 for approver ${method} ${endpoint}; refreshing token once"
    mint_approver_token
    api_request_as_approver_once_retry "$method" "$endpoint" "$body"
  fi
}

api_request_as_approver_once_retry() {
  local method="$1"
  local endpoint="$2"
  local body="${3-}"
  local response

  if [[ -n "$body" ]]; then
    if ! response="$(curl -sS -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" -H "Authorization: Bearer ${APPROVER_ACCESS_TOKEN}" -H "Content-Type: application/json" -d "$body" -w $'\n%{http_code}')"; then
      error "$my_name" "HTTP ${method} ${endpoint} failed for approver"
      exit 1
    fi
  else
    if ! response="$(curl -sS -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" -H "Authorization: Bearer ${APPROVER_ACCESS_TOKEN}" -w $'\n%{http_code}')"; then
      error "$my_name" "HTTP ${method} ${endpoint} failed for approver"
      exit 1
    fi
  fi

  API_HTTP_CODE="${response##*$'\n'}"
  API_BODY="${response%$'\n'*}"
}

require_status() {
  local expected="$1"
  local label="$2"
  if [[ "$API_HTTP_CODE" != "$expected" ]]; then
    error "$my_name" "${label} returned HTTP ${API_HTTP_CODE}; expected ${expected}"
    printf '%s\n' "$API_BODY" >&2
    exit 1
  fi
}

sql_quote() {
  local value="$1"
  value="${value//\'/\'\'}"
  printf "'%s'" "$value"
}

sql_nullable() {
  local value="$1"
  if [[ -z "$value" ]]; then
    printf 'NULL'
    return 0
  fi
  sql_quote "$value"
}

ensure_db_container_id() {
  if [[ -n "$DB_CONTAINER_ID" ]]; then
    return 0
  fi

  DB_CONTAINER_ID="$(docker ps --filter 'label=com.docker.compose.service=db' --filter 'status=running' --format '{{.ID}}' | head -n 1 | tr -d '[:space:]')"
  if [[ -z "$DB_CONTAINER_ID" ]]; then
    error "$my_name" "Unable to resolve the running db container for join_pair storage bootstrapping"
    exit 1
  fi
}

ensure_engine_stage_container_id() {
  if [[ -n "$ENGINE_STAGE_CONTAINER_ID" ]]; then
    return 0
  fi

  ENGINE_STAGE_CONTAINER_ID="$(docker ps --filter label=com.docker.compose.project=dq-rulebuilder --filter label=com.docker.compose.service=dq-engine-test-data-worker --format '{{.ID}}' | head -n 1 | tr -d '[:space:]')"
  if [[ -z "$ENGINE_STAGE_CONTAINER_ID" ]]; then
    error "$my_name" "Unable to resolve the running dq-engine-test-data-worker container for local CSV parquet staging"
    exit 1
  fi
}

sanitize_identifier() {
  printf '%s' "$1" | tr -cs 'A-Za-z0-9._-' '_'
}

cleanup_parallel_jobs() {
  local pid log_file

  for pid in "${CASE_JOB_PIDS[@]}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done

  for log_file in "${CASE_JOB_LOGS[@]}"; do
    if [[ -n "$log_file" && -f "$log_file" ]]; then
      rm -f "$log_file"
    fi
  done

  if [[ -n "$PARALLEL_LOG_DIR" && -d "$PARALLEL_LOG_DIR" ]]; then
    rmdir "$PARALLEL_LOG_DIR" >/dev/null 2>&1 || true
  fi
}

db_query_tsv() {
  local sql="$1"
  ensure_db_container_id
  docker exec "$DB_CONTAINER_ID" psql -U postgres -d dq -v ON_ERROR_STOP=1 -P pager=off -At -F $'\t' -c "$sql"
}

db_exec_sql() {
  local sql="$1"
  ensure_db_container_id
  docker exec "$DB_CONTAINER_ID" psql -U postgres -d dq -v ON_ERROR_STOP=1 -P pager=off -c "$sql" >/dev/null
}

queue_restore_version_storage() {
  local version_id="$1"
  local storage_uri="$2"
  local storage_format="$3"

  if grep -Fqx -- "-- version:${version_id}" "$JOIN_PAIR_RESTORE_SQL_FILE"; then
    return 0
  fi

  {
    printf -- "-- version:%s\n" "$version_id"
    printf 'UPDATE data_object_versions SET storage_uri = %s, storage_format = %s WHERE id = %s;\n' \
      "$(sql_nullable "$storage_uri")" \
      "$(sql_nullable "$storage_format")" \
      "$(sql_quote "$version_id")"
  } >> "$JOIN_PAIR_RESTORE_SQL_FILE"
}

cleanup_join_pair_storage_bootstrap() {
  if [[ -z "${JOIN_PAIR_RESTORE_SQL_FILE:-}" || ! -f "$JOIN_PAIR_RESTORE_SQL_FILE" ]]; then
    return 0
  fi

  if [[ -s "$JOIN_PAIR_RESTORE_SQL_FILE" ]]; then
    if ensure_db_container_id 2>/dev/null; then
      if ! docker exec -i "$DB_CONTAINER_ID" psql -U postgres -d dq -v ON_ERROR_STOP=1 -P pager=off < "$JOIN_PAIR_RESTORE_SQL_FILE" >/dev/null 2>&1; then
        warning "$my_name" "Failed to restore data_object_versions storage metadata after join_pair validation"
      fi
    else
      warning "$my_name" "Skipped restoring data_object_versions storage metadata because the db container is unavailable"
    fi
  fi

  rm -f "$JOIN_PAIR_RESTORE_SQL_FILE"
}

cleanup_script_state() {
  cleanup_parallel_jobs
  cleanup_join_pair_storage_bootstrap
}

trap cleanup_script_state EXIT

print_unsupported_matrix() {
  if [[ "$(printf '%s' "$FILTERED_UNSUPPORTED_RULE_KINDS_JSON" | jq 'length')" -eq 0 ]]; then
    return 0
  fi
  warning "$my_name" "The following rule kinds are not currently covered by this validator end-to-end:"
  printf '%s' "$FILTERED_UNSUPPORTED_RULE_KINDS_JSON" | jq -r '.[] | "  - \(.kind): \(.reason)"'
}

lookup_attribute_id() {
  local version_id="$1"
  local attribute_name="$2"

  api_request GET "/data-catalog/v1/attributes-catalog?versionId=${version_id}&page=1&limit=100"
  require_status 200 "Attribute lookup for ${version_id}"

  local attribute_id
  attribute_id="$(printf '%s' "$API_BODY" | jq -r --arg name "$attribute_name" '.data[] | select(.name == $name) | .id' | head -n 1)"
  if [[ -z "$attribute_id" ]]; then
    error "$my_name" "Attribute '${attribute_name}' not found on version ${version_id}"
    printf '%s\n' "$API_BODY" >&2
    exit 1
  fi
  printf '%s\n' "$attribute_id"
}

poll_materialization() {
  local request_id="$1"
  local deadline=$(( $(date +%s) + DQ_RULE_E2E_MATERIALIZATION_TIMEOUT_SECONDS ))

  while true; do
    api_request GET "/rulebuilder/v1/test-data/materializations/${request_id}"
    require_status 200 "Get test-data materialization ${request_id}"

    local status
    status="$(printf '%s' "$API_BODY" | jq -r '.status // empty')"
    if [[ "$status" == "completed" ]]; then
      return 0
    fi
    if [[ "$status" == "failed" ]]; then
      error "$my_name" "Materialization ${request_id} failed"
      printf '%s\n' "$API_BODY" >&2
      exit 1
    fi
    if [[ $(date +%s) -ge $deadline ]]; then
      error "$my_name" "Timed out waiting for materialization ${request_id}"
      printf '%s\n' "$API_BODY" >&2
      exit 1
    fi
    sleep 2
  done
}

poll_gx_run() {
  local run_id="$1"
  local deadline=$(( $(date +%s) + DQ_RULE_E2E_GX_TIMEOUT_SECONDS ))

  while true; do
    api_request GET "/rulebuilder/v1/gx/runs/${run_id}"
    require_status 200 "Get GX run ${run_id}"

    local status
    status="$(printf '%s' "$API_BODY" | jq -r '.status // empty')"
    if [[ "$status" == "succeeded" ]]; then
      return 0
    fi
    if [[ "$status" == "failed" || "$status" == "cancelled" ]]; then
      error "$my_name" "GX run ${run_id} ended with status=${status}"
      printf '%s\n' "$API_BODY" >&2
      exit 1
    fi
    if [[ $(date +%s) -ge $deadline ]]; then
      error "$my_name" "Timed out waiting for GX run ${run_id}"
      printf '%s\n' "$API_BODY" >&2
      exit 1
    fi
    sleep 2
  done
}

materialize_test_source() {
  local version_id="$1"
  local selected_attribute_names_json="$2"
  local case_id="$3"
  local role="$4"

  local materialization_body
  materialization_body="$(jq -nc \
    --arg version_id "$version_id" \
    --arg output_format "$DQ_RULE_E2E_OUTPUT_FORMAT" \
    --argjson sample_count "$DQ_RULE_E2E_MATERIALIZATION_SAMPLE_COUNT" \
    --argjson selected_attribute_names "$selected_attribute_names_json" \
    '{
      data_object_version_id: $version_id,
      sample_count: $sample_count,
      output_format: $output_format,
      refresh: true,
      selected_attribute_names: $selected_attribute_names
    }')"

  api_request POST "/rulebuilder/v1/test-data/materializations" "$materialization_body"
  require_status 202 "Create ${role} test-data materialization for ${case_id}"

  local materialization_request_id
  materialization_request_id="$(printf '%s' "$API_BODY" | jq -r '.request_id // empty')"
  if [[ -z "$materialization_request_id" ]]; then
    error "$my_name" "Materialization response missing request_id for ${case_id} (${role})"
    printf '%s\n' "$API_BODY" >&2
    exit 1
  fi

  poll_materialization "$materialization_request_id"

  local materialization_json output_uri output_format
  materialization_json="$API_BODY"
  output_uri="$(printf '%s' "$materialization_json" | jq -r '(.result.output_uri // .output_uri // empty)')"
  output_format="$(printf '%s' "$materialization_json" | jq -r '(.result.output_format // .output_format // empty)')"
  if [[ -z "$output_uri" || -z "$output_format" ]]; then
    error "$my_name" "Completed materialization missing output_uri/output_format for ${case_id} (${role})"
    printf '%s\n' "$materialization_json" >&2
    exit 1
  fi

  jq -nc \
    --arg version_id "$version_id" \
    --arg output_uri "$output_uri" \
    --arg output_format "$output_format" \
    '{version_id: $version_id, output_uri: $output_uri, output_format: $output_format}'
}

stage_local_csv_source() {
  local version_id="$1"
  local local_csv_path="$2"
  local local_csv_transform="$3"
  local case_id="$4"
  local role="$5"

  local absolute_csv_path
  absolute_csv_path="$ROOT_DIR/$local_csv_path"
  if [[ ! -f "$absolute_csv_path" ]]; then
    error "$my_name" "Local CSV source for ${case_id} (${role}) does not exist: ${local_csv_path}"
    exit 1
  fi
  if [[ ! -s "$absolute_csv_path" ]]; then
    error "$my_name" "Local CSV source for ${case_id} (${role}) is empty: ${local_csv_path}"
    exit 1
  fi

  ensure_engine_stage_container_id

  local helper_container_path csv_basename container_csv_path sanitized_case_id sanitized_role
  helper_container_path="/tmp/stage_local_csv_to_s3_parquet.py"
  sanitized_case_id="$(sanitize_identifier "$case_id")"
  sanitized_role="$(sanitize_identifier "$role")"
  csv_basename="$(basename "$local_csv_path")"
  container_csv_path="/tmp/${sanitized_case_id}-${sanitized_role}-${csv_basename}"

  docker cp "$ROOT_DIR/scripts/stage_local_csv_to_s3_parquet.py" "${ENGINE_STAGE_CONTAINER_ID}:${helper_container_path}" >/dev/null
  docker cp "$absolute_csv_path" "${ENGINE_STAGE_CONTAINER_ID}:${container_csv_path}" >/dev/null

  docker exec "$ENGINE_STAGE_CONTAINER_ID" python "$helper_container_path" \
    --workspace-id "$DQ_RULE_E2E_WORKSPACE_ID" \
    --case-id "$case_id" \
    --role "$role" \
    --version-id "$version_id" \
    --input-csv "$container_csv_path" \
    --transform "$local_csv_transform"
}

register_materialized_delivery_note() {
  local data_delivery_id="$1"
  local data_object_id="$2"
  local version_id="$3"
  local output_uri="$4"
  local output_format="$5"
  local attributes_count="$6"
  local source_snapshot_id="$7"

  db_exec_sql "
    INSERT INTO data_deliveries (
      id,
      data_object_version_id,
      data_object_id,
      version,
      timestamp,
      layer,
      delivery_location,
      record_count,
      size_bytes,
      status,
      attributes_count
    ) VALUES (
      $(sql_quote "$data_delivery_id"),
      $(sql_quote "$version_id"),
      $(sql_quote "$data_object_id"),
      1,
      NOW(),
      'standardized',
      $(sql_quote "$output_uri"),
      NULL,
      NULL,
      'completed',
      $(sql_nullable "$attributes_count")
    );

    INSERT INTO data_delivery_notes (
      data_delivery_id,
      layer,
      storage_location,
      delivery_format,
      file_count,
      ingestor_name,
      ingestor_run_id,
      source_system,
      source_snapshot_id,
      checksum,
      checksum_algorithm,
      metadata_json
    ) VALUES (
      $(sql_quote "$data_delivery_id"),
      'standardized',
      $(sql_quote "$output_uri"),
      $(sql_quote "$output_format"),
      1,
      'dq-rulebuilder-custom-query-validator',
      $(sql_nullable "$RUN_STAMP"),
      'validation',
      $(sql_quote "$source_snapshot_id"),
      NULL,
      NULL,
      jsonb_build_object('validator', 'custom_query_assertion', 'output_uri', $(sql_quote "$output_uri"))
    );
  "
}

count_rows_in_materialized_parquet() {
  local output_uri="$1"
  local column_name="$2"
  local regex_pattern="$3"

  ensure_engine_stage_container_id

  docker exec -i "$ENGINE_STAGE_CONTAINER_ID" python - "$output_uri" "$column_name" "$regex_pattern" <<'PY'
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import boto3
from pyspark.sql import SparkSession, functions as F

output_uri = sys.argv[1].strip()
column_name = sys.argv[2].strip()
regex_pattern = sys.argv[3]

if output_uri.startswith("s3a://"):
  scheme = "s3a://"
elif output_uri.startswith("s3://"):
  scheme = "s3://"
else:
  raise SystemExit(f"Expected an s3:// or s3a:// output URI, got {output_uri!r}")

bucket_and_key = output_uri[len(scheme) :]
bucket, _, key_prefix = bucket_and_key.partition("/")
key_prefix = key_prefix.rstrip("/")
if not bucket or not key_prefix:
    raise SystemExit(f"Invalid materialized output URI: {output_uri!r}")

endpoint = (os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL") or "").strip()
access_key = (os.getenv("DQ_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
secret_key = (os.getenv("DQ_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
region = (os.getenv("DQ_S3_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "").strip() or None
ssl_enabled_raw = (os.getenv("DQ_S3_SSL_ENABLED") or "").strip().lower()
verify = endpoint.lower().startswith("https://") if ssl_enabled_raw == "" else ssl_enabled_raw not in {"false", "0", "no"}

for name, value in (
    ("DQ_S3_ENDPOINT/AWS_ENDPOINT_URL", endpoint),
    ("DQ_S3_ACCESS_KEY/AWS_ACCESS_KEY_ID", access_key),
    ("DQ_S3_SECRET_KEY/AWS_SECRET_ACCESS_KEY", secret_key),
):
    if not value:
        raise SystemExit(f"{name} is required to inspect AIStor materializations")

client = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    region_name=region,
    verify=verify,
)

scratch_dir = Path(tempfile.mkdtemp(prefix="dq-rulebuilder-materialization-count-"))
try:
    paginator = client.get_paginator("list_objects_v2")
    downloaded = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=key_prefix):
        for item in page.get("Contents") or []:
            object_key = item["Key"]
            file_name = Path(object_key).name
            if not file_name or file_name.startswith((".", "_")) or file_name.endswith(".crc"):
                continue
            relative_key = object_key[len(key_prefix):].lstrip("/")
            if not relative_key:
                continue
            target_path = scratch_dir / relative_key
            target_path.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, object_key, str(target_path))
            downloaded += 1

    if downloaded < 1:
        raise SystemExit(f"No parquet files were found under {output_uri!r}")

    spark = (
        SparkSession.builder.master("local[*]")
        .appName("dq-rulebuilder-materialization-count")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    try:
        dataframe = spark.read.parquet(str(scratch_dir))
        total_rows = int(dataframe.count())
        if column_name not in dataframe.columns:
            raise SystemExit(f"Column {column_name!r} is not present in materialized output {output_uri!r}")
        invalid_rows = int(dataframe.where(~F.col(column_name).rlike(regex_pattern)).count())
        print(json.dumps({"total_rows": total_rows, "invalid_rows": invalid_rows}, sort_keys=True))
    finally:
        spark.stop()
finally:
    shutil.rmtree(scratch_dir, ignore_errors=True)
PY
}

rewrite_custom_query_assertion_dsl_json() {
  local case_id="$1"
  local dsl_json="$2"

  case "$case_id" in
    correct_atm_cash_movement_matches_authoritative_transaction_total)
      printf '%s' "$dsl_json" | jq -c '
        .rule.measure.query = "SELECT transaction_id, amount FROM teller_machine_left_reconcile" |
        .rule.measure.comparison_data_source_name = "Transaction Source" |
        .rule.measure.comparison_query = "SELECT order_id AS transaction_id, total_amount AS amount FROM teller_machine_right_reconcile"
      '
      ;;
    reconcile_atm_cash_movement_matches_customer_transaction_total)
      printf '%s' "$dsl_json" | jq -c '
        .rule.measure.query = "SELECT amount FROM teller_machine_left_reconcile" |
        .rule.measure.comparison_data_source_name = "Transaction Source" |
        .rule.measure.comparison_query = "SELECT total_amount AS amount FROM teller_machine_right_reconcile"
      '
      ;;
    transfer_match_delivery_row_count_matches)
      printf '%s' "$dsl_json" | jq -c '
        .rule.measure.query = "SELECT transaction_id, row_count FROM transfer_match_delivery_rows_left" |
        .rule.measure.comparison_data_source_name = "Transaction Source" |
        .rule.measure.comparison_query = "SELECT order_id AS transaction_id, row_count FROM transfer_match_delivery_rows_right"
      '
      ;;
    transfer_match_delivery_note_hash_count_matches)
      printf '%s' "$dsl_json" | jq -c '
        .rule.measure.query = "SELECT transaction_id, file_hash, hash_count FROM transfer_match_delivery_note_left" |
        .rule.measure.comparison_data_source_name = "Transaction Source" |
        .rule.measure.comparison_query = "SELECT order_id AS transaction_id, target_file_hash AS file_hash, hash_count FROM transfer_match_delivery_note_right"
      '
      ;;
    join_consistency_customer_contact_email_and_actuality_align)
      printf '%s' "$dsl_json" | jq -c '
        .rule.measure.query = "SELECT customer_id, email, created_at FROM customer_contact_left_join_consistency" |
        .rule.measure.comparison_data_source_name = "Customer Source" |
        .rule.measure.comparison_query = "SELECT customer_id, email_address AS email, last_contacted AS created_at FROM customer_contact_right_join_consistency"
      '
      ;;
    *)
      printf '%s' "$dsl_json"
      ;;
  esac
}

run_case() {
  local case_json="$1"
  local case_id rule_kind version_id data_object_id dimension execution_shape rule_name description dsl_json
  case_id="$(printf '%s' "$case_json" | jq -r '.case_id')"
  rule_kind="$(printf '%s' "$case_json" | jq -r '.dsl.rule.kind')"
  version_id="$(printf '%s' "$case_json" | jq -r '.version_id')"
  data_object_id="$(printf '%s' "$case_json" | jq -r '.data_object_id')"
  dimension="$(printf '%s' "$case_json" | jq -r '.dimension')"
  execution_shape="$(printf '%s' "$case_json" | jq -r '.execution_shape // "single_object"')"
  if [[ "$rule_kind" == "custom_query_assertion" ]]; then
    execution_shape="single_object"
  fi
  dsl_json="$(printf '%s' "$case_json" | jq -c '.dsl')"
  if [[ "$rule_kind" == "custom_query_assertion" ]]; then
    dsl_json="$(rewrite_custom_query_assertion_dsl_json "$case_id" "$dsl_json")"
  fi
  rule_name="e2e-${RUN_STAMP}-${case_id}"
  description="${rule_kind} end-to-end lifecycle regression (${case_id})"

  info "$my_name" "Running case ${case_id} (${rule_kind})"

  local create_body
  create_body="$(printf '%s' "$case_json" | jq -c \
    --arg name "$rule_name" \
    --arg description "$description" \
    --arg dimension "$dimension" \
    --arg workspace_id "$DQ_RULE_E2E_WORKSPACE_ID" \
    --argjson dsl "$dsl_json" \
    '{
      name: $name,
      description: $description,
      dimension: $dimension,
      active: false,
      workspace_id: $workspace_id,
      dsl: $dsl
    }')"

  api_request POST "/rulebuilder/v1/rules" "$create_body"
  require_status 200 "Create rule for ${case_id}"
  local rule_id
  rule_id="$(printf '%s' "$API_BODY" | jq -r '.id // empty')"
  if [[ -z "$rule_id" ]]; then
    error "$my_name" "Create rule response missing id for ${case_id}"
    printf '%s\n' "$API_BODY" >&2
    exit 1
  fi

  if [[ "$rule_kind" != "custom_query_assertion" ]]; then
    local -a attribute_ids=()
    local attribute_name
    while IFS= read -r attribute_name; do
      attribute_ids+=("$(lookup_attribute_id "$version_id" "$attribute_name")")
    done < <(printf '%s' "$case_json" | jq -r '.assign_attribute_names[]')

    local attribute_ids_json
    attribute_ids_json="$(printf '%s\n' "${attribute_ids[@]}" | jq -R . | jq -s .)"
    local rule_attributes_body
    rule_attributes_body="$(jq -nc --arg rule_id "$rule_id" --argjson attribute_ids "$attribute_ids_json" '{entries: ($attribute_ids | map({ruleId: $rule_id, attributeId: .}))}')"

    api_request POST "/data-catalog/v1/rule-attributes" "$rule_attributes_body"
    require_status 200 "Assign attributes for ${case_id}"
  fi

  api_request POST "/rulebuilder/v1/rules/${rule_id}/validate"
  require_status 200 "Validate rule ${case_id}"
  local compiled_expression
  compiled_expression="$(printf '%s' "$API_BODY" | jq -r '.compiled_expression // empty')"
  if [[ "$rule_kind" != "custom_query_assertion" && -z "$compiled_expression" ]]; then
    error "$my_name" "Validation response missing compiled_expression for ${case_id}"
    printf '%s\n' "$API_BODY" >&2
    exit 1
  fi

  if [[ "$rule_kind" != "custom_query_assertion" ]]; then
    local start_test_body
    start_test_body="$(jq -nc --arg version_id "$version_id" --argjson sample_count "$DQ_RULE_E2E_TEST_SAMPLE_COUNT" '{versionId: $version_id, sampleCount: $sample_count}')"
    api_request POST "/rulebuilder/v1/rules/${rule_id}/test-runs/start" "$start_test_body"
    require_status 200 "Start generated-data test for ${case_id}"
    local proof_id
    proof_id="$(printf '%s' "$API_BODY" | jq -r '.id // empty')"
    if [[ -z "$proof_id" ]]; then
      error "$my_name" "Start test response missing proof id for ${case_id}"
      printf '%s\n' "$API_BODY" >&2
      exit 1
    fi

    local run_test_body
    run_test_body="$(jq -nc --arg version_id "$version_id" --arg proof_id "$proof_id" --argjson sample_count "$DQ_RULE_E2E_TEST_SAMPLE_COUNT" '{versionId: $version_id, sampleCount: $sample_count, proofId: $proof_id}')"
    api_request POST "/rulebuilder/v1/rules/${rule_id}/test-with-generated-data" "$run_test_body"
    require_status 200 "Run generated-data test for ${case_id}"
  fi

  local activation_data_object_id activation_version_id
  activation_data_object_id="$data_object_id"
  activation_version_id="$version_id"
  if [[ "$rule_kind" == "custom_query_assertion" ]]; then
    activation_data_object_id="$(db_query_tsv "SELECT data_object_id FROM data_object_versions WHERE id = $(sql_quote "$version_id")")"
    if [[ -z "$activation_data_object_id" ]]; then
      activation_data_object_id="$(db_query_tsv "SELECT id FROM data_objects_catalog WHERE name = 'Transaction' LIMIT 1")"
    fi
    if [[ -z "$activation_data_object_id" ]]; then
      error "$my_name" "data_object_version ${version_id} was not found while preparing the custom-query activation"
      exit 1
    fi
    activation_version_id="$(db_query_tsv "SELECT id FROM data_object_versions WHERE data_object_id = $(sql_quote "$activation_data_object_id") ORDER BY created_at DESC NULLS LAST, version DESC LIMIT 1")"
    if [[ -z "$activation_version_id" ]]; then
      error "$my_name" "No live data_object_versions row was found for data object ${activation_data_object_id} while preparing the custom-query activation"
      exit 1
    fi
  fi

  local approval_body
  approval_body="$(jq -nc --arg rule_id "$rule_id" --arg workspace_id "$DQ_RULE_E2E_WORKSPACE_ID" '{rule_id: $rule_id, workspace_id: $workspace_id, request_type: "activation", status: "pending"}')"
  api_request POST "/rulebuilder/v1/approvals" "$approval_body"
  require_status 200 "Create approval for ${case_id}"
  local approval_id
  approval_id="$(printf '%s' "$API_BODY" | jq -r '.id // empty')"
  if [[ -z "$approval_id" ]]; then
    error "$my_name" "Approval response missing id for ${case_id}"
    printf '%s\n' "$API_BODY" >&2
    exit 1
  fi

  api_request_as_approver PUT "/rulebuilder/v1/approvals/${approval_id}" '{"status":"approved"}'
  require_status 200 "Approve activation request for ${case_id}"

  local activate_body
  activate_body="$(printf '%s' "$case_json" | jq -c --arg data_object_id "$activation_data_object_id" --arg version_id "$activation_version_id" '{data_object_id: $data_object_id, data_object_version_ids: [$version_id], primary_key_fields: (.primary_key_fields // []), suite_version: 1}')"
  api_request POST "/rulebuilder/v1/rules/${rule_id}/activate" "$activate_body"
  require_status 200 "Activate rule ${case_id}"

  local adhoc_body
  if [[ "$execution_shape" == "join_pair" ]]; then
    api_request GET "/rulebuilder/v1/gx/suites/by-rule/${rule_id}?status=active&latestOnly=true"
    require_status 200 "Fetch GX suite for ${case_id}"

    local suite_execution_shape suite_output_uri suite_scope_json expected_scope_json
    suite_execution_shape="$(printf '%s' "$API_BODY" | jq -r '.[0].execution_contract.execution_shape // empty')"
    suite_output_uri="$(printf '%s' "$API_BODY" | jq -r '.[0].execution_contract.source_materialization.output_location // empty')"
    suite_scope_json="$(printf '%s' "$API_BODY" | jq -c '((.[0].resolved_execution_scope.data_object_version_ids // []) | sort)')"
    expected_scope_json="$(printf '%s' "$case_json" | jq -c '((.expected_suite_scope // []) | sort)')"

    if [[ "$suite_execution_shape" != "join_pair" ]]; then
      error "$my_name" "GX suite for ${case_id} did not publish as execution_shape=join_pair"
      printf '%s\n' "$API_BODY" >&2
      exit 1
    fi
    if [[ -z "$suite_output_uri" ]]; then
      error "$my_name" "GX suite for ${case_id} is missing source_materialization.output_location"
      printf '%s\n' "$API_BODY" >&2
      exit 1
    fi
    case "$suite_output_uri" in
      "s3://dq-landing-zone-${DQ_RULE_E2E_WORKSPACE_ID}/"*) ;;
      *)
        error "$my_name" "GX suite for ${case_id} published to unexpected landing-zone output_location=${suite_output_uri}"
        exit 1
        ;;
    esac
    if [[ "$suite_scope_json" != "$expected_scope_json" ]]; then
      error "$my_name" "GX suite for ${case_id} resolved unexpected execution scope"
      printf 'expected=%s\nactual=%s\n' "$expected_scope_json" "$suite_scope_json" >&2
      exit 1
    fi

    local source_json selected_attribute_names_json materialized_source_json source_version_id source_output_uri source_output_format previous_storage_row previous_storage_uri previous_storage_format source_mode source_role local_csv_path local_csv_transform
    while IFS= read -r source_json; do
      source_version_id="$(printf '%s' "$source_json" | jq -r '.version_id')"
      source_mode="$(printf '%s' "$source_json" | jq -r '.source_mode // "generated_materialization"')"
      source_role="$(printf '%s' "$source_json" | jq -r '.role // "source"')"
      if [[ "$source_mode" == "local_csv_parquet_stage" ]]; then
        local_csv_path="$(printf '%s' "$source_json" | jq -r '.local_csv_path // empty')"
        local_csv_transform="$(printf '%s' "$source_json" | jq -r '.local_csv_transform // empty')"
        if [[ -z "$local_csv_path" || -z "$local_csv_transform" ]]; then
          error "$my_name" "join_pair local_csv_parquet_stage source for ${case_id} is missing local_csv_path or local_csv_transform"
          printf '%s\n' "$source_json" >&2
          exit 1
        fi
        materialized_source_json="$(stage_local_csv_source \
          "$source_version_id" \
          "$local_csv_path" \
          "$local_csv_transform" \
          "$case_id" \
          "$source_role")"
      else
        selected_attribute_names_json="$(printf '%s' "$source_json" | jq -c '.selected_attribute_names // []')"
        materialized_source_json="$(materialize_test_source \
          "$source_version_id" \
          "$selected_attribute_names_json" \
          "$case_id" \
          "$source_role")"
      fi
      source_output_uri="$(printf '%s' "$materialized_source_json" | jq -r '.output_uri')"
      source_output_format="$(printf '%s' "$materialized_source_json" | jq -r '.output_format')"

      if [[ "$case_id" == "regex_customer_email_format_high_invalid_rows" ]]; then
        local high_invalid_rows_json high_invalid_rows total_rows
        high_invalid_rows_json="$(count_rows_in_materialized_parquet "$source_output_uri" "email" "$(printf '%s' "$case_json" | jq -r '.check_type_params.pattern')")"
        total_rows="$(printf '%s' "$high_invalid_rows_json" | jq -r '.total_rows')"
        high_invalid_rows="$(printf '%s' "$high_invalid_rows_json" | jq -r '.invalid_rows')"
        if [[ -z "$high_invalid_rows" || "$high_invalid_rows" -le 200 ]]; then
          error "$my_name" "AIStor materialization for ${case_id} only wrote ${high_invalid_rows:-<unknown>} invalid rows; expected more than 200"
          printf '%s\n' "$high_invalid_rows_json" >&2
          exit 1
        fi
        info "$my_name" "Validated AIStor materialization for ${case_id}: total_rows=${total_rows}, invalid_rows=${high_invalid_rows}"
      fi

      previous_storage_row="$(db_query_tsv "SELECT COALESCE(storage_uri, ''), COALESCE(storage_format, '') FROM data_object_versions WHERE id = $(sql_quote "$source_version_id")")"
      if [[ -z "$previous_storage_row" ]]; then
        error "$my_name" "data_object_version ${source_version_id} was not found while bootstrapping join_pair storage metadata"
        exit 1
      fi
      if [[ "$previous_storage_row" == *$'\t'* ]]; then
        previous_storage_uri="${previous_storage_row%%$'\t'*}"
        previous_storage_format="${previous_storage_row#*$'\t'}"
      else
        previous_storage_uri="$previous_storage_row"
        previous_storage_format=""
      fi
      queue_restore_version_storage "$source_version_id" "$previous_storage_uri" "$previous_storage_format"
      db_exec_sql "UPDATE data_object_versions SET storage_uri = $(sql_nullable "$source_output_uri"), storage_format = $(sql_nullable "$source_output_format") WHERE id = $(sql_quote "$source_version_id");"
    done < <(printf '%s' "$case_json" | jq -c '.source_materializations[]')

    adhoc_body="$(jq -nc \
      --arg version_id "$version_id" \
      --arg rule_id "$rule_id" \
      '{
        data_object_version_id: $version_id,
        target_data_object_version_ids: [$version_id],
        rule_ids: [$rule_id]
      }')"
  else
    local materialization_json output_uri output_format
    local effective_data_object_id effective_version_id
    effective_data_object_id="$activation_data_object_id"
    effective_version_id="$activation_version_id"
    if [[ "$rule_kind" == "custom_query_assertion" ]]; then
      local custom_left_csv_path custom_left_transform
      custom_left_csv_path="$(printf '%s' "$case_json" | jq -r '.source_materializations[] | select(.role == "left") | .local_csv_path' | head -n 1)"
      custom_left_transform="$(printf '%s' "$case_json" | jq -r '.source_materializations[] | select(.role == "left") | .local_csv_transform' | head -n 1)"
      if [[ -z "$custom_left_csv_path" || -z "$custom_left_transform" ]]; then
        error "$my_name" "custom_query_assertion case ${case_id} is missing left source materialization details"
        exit 1
      fi
      materialization_json="$(stage_local_csv_source \
        "$activation_version_id" \
        "$custom_left_csv_path" \
        "$custom_left_transform" \
        "$case_id" \
        "primary")"
    else
      materialization_json="$(materialize_test_source \
        "$version_id" \
        "$(printf '%s' "$case_json" | jq -c '.materialize_attribute_names')" \
        "$case_id" \
        "primary")"
    fi
    output_uri="$(printf '%s' "$materialization_json" | jq -r '.output_uri')"
    output_format="$(printf '%s' "$materialization_json" | jq -r '.output_format')"

    if [[ "$rule_kind" == "custom_query_assertion" ]]; then
      local data_delivery_id attributes_count
      data_delivery_id="td-${RUN_STAMP}-$(sanitize_identifier "$case_id")-primary"
      attributes_count="$(printf '%s' "$case_json" | jq -r '.assign_attribute_names | length')"
      register_materialized_delivery_note \
        "$data_delivery_id" \
        "$activation_data_object_id" \
        "$activation_version_id" \
        "$output_uri" \
        "$output_format" \
        "$attributes_count" \
        "$case_id"
    fi

    adhoc_body="$(jq -nc \
      --arg version_id "$effective_version_id" \
      --arg rule_id "$rule_id" \
      --arg output_uri "$output_uri" \
      --arg output_format "$output_format" \
      '{
        data_object_version_id: $version_id,
        target_data_object_version_ids: [$version_id],
        rule_ids: [$rule_id],
        source_override_uri: $output_uri,
        source_override_format: $output_format
      }')"
  fi

  api_request POST "/rulebuilder/v1/gx/runs/adhoc" "$adhoc_body"
  require_status 202 "Create ad-hoc GX run for ${case_id}"
  local run_id
  run_id="$(printf '%s' "$API_BODY" | jq -r '.[0].run_id // empty')"
  if [[ -z "$run_id" ]]; then
    error "$my_name" "Ad-hoc GX enqueue response missing run_id for ${case_id}"
    printf '%s\n' "$API_BODY" >&2
    exit 1
  fi

  poll_gx_run "$run_id"
  local storage_uri
  storage_uri="$(printf '%s' "$API_BODY" | jq -r '(.result_summary.results // [] | map(.storage_uri // empty) | map(select(length > 0)) | .[0] // empty)')"
  if [[ "$execution_shape" == "join_pair" ]]; then
    local pre_dispatch_phase expected_join_pair_output_prefix
    pre_dispatch_phase="$(printf '%s' "$API_BODY" | jq -r '.handoff_payload.status_details.pre_dispatch_phase // .status_details.pre_dispatch_phase // empty')"
    expected_join_pair_output_prefix="$(printf '%s' "$API_BODY" | jq -r '.execution_contract.source_materialization.output_location // empty')"
    if [[ "$pre_dispatch_phase" != "join_pair_materialization" ]]; then
      error "$my_name" "GX run ${run_id} for ${case_id} did not retain pre_dispatch_phase=join_pair_materialization"
      printf '%s\n' "$API_BODY" >&2
      exit 1
    fi
    if [[ -z "$expected_join_pair_output_prefix" ]]; then
      error "$my_name" "GX run ${run_id} for ${case_id} is missing execution_contract.source_materialization.output_location"
      printf '%s\n' "$API_BODY" >&2
      exit 1
    fi
    if [[ -z "$storage_uri" ]]; then
      error "$my_name" "GX run ${run_id} for ${case_id} did not report a joined storage_uri"
      printf '%s\n' "$API_BODY" >&2
      exit 1
    fi
    case "$storage_uri" in
      "${expected_join_pair_output_prefix}"*) ;;
      *)
        error "$my_name" "GX run ${run_id} for ${case_id} reported storage_uri=${storage_uri}, expected prefix ${expected_join_pair_output_prefix}"
        printf '%s\n' "$API_BODY" >&2
        exit 1
        ;;
    esac
  elif [[ -n "$storage_uri" && "$storage_uri" != "$output_uri" ]]; then
    error "$my_name" "GX run ${run_id} reported storage_uri=${storage_uri}, expected ${output_uri}"
    printf '%s\n' "$API_BODY" >&2
    exit 1
  fi

  CASE_PASSED_COUNT=$((CASE_PASSED_COUNT + 1))
  info "$my_name" "Case ${case_id} passed"
}

reap_parallel_case_jobs() {
  local next_pids=()
  local next_ids=()
  local next_logs=()
  local idx pid case_id log_file exit_code

  for idx in "${!CASE_JOB_PIDS[@]}"; do
    pid="${CASE_JOB_PIDS[$idx]}"
    case_id="${CASE_JOB_IDS[$idx]}"
    log_file="${CASE_JOB_LOGS[$idx]}"

    if kill -0 "$pid" >/dev/null 2>&1; then
      next_pids+=("$pid")
      next_ids+=("$case_id")
      next_logs+=("$log_file")
      continue
    fi

    if wait "$pid"; then
      exit_code=0
    else
      exit_code=$?
    fi

    if [[ -f "$log_file" ]]; then
      cat "$log_file"
      rm -f "$log_file"
    fi

    if [[ "$exit_code" -eq 0 ]]; then
      CASE_PASSED_COUNT=$((CASE_PASSED_COUNT + 1))
      info "$my_name" "Parallel case ${case_id} completed successfully"
    else
      PARALLEL_FAILURE=1
      error "$my_name" "Parallel case ${case_id} failed with exit code ${exit_code}"
    fi
  done

  CASE_JOB_PIDS=("${next_pids[@]}")
  CASE_JOB_IDS=("${next_ids[@]}")
  CASE_JOB_LOGS=("${next_logs[@]}")
}

run_cases_sequential() {
  mint_token

  while IFS= read -r case_json; do
    run_case "$case_json"
  done < <(printf '%s' "$FILTERED_SUPPORTED_CASES_JSON" | jq -c '.[]')
}

run_cases_parallel() {
  local parallelism="$PARALLELISM"
  local selected_count case_json case_id child_log

  selected_count="$(printf '%s' "$FILTERED_SUPPORTED_CASES_JSON" | jq 'length')"
  if [[ "$parallelism" -le 1 || "$selected_count" -le 1 ]]; then
    run_cases_sequential
    return 0
  fi

  PARALLEL_LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dq-rule-e2e-parallel.XXXXXX")"
  info "$my_name" "Executing ${selected_count} selected cases with bounded case parallelism=${parallelism}; Spark-backed work will queue in Redis"

  while IFS= read -r case_json; do
    case_id="$(printf '%s' "$case_json" | jq -r '.case_id')"

    while [[ "${#CASE_JOB_PIDS[@]}" -ge "$parallelism" ]]; do
      reap_parallel_case_jobs
      if [[ "${#CASE_JOB_PIDS[@]}" -ge "$parallelism" ]]; then
        sleep 1
      fi
    done

    child_log="${PARALLEL_LOG_DIR}/$(sanitize_identifier "$case_id").log"
    info "$my_name" "Launching parallel case ${case_id}"
    "$0" --parallelism 1 --case-ids "$case_id" >"$child_log" 2>&1 &
    CASE_JOB_PIDS+=("$!")
    CASE_JOB_IDS+=("$case_id")
    CASE_JOB_LOGS+=("$child_log")
  done < <(printf '%s' "$FILTERED_SUPPORTED_CASES_JSON" | jq -c '.[]')

  while [[ "${#CASE_JOB_PIDS[@]}" -gt 0 ]]; do
    reap_parallel_case_jobs
    if [[ "${#CASE_JOB_PIDS[@]}" -gt 0 ]]; then
      sleep 1
    fi
  done

  if [[ "$PARALLEL_FAILURE" -ne 0 ]]; then
    exit 1
  fi
}

if [[ -n "$RULE_KINDS_FILTER_CSV" ]]; then
  info "$my_name" "Applying rule kind filter: ${RULE_KINDS_FILTER_CSV}"
fi
if [[ -n "$DIMENSIONS_FILTER_CSV" ]]; then
  info "$my_name" "Applying dimension filter: ${DIMENSIONS_FILTER_CSV}"
fi
if [[ -n "$CASE_IDS_FILTER_CSV" ]]; then
  info "$my_name" "Applying case_id filter: ${CASE_IDS_FILTER_CSV}"
fi
info "$my_name" "Case parallelism: ${PARALLELISM}"

info "$my_name" "Supported GX lifecycle cases selected: $(printf '%s' "$FILTERED_SUPPORTED_CASES_JSON" | jq 'length')"
print_unsupported_matrix
if [[ "$DQ_RULE_E2E_REQUIRE_ALL_RULE_KINDS" == "true" ]]; then
  if [[ "$(printf '%s' "$FILTERED_UNSUPPORTED_RULE_KINDS_JSON" | jq 'length')" -gt 0 ]]; then
    error "$my_name" "Full all-rule-kind coverage is not currently possible for the requested selection; refusing to continue"
    exit 1
  fi
fi

run_cases_parallel

info "$my_name" "PASS: ${CASE_PASSED_COUNT} selected end-to-end GX lifecycle cases completed successfully"