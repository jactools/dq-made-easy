#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate the edge ingress rendering for the selected root env.
# What it does:
# - Ensures local edge TLS assets exist.
# - Renders the edge config without requiring upstream services.
# - Fails if the rendered host routes or upstream targets do not match the selected env.
# validate: groups=ui,regression
# Version: 1.3
# Last modified: 2026-05-01
# Changelog:
# - 1.1 (2026-04-28): Pass local TLS and host routing env vars explicitly so the validator is self-contained.
# - 1.2 (2026-05-01): Source the selected root env file and derive expected hostnames from the Test environment.
# - 1.3 (2026-05-01): Validate public mode when the selected env renders public edge routes.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_edge_local_ingress.sh"

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

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR"

if ! source_selected_root_env_file; then
  exit 1
fi

EDGE_MODE="${EDGE_MODE:-local}"

EDGE_LOCAL_APP_HOST="${EDGE_LOCAL_APP_HOST:-${LOCAL_APP_HOST:-}}"
EDGE_LOCAL_KONG_HOST="${EDGE_LOCAL_KONG_HOST:-${LOCAL_KONG_HOST:-}}"
EDGE_LOCAL_KEYCLOAK_HOST="${EDGE_LOCAL_KEYCLOAK_HOST:-${LOCAL_KEYCLOAK_HOST:-}}"
EDGE_LOCAL_OPENMETADATA_HOST="${EDGE_LOCAL_OPENMETADATA_HOST:-${LOCAL_OPENMETADATA_HOST:-}}"
EDGE_LOCAL_OBSERVABILITY_HOST="${EDGE_LOCAL_OBSERVABILITY_HOST:-${LOCAL_OBSERVABILITY_HOST:-}}"
EDGE_LOCAL_SUPPORT_HOST="${EDGE_LOCAL_SUPPORT_HOST:-${LOCAL_SUPPORT_HOST:-}}"
EDGE_LOCAL_AIRFLOW_HOST="${EDGE_LOCAL_AIRFLOW_HOST:-${LOCAL_AIRFLOW_HOST:-}}"

EDGE_PUBLIC_APEX_HOST="${EDGE_PUBLIC_APEX_HOST:-${PUBLIC_APEX_HOST:-}}"
EDGE_PUBLIC_CANONICAL_HOST="${EDGE_PUBLIC_CANONICAL_HOST:-${PUBLIC_CANONICAL_HOST:-}}"
EDGE_SSL_CERTS_DIR="${EDGE_SSL_CERTS_DIR:-}"
EDGE_SSL_CERT_FILE_NAME="${EDGE_SSL_CERT_FILE_NAME:-}"
EDGE_SSL_KEY_FILE_NAME="${EDGE_SSL_KEY_FILE_NAME:-}"

if [[ -z "$EDGE_SSL_CERTS_DIR" || -z "$EDGE_SSL_CERT_FILE_NAME" || -z "$EDGE_SSL_KEY_FILE_NAME" ]]; then
  error "$my_name" "selected root env file must define edge cert directory and filenames"
  exit 1
fi

EDGE_SSL_CERTS_DIR="$(resolve_path "$EDGE_SSL_CERTS_DIR")"
EDGE_CERT_FILE_PATH="$EDGE_SSL_CERTS_DIR/$EDGE_SSL_CERT_FILE_NAME"
EDGE_KEY_FILE_PATH="$EDGE_SSL_CERTS_DIR/$EDGE_SSL_KEY_FILE_NAME"

if [[ "$EDGE_MODE" == "public" ]]; then
  if [[ -z "$EDGE_PUBLIC_APEX_HOST" || -z "$EDGE_PUBLIC_CANONICAL_HOST" ]]; then
    error "$my_name" "selected root env file must define public edge hostnames"
    exit 1
  fi
else
  if [[ -z "$EDGE_LOCAL_APP_HOST" || -z "$EDGE_LOCAL_KONG_HOST" || -z "$EDGE_LOCAL_KEYCLOAK_HOST" || -z "$EDGE_LOCAL_OPENMETADATA_HOST" || -z "$EDGE_LOCAL_OBSERVABILITY_HOST" || -z "$EDGE_LOCAL_SUPPORT_HOST" ]]; then
    error "$my_name" "selected root env file must define local edge hostnames"
    exit 1
  fi
fi

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

assert_contains() {
  local needle="$1"
  local haystack="$2"

  if ! printf '%s' "$haystack" | grep -Fq "$needle"; then
    error "$my_name" "expected rendered edge config to contain: $needle"
    exit 1
  fi
}

assert_not_contains() {
  local needle="$1"
  local haystack="$2"

  if printf '%s' "$haystack" | grep -Fq "$needle"; then
    error "$my_name" "did not expect rendered edge config to contain: $needle"
    exit 1
  fi
}

require_cmd docker

if [ ! -f "$EDGE_CERT_FILE_PATH" ] || [ ! -f "$EDGE_KEY_FILE_PATH" ]; then
  if [[ "$EDGE_SSL_CERTS_DIR" == "$ROOT_DIR/tmp/certs" ]]; then
    info "$my_name" "generating local edge wildcard certificate..."
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

info "$my_name" "Rendering local edge ingress config..."
edge_container_id="$(find_running_compose_container edge)"
rendered_config="$(docker exec \
  -e EDGE_MODE="$EDGE_MODE" \
  -e EDGE_LOCAL_APP_HOST="$EDGE_LOCAL_APP_HOST" \
  -e EDGE_LOCAL_KONG_HOST="$EDGE_LOCAL_KONG_HOST" \
  -e EDGE_LOCAL_KEYCLOAK_HOST="$EDGE_LOCAL_KEYCLOAK_HOST" \
  -e EDGE_LOCAL_OPENMETADATA_HOST="$EDGE_LOCAL_OPENMETADATA_HOST" \
  -e EDGE_LOCAL_OBSERVABILITY_HOST="$EDGE_LOCAL_OBSERVABILITY_HOST" \
  -e EDGE_LOCAL_SUPPORT_HOST="$EDGE_LOCAL_SUPPORT_HOST" \
  -e EDGE_LOCAL_AIRFLOW_HOST="$EDGE_LOCAL_AIRFLOW_HOST" \
  -e EDGE_PUBLIC_APEX_HOST="$EDGE_PUBLIC_APEX_HOST" \
  -e EDGE_PUBLIC_CANONICAL_HOST="$EDGE_PUBLIC_CANONICAL_HOST" \
  -e EDGE_SSL_CERT_FILE="/etc/nginx/certs/$EDGE_SSL_CERT_FILE_NAME" \
  -e EDGE_SSL_KEY_FILE="/etc/nginx/certs/$EDGE_SSL_KEY_FILE_NAME" \
  "$edge_container_id" \
  /bin/sh -c '/bin/sh /opt/edge/render-edge-config.sh && if [ "$EDGE_MODE" = public ]; then sed -n "1,360p" /etc/nginx/conf.d/default.conf; else sed -n "1,240p" /etc/nginx/nginx.conf; fi')"

if [[ "$EDGE_MODE" == "public" ]]; then
  assert_contains "server_name ${EDGE_PUBLIC_APEX_HOST};" "$rendered_config"
  assert_contains "return 308 https://${EDGE_PUBLIC_CANONICAL_HOST}\$request_uri;" "$rendered_config"
  assert_contains "server_name _ ${EDGE_PUBLIC_CANONICAL_HOST};" "$rendered_config"
  assert_contains 'location /iam/ {' "$rendered_config"
  assert_contains 'location /metadata/ {' "$rendered_config"
  assert_contains 'location /observability/ {' "$rendered_config"
  assert_contains 'location /support/ {' "$rendered_config"
  assert_contains 'location /ops/kong/ {' "$rendered_config"
  success "$my_name" "public edge ingress renders expected path-prefix routes"
else
  assert_contains 'stream {' "$rendered_config"
  assert_contains 'ssl_preread on;' "$rendered_config"
  assert_contains 'map $ssl_preread_server_name $upstream {' "$rendered_config"
  assert_contains "${EDGE_LOCAL_APP_HOST} frontend:443;" "$rendered_config"
  assert_contains "${EDGE_LOCAL_KONG_HOST} kong:8443;" "$rendered_config"
  assert_contains "${EDGE_LOCAL_KEYCLOAK_HOST} keycloak:8443;" "$rendered_config"
  assert_contains "${EDGE_LOCAL_OPENMETADATA_HOST} openmetadata-server:8585;" "$rendered_config"
  assert_contains "${EDGE_LOCAL_OBSERVABILITY_HOST} grafana:3000;" "$rendered_config"
  assert_contains "${EDGE_LOCAL_SUPPORT_HOST} zammad-https:443;" "$rendered_config"
  assert_contains 'listen 443;' "$rendered_config"
  assert_contains 'proxy_pass $upstream;' "$rendered_config"
  assert_not_contains 'proxy_set_header' "$rendered_config"
  assert_not_contains 'location / {' "$rendered_config"
  if [[ -n "$EDGE_LOCAL_AIRFLOW_HOST" ]]; then
    assert_not_contains "$EDGE_LOCAL_AIRFLOW_HOST" "$rendered_config"
  fi

  success "$my_name" "local edge ingress renders expected transparent TLS routing"
fi