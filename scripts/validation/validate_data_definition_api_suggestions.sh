#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate data-definition API suggestions for every attribute in one data object version.
#
# What it does:
# - Requires the API, Kong, Redis, and dq-llm services to already be running.
# - Uses a seeded user token through the shared auth helper.
# - Accepts a data object version id as a command-line argument, or discovers one when omitted.
# - Queues one data-definition task with every attribute for that data object version.
# - Waits for the task event stream and verifies every selected attribute has a governed business term suggestion.
#
# validate: groups=api,regression
# Version: 1.6
# Last modified: 2026-06-01
# Changelog:
# - 1.5 (2026-06-01): On event stream timeout, fetches request status to distinguish still-running tasks from terminal outcomes.
# - 1.4 (2026-06-01): Improved health wait diagnostics to report curl timeout and transport failures explicitly.
# - 1.3 (2026-05-26): Subscribed to asynchronous task events instead of polling status.
# - 1.2 (2026-05-26): Expected HTTP 202 Accepted for asynchronous data-definition task submission.
# - 1.1 (2026-05-26): Added --env/--env-file handling and command-line version selection.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"

my_name="validate_data_definition_api_suggestions.sh"
work_dir="$ROOT_DIR/tmp/data-definition-api-validation"
response_file="$work_dir/${my_name}.$$.response"
headers_file="$work_dir/${my_name}.$$.headers"
events_file="$work_dir/${my_name}.$$.events"
data_object_version_id=""
option_workspace_id=""
option_domain_name=""
option_source_system=""
option_steward_name=""
option_max_discovery_attributes=""
option_event_timeout_seconds=""

mkdir -p "$work_dir"

cleanup() {
  rm -f "$response_file" "$headers_file" "$events_file"
}
trap cleanup EXIT

print_usage() {
  printf '%s\n' \
    "Usage: scripts/validate_data_definition_api_suggestions.sh [OPTIONS] [DATA_OBJECT_VERSION_ID]" \
    "" \
    "Canonical env options:" \
    "  --env dev|test|prod          Use .env.dev.local, .env.test.local, or .env.prod.local" \
    "  --env-file PATH              Use an explicit env file" \
    "" \
    "Validation options:" \
    "  --version-id ID              Validate this data object version id" \
    "  --workspace-id ID            Override workspace id when the attribute response lacks one" \
    "  --domain-name NAME           Override data-definition primary domain" \
    "  --source-system NAME         Override data-definition source system" \
    "  --steward-name NAME          Override steward name" \
    "  --max-discovery-attributes N Limit auto-discovery to versions with at most N attributes" \
    "  --event-timeout-seconds N    Maximum seconds to wait for task events" \
    "  -h, --help                   Show this help"
}

parse_script_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --version-id)
        if [[ $# -lt 2 ]]; then
          error "$my_name" "--version-id requires a value"
          exit 2
        fi
        data_object_version_id="$2"
        shift 2
        ;;
      --workspace-id)
        if [[ $# -lt 2 ]]; then
          error "$my_name" "--workspace-id requires a value"
          exit 2
        fi
        option_workspace_id="$2"
        shift 2
        ;;
      --domain-name)
        if [[ $# -lt 2 ]]; then
          error "$my_name" "--domain-name requires a value"
          exit 2
        fi
        option_domain_name="$2"
        shift 2
        ;;
      --source-system)
        if [[ $# -lt 2 ]]; then
          error "$my_name" "--source-system requires a value"
          exit 2
        fi
        option_source_system="$2"
        shift 2
        ;;
      --steward-name)
        if [[ $# -lt 2 ]]; then
          error "$my_name" "--steward-name requires a value"
          exit 2
        fi
        option_steward_name="$2"
        shift 2
        ;;
      --max-discovery-attributes)
        if [[ $# -lt 2 ]]; then
          error "$my_name" "--max-discovery-attributes requires a value"
          exit 2
        fi
        option_max_discovery_attributes="$2"
        shift 2
        ;;
      --event-timeout-seconds)
        if [[ $# -lt 2 ]]; then
          error "$my_name" "--event-timeout-seconds requires a value"
          exit 2
        fi
        option_event_timeout_seconds="$2"
        shift 2
        ;;
      -h|--help)
        print_usage
        exit 0
        ;;
      --*)
        error "$my_name" "Unknown option: $1"
        print_usage >&2
        exit 2
        ;;
      *)
        if [[ -n "$data_object_version_id" ]]; then
          error "$my_name" "Only one DATA_OBJECT_VERSION_ID argument is supported"
          print_usage >&2
          exit 2
        fi
        data_object_version_id="$1"
        shift
        ;;
    esac
  done
}

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  exit 2
fi
set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

parse_script_args "$@"

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 2
fi

export ROOT_ENV_FILE
if ! source_selected_root_env_file; then
  exit 1
fi

if [[ -n "$option_workspace_id" ]]; then
  DQ_DATA_DEFINITION_WORKSPACE_ID="$option_workspace_id"
  export DQ_DATA_DEFINITION_WORKSPACE_ID
fi
if [[ -n "$option_domain_name" ]]; then
  DQ_DATA_DEFINITION_DOMAIN_NAME="$option_domain_name"
  export DQ_DATA_DEFINITION_DOMAIN_NAME
fi
if [[ -n "$option_source_system" ]]; then
  DQ_DATA_DEFINITION_SOURCE_SYSTEM="$option_source_system"
  export DQ_DATA_DEFINITION_SOURCE_SYSTEM
fi
if [[ -n "$option_steward_name" ]]; then
  DQ_DATA_DEFINITION_STEWARD_NAME="$option_steward_name"
  export DQ_DATA_DEFINITION_STEWARD_NAME
fi
if [[ -n "$option_max_discovery_attributes" ]]; then
  DQ_DATA_DEFINITION_MAX_DISCOVERY_ATTRIBUTES="$option_max_discovery_attributes"
  export DQ_DATA_DEFINITION_MAX_DISCOVERY_ATTRIBUTES
fi
if [[ -n "$option_event_timeout_seconds" ]]; then
  DQ_DATA_DEFINITION_EVENT_TIMEOUT_SECONDS="$option_event_timeout_seconds"
  export DQ_DATA_DEFINITION_EVENT_TIMEOUT_SECONDS
fi

info "$my_name" "Environment: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE")"

dq_source_seeded_user_credentials --env-file "$ROOT_ENV_FILE" --quiet

REQUESTER_EMAIL="${KEYCLOAK_JACCLOUD_USERNAME:?KEYCLOAK_JACCLOUD_USERNAME must be set}"
REQUESTER_PASSWORD="${KEYCLOAK_JACCLOUD_PASSWORD:?KEYCLOAK_JACCLOUD_PASSWORD must be set}"

: "${KONG_PUBLIC_URL:?KONG_PUBLIC_URL must be set to the public Kong URL used by the UI}"
: "${SSO_PUBLIC_ISSUER_URL:?SSO_PUBLIC_ISSUER_URL must be set}"
: "${VITE_KEYCLOAK_CLIENT_ID:?VITE_KEYCLOAK_CLIENT_ID must be set}"

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [[ -f "$KONG_CA_CERT" && -z "${CURL_CA_BUNDLE:-}" ]]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: ${cmd}"
    exit 2
  fi
}

require_running_service() {
  local service_name="$1"
  local container_name

  container_name="$(docker ps --filter "label=com.docker.compose.service=${service_name}" --filter 'status=running' --format '{{.Names}}' | head -1)"
  if [[ -z "$container_name" ]]; then
    error "$my_name" "${service_name} must already be running; start the stack separately before running this validation"
    exit 1
  fi
}

wait_for_http_200() {
  local url="$1"
  local label="$2"
  local attempt
  local code
  local curl_rc
  local status_note

  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    set +e
    code="$(curl -sS --connect-timeout 10 --max-time 10 -o /dev/null -w '%{http_code}' "$url")"
    curl_rc=$?
    set -e

    if [[ "$curl_rc" -eq 0 && "$code" == "200" ]]; then
      return 0
    fi

    if [[ "$curl_rc" -eq 28 ]]; then
      status_note="timeout after 10s"
    elif [[ "$curl_rc" -ne 0 ]]; then
      status_note="curl rc=${curl_rc}"
    else
      status_note="http=${code:-unknown}"
    fi

    info "$my_name" "Waiting for ${label} to report HTTP 200 (${status_note}; current=${code:-000})"
    sleep 2
  done

  error "$my_name" "${label} did not report HTTP 200 at ${url}"
  exit 1
}

api_request_with_token() {
  local token="$1"
  local method="$2"
  local endpoint="$3"
  local body="${4-}"
  local response_code
  local curl_rc

  rm -f "$response_file" "$headers_file"

  set +e
  if [[ -n "$body" ]]; then
    response_code="$(curl -sS \
      -D "$headers_file" \
      -o "$response_file" \
      -w '%{http_code}' \
      -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" \
      -H "Authorization: Bearer ${token}" \
      -H 'Content-Type: application/json' \
      -d "$body")"
  else
    response_code="$(curl -sS \
      -D "$headers_file" \
      -o "$response_file" \
      -w '%{http_code}' \
      -X "$method" "${KONG_PUBLIC_URL%/}${endpoint}" \
      -H "Authorization: Bearer ${token}")"
  fi
  curl_rc=$?
  set -e

  if [[ "$curl_rc" -ne 0 ]]; then
    error "$my_name" "HTTP ${method} ${endpoint} failed with rc=${curl_rc}"
    cat "$headers_file" >&2 || true
    cat "$response_file" >&2 || true
    exit "$curl_rc"
  fi

  HTTP_CODE="$response_code"
  HTTP_BODY="$(cat "$response_file")"
}

collect_attributes_for_version() {
  local version_id="$1"
  local page=1
  local has_next="true"
  local collected="[]"

  while [[ "$has_next" == "true" ]]; do
    api_request_with_token "$ACCESS_TOKEN" GET "/data-catalog/v1/attributes-catalog?versionId=${version_id}&page=${page}&limit=100"
    if [[ "$HTTP_CODE" != "200" ]]; then
      error "$my_name" "GET attributes for version ${version_id} returned HTTP ${HTTP_CODE}"
      printf '%s\n' "$HTTP_BODY" >&2
      exit 1
    fi

    collected="$(jq -c --argjson existing "$collected" '$existing + [.data[]?]' <<<"$HTTP_BODY")"
    has_next="$(jq -r '.pagination.has_next // false' <<<"$HTTP_BODY")"
    if [[ "$has_next" != "true" ]]; then
      break
    fi
    page=$((page + 1))
  done

  printf '%s\n' "$collected"
}

find_data_object_version_with_attributes() {
  local max_discovery_attributes="${DQ_DATA_DEFINITION_MAX_DISCOVERY_ATTRIBUTES:-12}"
  local page=1
  local has_next="true"
  local page_body
  local version_id
  local attributes_json
  local attribute_count

  if [[ -n "$data_object_version_id" ]]; then
    printf '%s\n' "$data_object_version_id"
    return 0
  fi

  while [[ "$has_next" == "true" ]]; do
    api_request_with_token "$ACCESS_TOKEN" GET "/data-catalog/v1/data-object-versions?page=${page}&limit=100"
    if [[ "$HTTP_CODE" != "200" ]]; then
      error "$my_name" "GET /data-catalog/v1/data-object-versions?page=${page}&limit=100 returned HTTP ${HTTP_CODE}"
      printf '%s\n' "$HTTP_BODY" >&2
      exit 1
    fi

    page_body="$HTTP_BODY"
    while IFS= read -r version_id; do
      [[ -z "$version_id" ]] && continue
      attributes_json="$(collect_attributes_for_version "$version_id")"
      attribute_count="$(jq -r 'length' <<<"$attributes_json")"
      if [[ "$attribute_count" -gt 0 && "$attribute_count" -le "$max_discovery_attributes" ]]; then
        printf '%s\n' "$version_id"
        return 0
      fi
    done <<<"$(jq -r '.data[]?.id // empty' <<<"$page_body")"

    has_next="$(jq -r '.pagination.has_next // false' <<<"$page_body")"
    if [[ "$has_next" != "true" ]]; then
      break
    fi
    page=$((page + 1))
  done

  error "$my_name" "Could not find a data object version with 1-${max_discovery_attributes} attributes; pass DATA_OBJECT_VERSION_ID or --version-id to validate a specific version"
  exit 1
}

build_data_definition_payload() {
  local version_id="$1"
  local attribute_ids_json="$2"
  local workspace_id="$3"
  local run_token="$4"
  local domain_name="${DQ_DATA_DEFINITION_DOMAIN_NAME:-}"
  local source_system="${DQ_DATA_DEFINITION_SOURCE_SYSTEM:-}"
  local steward_name="${DQ_DATA_DEFINITION_STEWARD_NAME:-Data Definition Validation Steward}"

  jq -nc \
    --arg current_workspace_id "$workspace_id" \
    --arg version_id "$version_id" \
    --arg user_input "Validation run ${run_token}: generate governed business terms for every selected attribute." \
    --arg steward_name "$steward_name" \
    --arg board_name "Data Definition Board" \
    --arg glossary_name "validation_data_definition_terms" \
    --arg glossary_display_name "Validation Data Definition Terms" \
    --arg domain_name "$domain_name" \
    --arg source_system "$source_system" \
    --argjson selected_attribute_ids "$attribute_ids_json" \
    '{
      current_workspace_id: $current_workspace_id,
      version_id: $version_id,
      selected_attribute_ids: $selected_attribute_ids,
      user_input: $user_input,
      policies: [
        "Guidelines for Definitions of Business Terms v1.0",
        "BCBS 239 traceability, accuracy, completeness, governance, and auditability"
      ],
      context_documents: [
        {
          document_type: "policy",
          name: "Guidelines for Definitions of Business Terms",
          content: "Definitions must be canonical English, one entry per concept, non-circular, source-referenced, domain-owned, and policy-linked.",
          source_uri: "urn:dq-made-easy:policy:business-term-definition-guidelines:v1"
        }
      ],
      steward_name: $steward_name,
      board_name: $board_name,
      glossary_name: $glossary_name,
      glossary_display_name: $glossary_display_name,
      auto_import: false
    }
    + (if $domain_name == "" then {} else {domain_name: $domain_name} end)
    + (if $source_system == "" then {} else {source_system: $source_system} end)'
}

assert_completed_result_has_terms_for_all_attributes() {
  local expected_attribute_ids_json="$1"
  local status_body="$2"

  if ! jq -e --argjson expected_ids "$expected_attribute_ids_json" '
    (.request.status == "completed") and
    (.request.result.registry_contract.definitions // []) as $definitions |
    ($definitions | length) == ($expected_ids | length) and
    all($expected_ids[]; . as $expected_id |
      any($definitions[];
        (.target_id == $expected_id) and
        ((.definition_name // "") | length > 0) and
        ((.business_definition // "") | test("^(A|An)\\s+")) and
        ((.concept_key // .definition_id // "") | length > 0) and
        ((.primary_domain // "") | length > 0) and
        ((.definition_owner // "") | length > 0) and
        ((.source_references // []) | type == "array" and length > 0) and
        ((.policy_documents // []) | type == "array" and length > 0) and
        ((.homonym_context.primary_domain // "") | length > 0) and
        ((.homonym_context.object_class // "") | length > 0) and
        ((.homonym_context.property // "") | length > 0)
      )
    )
  ' <<<"$status_body" >/dev/null; then
    error "$my_name" "Completed data-definition result did not include governed business term suggestions for every selected attribute"
    printf '%s\n' "$status_body" | jq '{request: {request_id: .request.request_id, status: .request.status, error_message: .request.error_message, selected_attribute_ids: .request.selected_attribute_ids}, definitions: (.request.result.registry_contract.definitions // [])}' >&2 || printf '%s\n' "$status_body" >&2
    exit 1
  fi
}

resolve_events_url() {
  local events_url="$1"
  case "$events_url" in
    http://*|https://*)
      printf '%s\n' "$events_url"
      ;;
    /*)
      printf '%s%s\n' "${KONG_PUBLIC_URL%/}" "$events_url"
      ;;
    *)
      error "$my_name" "Data-definition task creation returned unsupported events_url: ${events_url}"
      exit 1
      ;;
  esac
}

data_lines_to_json() {
  awk '
    /^data: / { print substr($0, 7); next }
    /^data:/ { print substr($0, 6); next }
  ' "$1"
}

wait_for_terminal_data_definition_event() {
  local events_url="$1"
  local request_id="$2"
  local event_timeout_seconds="${DQ_DATA_DEFINITION_EVENT_TIMEOUT_SECONDS:-300}"
  local response_code
  local curl_rc
  local terminal_payload

  rm -f "$events_file" "$headers_file"
  info "$my_name" "Subscribing to data-definition task events for ${request_id}"

  set +e
  response_code="$(curl -sS -N \
    -D "$headers_file" \
    -o "$events_file" \
    -w '%{http_code}' \
    --connect-timeout 10 \
    --max-time "$event_timeout_seconds" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H 'Accept: text/event-stream' \
    "$events_url")"
  curl_rc=$?
  set -e

  if [[ "$curl_rc" -ne 0 ]]; then
    if [[ "$curl_rc" -eq 28 ]]; then
      info "$my_name" "Data-definition task events timed out after ${event_timeout_seconds}s; checking current request status for ${request_id}"
      api_request_with_token "$ACCESS_TOKEN" GET "/data-catalog/v1/data-definition-tasks/${request_id}"
      if [[ "$HTTP_CODE" == "200" ]]; then
        status_body="$HTTP_BODY"
        task_status="$(jq -r '.request.status // empty' <<<"$status_body")"
        case "$task_status" in
          completed)
            info "$my_name" "Data-definition task ${request_id} reached completed status after stream timeout"
            return 0
            ;;
          failed)
            error "$my_name" "Data-definition task ${request_id} reached failed status after stream timeout"
            printf '%s\n' "$status_body" | jq '{request_id: .request.request_id, status: .request.status, error_message: .request.error_message}' >&2 || printf '%s\n' "$status_body" >&2
            exit 1
            ;;
          pending|started)
            error "$my_name" "Data-definition task ${request_id} is still ${task_status} after ${event_timeout_seconds}s"
            printf '%s\n' "$status_body" | jq '{request_id: .request.request_id, status: .request.status, requested_at: .request.requested_at, started_at: .request.started_at, completed_at: .request.completed_at, error_message: .request.error_message}' >&2 || printf '%s\n' "$status_body" >&2
            exit 124
            ;;
          *)
            error "$my_name" "Data-definition task ${request_id} returned unknown status '${task_status}' after stream timeout"
            printf '%s\n' "$status_body" >&2
            exit 1
            ;;
        esac
      fi

      error "$my_name" "Data-definition task status lookup failed with HTTP ${HTTP_CODE} after event stream timeout"
      printf '%s\n' "$HTTP_BODY" >&2
      exit 1
    fi

    error "$my_name" "Data-definition task event stream failed with rc=${curl_rc} after waiting up to ${event_timeout_seconds}s"
    cat "$headers_file" >&2 || true
    cat "$events_file" >&2 || true
    exit "$curl_rc"
  fi

  if [[ "$response_code" != "200" ]]; then
    error "$my_name" "Data-definition task event stream returned HTTP ${response_code}"
    cat "$headers_file" >&2 || true
    cat "$events_file" >&2 || true
    exit 1
  fi

  terminal_payload="$(data_lines_to_json "$events_file" | jq -sc 'map(select((.request.status // .status // "") as $status | $status == "completed" or $status == "failed")) | last // empty')"
  if [[ -z "$terminal_payload" ]]; then
    error "$my_name" "Data-definition task event stream ended without a terminal completed or failed event"
    cat "$events_file" >&2 || true
    exit 1
  fi

  task_status="$(jq -r '.request.status // .status // empty' <<<"$terminal_payload")"
  status_body="$(jq -c '{success: true, request: .request}' <<<"$terminal_payload")"
}

require_cmd docker
require_cmd curl
require_cmd jq
require_cmd awk

for service_name in api kong redis dq-llm; do
  require_running_service "$service_name"
done

wait_for_http_200 "${KONG_PUBLIC_URL%/}/health" "api health"

DQ_LLM_PUBLIC_URL="${DQ_LLM_PUBLIC_URL:-http://${DQ_LLM_HOST_BIND:-127.0.0.1}:${DQ_LLM_HOST_PORT:-8123}}"
wait_for_http_200 "${DQ_LLM_PUBLIC_URL%/}/health" "dq-llm health"

TOKEN_ENDPOINT="${SSO_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"
ACCESS_TOKEN="$(dq_keycloak_password_grant_access_token "$TOKEN_ENDPOINT" "$VITE_KEYCLOAK_CLIENT_ID" "$REQUESTER_EMAIL" "$REQUESTER_PASSWORD")"

run_token="$(date -u +%Y%m%d%H%M%S)-${RANDOM}${RANDOM}"
version_id="$(find_data_object_version_with_attributes)"
attributes_json="$(collect_attributes_for_version "$version_id")"
attribute_ids_json="$(jq -c '[.[] | select(.id != null) | .id]' <<<"$attributes_json")"
attribute_count="$(jq -r 'length' <<<"$attribute_ids_json")"

if [[ "$attribute_count" -eq 0 ]]; then
  error "$my_name" "Data object version ${version_id} has no attributes to validate"
  exit 1
fi

workspace_id="${DQ_DATA_DEFINITION_WORKSPACE_ID:-}"
if [[ -z "$workspace_id" ]]; then
  workspace_id="$(jq -r '[.[]?.workspace_id // empty][0] // empty' <<<"$attributes_json")"
fi
if [[ -z "$workspace_id" ]]; then
  workspace_id="retail-banking"
fi

info "$my_name" "Submitting data-definition validation task for version ${version_id} with ${attribute_count} attributes"
create_payload="$(build_data_definition_payload "$version_id" "$attribute_ids_json" "$workspace_id" "$run_token")"

api_request_with_token "$ACCESS_TOKEN" POST "/data-catalog/v1/data-definition-tasks" "$create_payload"
if [[ "$HTTP_CODE" != "202" ]]; then
  error "$my_name" "Data-definition task creation returned HTTP ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

if [[ "$(jq -r '.success // false' <<<"$HTTP_BODY")" != "true" ]]; then
  error "$my_name" "Data-definition task creation did not report success"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

request_id="$(jq -r '.request_id // empty' <<<"$HTTP_BODY")"
if [[ -z "$request_id" ]]; then
  error "$my_name" "Data-definition task creation did not return request_id"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

events_url="$(jq -r '.events_url // empty' <<<"$HTTP_BODY")"
if [[ -z "$events_url" ]]; then
  error "$my_name" "Data-definition task creation did not return events_url"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

status_body=""
task_status=""
wait_for_terminal_data_definition_event "$(resolve_events_url "$events_url")" "$request_id"

if [[ "$task_status" == "failed" ]]; then
  error "$my_name" "Data-definition task ${request_id} failed"
  printf '%s\n' "$status_body" | jq '{request_id: .request.request_id, status: .request.status, error_message: .request.error_message}' >&2 || printf '%s\n' "$status_body" >&2
  exit 1
fi

if [[ "$task_status" != "completed" ]]; then
  error "$my_name" "Data-definition task ${request_id} did not emit a completed event"
  printf '%s\n' "$status_body" >&2
  exit 1
fi

assert_completed_result_has_terms_for_all_attributes "$attribute_ids_json" "$status_body"

definition_count="$(jq -r '.request.result.registry_contract.definitions | length' <<<"$status_body")"
info "$my_name" "Final data-definition evidence"
info "$my_name" "- request_id=${request_id}"
info "$my_name" "- version_id=${version_id}"
info "$my_name" "- selected_attributes=${attribute_count}"
info "$my_name" "- generated_definitions=${definition_count}"

success "$my_name" "Data-definition API suggestions validation passed"