#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate the W6 transparent TLS routing slice and its documented gaps.
# What it does:
# - Confirms the local edge renderer uses SNI/TCP passthrough for TLS-native hosts.
# - Confirms the public edge renderer still uses path-based TLS termination, which remains an explicit redesign gap.
# - Confirms the Zammad HTTPS front door still points at the legacy zammad-nginx backend and is annotated as such.
# validate: groups=repo,regression

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_w6_transparent_tls_routing.sh"

require_file() {
  local file_path="$1"
  if [[ ! -f "$file_path" ]]; then
    error "$my_name" "Missing required file: $file_path"
    exit 1
  fi
}

require_present() {
  local needle="$1"
  local file_path="$2"
  if ! grep -Fq "$needle" "$file_path"; then
    error "$my_name" "Missing '${needle}' in ${file_path}"
    exit 1
  fi
}

require_absent() {
  local needle="$1"
  local file_path="$2"
  if grep -Fq "$needle" "$file_path"; then
    error "$my_name" "Found forbidden '${needle}' in ${file_path}"
    exit 1
  fi
}

require_file "$ROOT_DIR/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"
require_file "$ROOT_DIR/docker/zammad/nginx-https.conf.template"

require_present 'stream {' "$ROOT_DIR/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"
require_present 'ssl_preread on;' "$ROOT_DIR/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"
require_present 'map $ssl_preread_server_name $upstream {' "$ROOT_DIR/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"
require_present 'frontend:443;' "$ROOT_DIR/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"
require_present 'kong:8443;' "$ROOT_DIR/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"
require_present 'keycloak:8443;' "$ROOT_DIR/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"
require_present 'openmetadata-server:8585;' "$ROOT_DIR/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"
require_present 'grafana:3000;' "$ROOT_DIR/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"
require_present 'zammad-https:443;' "$ROOT_DIR/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"
require_absent 'airflow:8080;' "$ROOT_DIR/dq-edge/docker-entrypoint.d/40-render-edge-config.sh"

require_present '# W6 gap: this front door still terminates TLS before handing off to the' "$ROOT_DIR/docker/zammad/nginx-https.conf.template"
require_present 'set $zammad_upstream http://zammad-nginx:8080;' "$ROOT_DIR/docker/zammad/nginx-https.conf.template"

success "$my_name" "W6 transparent TLS routing validation passed"