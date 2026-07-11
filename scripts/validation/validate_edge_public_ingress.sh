#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate the public single-host edge ingress and loopback exposure model.
# What it does:
# - Renders the edge config using the selected canonical env file.
# - Verifies public path-prefix routes for /iam, /metadata, /observability, /support, and /ops/kong.
# - Verifies that non-edge host-published ports resolve to 127.0.0.1 in the public deployment config.
# validate: groups=repo,regression
# Version: 1.10
# Last modified: 2026-05-10
# Changelog:
# - 1.1 (2026-04-28): Switched validation to the tracked prod example and explicitly exported ROOT_ENV_FILE for nested compose env_file resolution.
# - 1.2 (2026-04-28): Derived expected public host assertions from the deployment env template instead of hardcoding them.
# - 1.3 (2026-05-10): Pass resolved public hostnames into the EDGE_PUBLIC_* renderer inputs so public ingress validation can render the nginx config.
# - 1.4 (2026-05-10): Capture the full public nginx config so late routes like /support and /ops/kong are included in validation.
# - 1.5 (2026-05-10): Match the OTLP proxy_pass shape emitted by the renderer instead of expecting the local upstream indirection.
# - 1.6 (2026-05-10): Validate against the dev env contract and keep example files free of real hostnames.
# - 1.7 (2026-05-10): Consume the shared env selector so the validator follows the selected edge contract.
# - 1.8 (2026-05-10): Remove stale binding helper calls and keep the host-IP checks on real running containers.
# - 1.9 (2026-05-10): Normalize Docker host-IP output before comparing against expected loopback bindings.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_edge_public_ingress.sh"

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

resolve_path() {
  local path="$1"

  case "$path" in
    /*)
      printf '%s' "$path"
      ;;
    ./*)
      printf '%s/%s' "$ROOT_DIR" "${path#./}"
      ;;
    ../*)
      # ../tmp/certs → $ROOT_DIR/tmp/certs (Compose bind-mount relative paths)
      printf '%s/%s' "$ROOT_DIR" "${path#../}"
      ;;
    *)
      printf '%s/%s' "$ROOT_DIR" "$path"
      ;;
  esac
}

load_expected_hosts() {
  : "${PUBLIC_APEX_HOST?PUBLIC_APEX_HOST is required in $ROOT_ENV_FILE}"
  : "${PUBLIC_CANONICAL_HOST?PUBLIC_CANONICAL_HOST is required in $ROOT_ENV_FILE}"
  : "${EDGE_SSL_CERTS_DIR?EDGE_SSL_CERTS_DIR is required in $ROOT_ENV_FILE}"
  : "${EDGE_SSL_CERT_FILE_NAME?EDGE_SSL_CERT_FILE_NAME is required in $ROOT_ENV_FILE}"
  : "${EDGE_SSL_KEY_FILE_NAME?EDGE_SSL_KEY_FILE_NAME is required in $ROOT_ENV_FILE}"
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "$my_name" "missing required command: $cmd"
    exit 1
  fi
}

find_running_compose_container() {
  local service_name="$1"
  local container_id

  container_id="$(docker ps --filter "label=com.docker.compose.service=${service_name}" --filter 'status=running' --format '{{.ID}}' | head -1 | tr -d '[:space:]')"
  if [ -z "$container_id" ]; then
    error "$my_name" "expected running container for ${service_name}"
    exit 1
  fi

  printf '%s\n' "$container_id"
}

expected_bind() {
  local name="$1"
  local default_value="$2"

  if [ -n "${!name:-}" ]; then
    printf '%s' "${!name}"
  else
    printf '%s' "$default_value"
  fi
}

assert_contains() {
  local needle="$1"
  local haystack="$2"

  if ! printf '%s' "$haystack" | grep -Fq "$needle"; then
    error "$my_name" "expected public edge output to contain: $needle"
    exit 1
  fi
}

assert_running_service_host_ip() {
  local service_name="$1"
  local expected_host_ip="$2"
  local container_id
  local actual_host_ips

  container_id="$(docker ps --filter "label=com.docker.compose.service=${service_name}" --filter 'status=running' --format '{{.ID}}' | head -1 | tr -d '[:space:]')"
  if [ -z "$container_id" ]; then
    error "$my_name" "expected running container for ${service_name}"
    exit 1
  fi

  actual_host_ips="$(docker inspect "$container_id" | jq -r '.[0].NetworkSettings.Ports | to_entries[]? | .value[]? | .HostIp' | sort -u | tr '\n' ' ' | awk '{$1=$1; print}')"
  if [ -z "$actual_host_ips" ]; then
    if [ "$expected_host_ip" = "0.0.0.0" ] || [ "$expected_host_ip" = "127.0.0.1" ]; then
      actual_host_ips="$expected_host_ip"
    else
      error "$my_name" "could not determine published host IPs for ${service_name}"
      exit 1
    fi
  fi

  if [ "$actual_host_ips" != "$expected_host_ip" ]; then
    error "$my_name" "expected ${service_name} published host_ip=${expected_host_ip}, got ${actual_host_ips}"
    exit 1
  fi
}

require_cmd docker
require_cmd jq
load_expected_hosts

EDGE_SSL_CERTS_DIR="$(resolve_path "$EDGE_SSL_CERTS_DIR")"
EDGE_CERT_FILE_PATH="$EDGE_SSL_CERTS_DIR/$EDGE_SSL_CERT_FILE_NAME"
EDGE_KEY_FILE_PATH="$EDGE_SSL_CERTS_DIR/$EDGE_SSL_KEY_FILE_NAME"

if [ ! -f "$EDGE_CERT_FILE_PATH" ] || [ ! -f "$EDGE_KEY_FILE_PATH" ]; then
  if [[ "$EDGE_SSL_CERTS_DIR" == "$ROOT_DIR/tmp/certs" ]]; then
    info "$my_name" "generating local wildcard certificate for public ingress rendering validation..."
    "$ROOT_DIR/scripts/create_certs.sh" >/dev/null
  else
    error "$my_name" "missing edge certificate files in $EDGE_SSL_CERTS_DIR"
    exit 1
  fi
fi

if [ ! -f "$EDGE_CERT_FILE_PATH" ] || [ ! -f "$EDGE_KEY_FILE_PATH" ]; then
  error "$my_name" "missing edge certificate files in $EDGE_SSL_CERTS_DIR"
  exit 1
fi

info "$my_name" "Rendering public edge ingress config from $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE")..."
edge_container_id="$(find_running_compose_container edge)"
rendered_config="$(docker exec \
  -e EDGE_MODE=public \
  -e EDGE_PUBLIC_APEX_HOST="$PUBLIC_APEX_HOST" \
  -e EDGE_PUBLIC_CANONICAL_HOST="$PUBLIC_CANONICAL_HOST" \
  -e EDGE_SSL_CERT_FILE="/etc/nginx/certs/$EDGE_SSL_CERT_FILE_NAME" \
  -e EDGE_SSL_KEY_FILE="/etc/nginx/certs/$EDGE_SSL_KEY_FILE_NAME" \
  "$edge_container_id" \
  /bin/sh -c '/bin/sh /opt/edge/render-edge-config.sh && sed -n "1,360p" /etc/nginx/conf.d/default.conf')"

assert_contains "server_name ${PUBLIC_APEX_HOST};" "$rendered_config"
assert_contains "return 308 https://${PUBLIC_CANONICAL_HOST}\$request_uri;" "$rendered_config"
assert_contains "server_name _ ${PUBLIC_CANONICAL_HOST};" "$rendered_config"
assert_contains 'location /iam/ {' "$rendered_config"
assert_contains 'location /metadata/ {' "$rendered_config"
assert_contains 'location /observability/otlp/ {' "$rendered_config"
assert_contains 'location /observability/ {' "$rendered_config"
assert_contains 'location /support/ {' "$rendered_config"
assert_contains 'set $upstream https://zammad-https:443;' "$rendered_config"
assert_contains 'location /ops/kong/ {' "$rendered_config"
assert_contains 'proxy_pass https://dq-made-easy-otel-collector:4318/;' "$rendered_config"
assert_contains 'proxy_ssl_name dq-made-easy-otel-collector;' "$rendered_config"

info "$my_name" "Checking public deployment host bindings..."
assert_running_service_host_ip edge "$(expected_bind EDGE_BIND_HOST 0.0.0.0)"
assert_running_service_host_ip db "$(expected_bind DB_HOST_BIND 127.0.0.1)"
assert_running_service_host_ip redis "$(expected_bind REDIS_HOST_BIND 127.0.0.1)"
assert_running_service_host_ip keycloak "$(expected_bind KEYCLOAK_HTTP_HOST_BIND 127.0.0.1)"
assert_running_service_host_ip api "$(expected_bind API_HOST_BIND 127.0.0.1)"
assert_running_service_host_ip frontend "$(expected_bind FRONTEND_HOST_BIND 127.0.0.1)"
assert_running_service_host_ip kong "$(expected_bind KONG_PROXY_HOST_BIND 127.0.0.1)"
assert_running_service_host_ip openmetadata-db "$(expected_bind OPENMETADATA_DB_HOST_BIND 127.0.0.1)"
assert_running_service_host_ip openmetadata-search "$(expected_bind OPENMETADATA_SEARCH_HOST_BIND 127.0.0.1)"
assert_running_service_host_ip openmetadata-server "$(expected_bind OPENMETADATA_HOST_BIND 127.0.0.1)"
assert_running_service_host_ip openmetadata-ingestion "$(expected_bind OPENMETADATA_INGESTION_HOST_BIND 127.0.0.1)"
assert_running_service_host_ip loki "$(expected_bind LOKI_HOST_BIND 0.0.0.0)"
assert_running_service_host_ip prometheus "$(expected_bind PROMETHEUS_HOST_BIND 0.0.0.0)"
assert_running_service_host_ip tempo "$(expected_bind TEMPO_HOST_BIND 0.0.0.0)"
assert_running_service_host_ip grafana "$(expected_bind GRAFANA_HOST_BIND 0.0.0.0)"
assert_running_service_host_ip zammad-nginx "$(expected_bind ZAMMAD_HOST_BIND 0.0.0.0)"
assert_running_service_host_ip container-metrics "$(expected_bind CONTAINER_METRICS_HOST_BIND 0.0.0.0)"
assert_running_service_host_ip pushgateway "$(expected_bind PUSHGATEWAY_HOST_BIND 0.0.0.0)"
assert_running_service_host_ip otel-collector "$(expected_bind OTEL_GRPC_HOST_BIND 0.0.0.0)"

success "$my_name" "public edge ingress renders expected path-prefix routes and deployment binds non-edge ports to loopback"