#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate OpenMetadata contract cache hits, misses, and totals appear in Grafana.
#
# What it does:
# - Requires the API, Kong, Grafana, and Prometheus containers to already be running.
# - Uses the shared auth helper to mint a seeded user token and Grafana cookie.
# - Uses the shared OpenMetadata auth helper to prepare OM_TOKEN with the seeded realm contract.
# - Verifies OpenMetadata cache TTL is enabled, then discovers live data-object versions with the required JOIN_CONSISTENCY attributes.
# - Confirms the OpenMetadata cache miss and hit counters increase after the live mutation path runs.
#
# validate: groups=api,observability
# Version: 1.0
# Last modified: 2026-05-11

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/openmetadata.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/grafana_oauth_session.sh"

my_name="validate_openmetadata_contract_cache.sh"

dq_source_seeded_user_credentials --quiet

REQUESTER_EMAIL="${KEYCLOAK_JACCLOUD_USERNAME:?KEYCLOAK_JACCLOUD_USERNAME must be set}"
REQUESTER_PASSWORD="${KEYCLOAK_JACCLOUD_PASSWORD:?KEYCLOAK_JACCLOUD_PASSWORD must be set}"

: "${KONG_PUBLIC_URL:?KONG_PUBLIC_URL must be set to the public Kong URL used by the UI}"
: "${GRAFANA_PUBLIC_URL:?GRAFANA_PUBLIC_URL must be set}"
: "${GRAFANA_ADMIN_USER:?GRAFANA_ADMIN_USER must be set}"
: "${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD must be set}"
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

  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" || true)"
    if [[ "$code" == "200" ]]; then
      return 0
    fi
    info "$my_name" "Waiting for ${label} to report HTTP 200 (current=${code:-unknown})"
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
  local response_file
  local headers_file
  local response_code
  local curl_rc

  response_file="$(mktemp)"
  headers_file="$(mktemp)"

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
    rm -f "$response_file" "$headers_file"
    exit "$curl_rc"
  fi

  HTTP_CODE="$response_code"
  HTTP_BODY="$(cat "$response_file")"
  rm -f "$response_file" "$headers_file"
}

prom_query_value() {
  local grafana_url="$1"
  local cookie_header="$2"
  local datasource_uid="$3"
  local query="$4"
  local response

  if ! response="$(curl -sS -H "Cookie: ${cookie_header}" --get --data-urlencode "query=${query}" "${grafana_url}/api/datasources/proxy/uid/${datasource_uid}/api/v1/query")"; then
    error "$my_name" "Prometheus query request failed for: ${query}"
    return 1
  fi

  if ! jq -e '.status == "success"' >/dev/null 2>&1 <<<"$response"; then
    error "$my_name" "Unexpected Prometheus response for query: ${query}"
    printf '%s\n' "$response" >&2
    return 1
  fi

  jq -r '.data.result[0].value[1] // "0"' <<<"$response"
}

wait_for_metric_increase() {
  local grafana_url="$1"
  local cookie_header="$2"
  local datasource_uid="$3"
  local query="$4"
  local baseline_value="$5"
  local label="$6"
  local current_value
  local attempt

  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
    current_value="$(prom_query_value "$grafana_url" "$cookie_header" "$datasource_uid" "$query")"
    if awk -v baseline="$baseline_value" -v current="$current_value" 'BEGIN { exit !((current + 0) > (baseline + 0)) }'; then
      printf '%s\n' "$current_value"
      return 0
    fi
    sleep 1
  done

  error "$my_name" "${label} did not increase"
  return 1
}

build_rule_payload() {
  local name="$1"
  local description="$2"
  local left_data_object_version_id="$3"
  local right_data_object_version_id="$4"

  jq -nc \
    --arg name "$name" \
    --arg description "$description" \
    --arg left_data_object_version_id "$left_data_object_version_id" \
    --arg right_data_object_version_id "$right_data_object_version_id" \
    --arg workspace "retail-banking" \
    '{
      name: $name,
      description: $description,
      dimension: "consistency",
      active: false,
      workspace: $workspace,
      generated: false,
      is_template: false,
      ai_output: false,
      dsl: {
        schemaVersion: "1.0.0",
        source: {
          kind: "check_type",
          checkType: "JOIN_CONSISTENCY",
          checkTypeParams: {
            checkType: "JOIN_CONSISTENCY",
            leftDataObjectVersionId: $left_data_object_version_id,
            rightDataObjectVersionId: $right_data_object_version_id,
            joinKeys: [
              {
                leftAttribute: "customer_id",
                rightAttribute: "customer_id"
              }
            ],
            comparisons: [
              {
                leftAttribute: "email",
                rightAttribute: "email_address",
                mode: "case_insensitive"
              }
            ],
            actualityDate: {
              leftAttribute: "created_at",
              rightAttribute: "last_contacted",
              toleranceSource: "DELIVERY_CONTRACT",
              contractId: "urn:dq:contract:demo-azure-payments-sql"
            },
            minMatchRate: 99
          }
        }
      }
    }'
}

find_data_object_version_with_attributes() {
  local label="$1"
  shift
  local required_attributes=("$@")
  local page=1
  local has_next="true"
  local page_body
  local version_id
  local attribute_names
  local missing_attribute
  local missing_attributes

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

      api_request_with_token "$ACCESS_TOKEN" GET "/data-catalog/v1/attributes-catalog?versionId=${version_id}&page=1&limit=100"
      if [[ "$HTTP_CODE" != "200" ]]; then
        error "$my_name" "GET /data-catalog/v1/attributes-catalog?versionId=${version_id}&page=1&limit=100 returned HTTP ${HTTP_CODE}"
        printf '%s\n' "$HTTP_BODY" >&2
        exit 1
      fi

      attribute_names="$(jq -r '.data[]?.name // empty' <<<"$HTTP_BODY")"
      missing_attributes=()
      for missing_attribute in "${required_attributes[@]}"; do
        if ! grep -Fxq "$missing_attribute" <<<"$attribute_names"; then
          missing_attributes+=("$missing_attribute")
        fi
      done

      if [[ "${#missing_attributes[@]}" -eq 0 ]]; then
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

  error "$my_name" "Could not find a live data_object_version_id for ${label} with attributes: ${required_attributes[*]}"
  exit 1
}

require_cmd docker
require_cmd curl
require_cmd jq

for service_name in api kong grafana prometheus; do
  require_running_service "$service_name"
done

wait_for_http_200 "${KONG_PUBLIC_URL%/}/health" "api health"

TOKEN_ENDPOINT="${SSO_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"
ACCESS_TOKEN="$(dq_keycloak_password_grant_access_token "$TOKEN_ENDPOINT" "$VITE_KEYCLOAK_CLIENT_ID" "$REQUESTER_EMAIL" "$REQUESTER_PASSWORD")"

prepare_openmetadata_access_token || {
  error "$my_name" "Unable to prepare OM_TOKEN for OpenMetadata validation"
  exit 1
}

GRAFANA_URL="${GRAFANA_PUBLIC_URL%/}"
GRAFANA_COOKIE_HEADER="$(grafana_validation_cookie_header "$ROOT_DIR" "$GRAFANA_URL" "$GRAFANA_ADMIN_USER" "$GRAFANA_ADMIN_PASSWORD")"

prometheus_uid=""
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  prometheus_uid="$(curl -sS -H "Cookie: ${GRAFANA_COOKIE_HEADER}" "${GRAFANA_URL}/api/datasources/name/Prometheus" | jq -r '.uid // empty')"
  if [[ -n "$prometheus_uid" ]]; then
    break
  fi
  info "$my_name" "Waiting for Grafana Prometheus datasource UID"
  sleep 2
done

if [[ -z "$prometheus_uid" ]]; then
  error "$my_name" "Could not resolve Grafana Prometheus datasource uid"
  exit 1
fi

app_config_response=""
api_request_with_token "$ACCESS_TOKEN" GET "/system/v1/app-config"
if [[ "$HTTP_CODE" != "200" ]]; then
  error "$my_name" "GET /system/v1/app-config returned HTTP ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi
app_config_response="$HTTP_BODY"

cache_ttl_seconds="$(jq -r '.open_metadata_contract_cache_ttl_seconds // empty' <<<"$app_config_response")"
if [[ -z "$cache_ttl_seconds" ]]; then
  error "$my_name" "App config did not include open_metadata_contract_cache_ttl_seconds"
  printf '%s\n' "$app_config_response" >&2
  exit 1
fi

if ! awk -v ttl="$cache_ttl_seconds" 'BEGIN { exit !((ttl + 0) > 0) }'; then
  error "$my_name" "open_metadata_contract_cache_ttl_seconds must be greater than zero for cache validation"
  printf 'open_metadata_contract_cache_ttl_seconds=%s\n' "$cache_ttl_seconds" >&2
  exit 1
fi

cache_hit_query='sum(dq_api_contract_policy_cache_events_total{provider="openmetadata",cache_status="hit"})'
cache_miss_query='sum(dq_api_contract_policy_cache_events_total{provider="openmetadata",cache_status="miss"})'
cache_total_query='sum(dq_api_contract_policy_cache_events_total{provider="openmetadata"})'

clear_openmetadata_contract_cache() {
  local cache_key_pattern="$1"
  local redis_container_name
  local cache_keys
  local cache_key

  redis_container_name="$(docker ps --filter 'label=com.docker.compose.service=redis' --filter 'status=running' --format '{{.Names}}' | head -1)"
  if [[ -z "$redis_container_name" ]]; then
    error "$my_name" "redis must already be running to clear the OpenMetadata contract cache"
    exit 1
  fi

  cache_keys="$(docker exec "$redis_container_name" redis-cli --scan --pattern "$cache_key_pattern" 2>/dev/null || true)"
  if [[ -z "$cache_keys" ]]; then
    return 0
  fi

  while IFS= read -r cache_key; do
    [[ -z "$cache_key" ]] && continue
    if ! docker exec "$redis_container_name" redis-cli DEL "$cache_key" >/dev/null 2>&1; then
      error "$my_name" "Failed to clear OpenMetadata contract cache key: $cache_key"
      exit 1
    fi
  done <<<"$cache_keys"
}

clear_openmetadata_contract_cache 'dq:openmetadata:contract-policy:urn:dq:contract:demo-azure-payments-sql:dataset:*'

baseline_hit="$(prom_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$cache_hit_query")"
baseline_miss="$(prom_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$cache_miss_query")"
baseline_total="$(prom_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$cache_total_query")"

left_data_object_version_id="$(find_data_object_version_with_attributes "JOIN_CONSISTENCY left side" customer_id email created_at)"
right_data_object_version_id="$(find_data_object_version_with_attributes "JOIN_CONSISTENCY right side" customer_id email_address last_contacted)"

if [[ "$left_data_object_version_id" == "$right_data_object_version_id" ]]; then
  error "$my_name" "Live catalog returned the same data_object_version_id for both JOIN_CONSISTENCY sides: ${left_data_object_version_id}"
  exit 1
fi

rule_name="OpenMetadata cache validation $(date -u +%Y%m%d%H%M%S)"
create_payload="$(build_rule_payload "$rule_name" "OpenMetadata cache validation create" "$left_data_object_version_id" "$right_data_object_version_id")"

api_request_with_token "$ACCESS_TOKEN" POST "/rulebuilder/v1/rules" "$create_payload"
if [[ "$HTTP_CODE" != "200" ]]; then
  error "$my_name" "POST /rulebuilder/v1/rules returned HTTP ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

rule_id="$(jq -r '.id // empty' <<<"$HTTP_BODY")"
if [[ -z "$rule_id" ]]; then
  error "$my_name" "Rule create response did not include an id"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

update_payload="$(build_rule_payload "$rule_name" "OpenMetadata cache validation update" "$left_data_object_version_id" "$right_data_object_version_id")"
api_request_with_token "$ACCESS_TOKEN" PUT "/rulebuilder/v1/rules/${rule_id}" "$update_payload"
if [[ "$HTTP_CODE" != "200" ]]; then
  error "$my_name" "PUT /rulebuilder/v1/rules/${rule_id} returned HTTP ${HTTP_CODE}"
  printf '%s\n' "$HTTP_BODY" >&2
  exit 1
fi

hit_value="$(wait_for_metric_increase "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$cache_hit_query" "$baseline_hit" "OpenMetadata cache hit counter")"
miss_value="$(wait_for_metric_increase "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$cache_miss_query" "$baseline_miss" "OpenMetadata cache miss counter")"
total_value="$(wait_for_metric_increase "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$cache_total_query" "$baseline_total" "OpenMetadata cache total counter")"

ratio_query='sum(dq_api_contract_policy_cache_events_total{provider="openmetadata",cache_status="hit"}) / clamp_min(sum(dq_api_contract_policy_cache_events_total{provider="openmetadata"}), 1)'
ratio_value="$(prom_query_value "$GRAFANA_URL" "$GRAFANA_COOKIE_HEADER" "$prometheus_uid" "$ratio_query")"

info "$my_name" "Final Grafana evidence"
info "$my_name" "- hit_increase=${hit_value}"
info "$my_name" "- miss_increase=${miss_value}"
info "$my_name" "- total_increase=${total_value}"
info "$my_name" "- hit_ratio=${ratio_value}"
info "$my_name" "- rule_id=${rule_id}"

success "$my_name" "OpenMetadata contract cache validation passed"
