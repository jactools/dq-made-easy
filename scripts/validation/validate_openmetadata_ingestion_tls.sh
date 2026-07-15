#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate the OpenMetadata ingestion compose wiring keeps HTTPS-only startup behavior.
# What it does:
# - Renders the compose config for the selected env file.
# - Verifies the ingestion service uses HTTPS URLs and Airflow API SSL env vars.
# - Fails if the removed Airflow users seed command reappears.
# validate: groups=repo
# validate: include=true
# Version: 1.0
# Last modified: 2026-07-08

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_openmetadata_ingestion_tls.sh"

ENV_FILE="${1:-.env.dev.local}"

if [[ ! -f "$ROOT_DIR/$ENV_FILE" && ! -f "$ENV_FILE" ]]; then
  error "$my_name" "env file not found: $ENV_FILE"
  exit 1
fi

if [[ -f "$ROOT_DIR/$ENV_FILE" ]]; then
  ENV_FILE="$ROOT_DIR/$ENV_FILE"
fi

assert_contains() {
  local needle="$1"
  local haystack="$2"

  if ! printf '%s' "$haystack" | grep -Fq "$needle"; then
    error "$my_name" "expected compose config to contain: $needle"
    exit 1
  fi
}

assert_not_contains() {
  local needle="$1"
  local haystack="$2"

  if printf '%s' "$haystack" | grep -Fq "$needle"; then
    error "$my_name" "compose config must not contain: $needle"
    exit 1
  fi
}

info "$my_name" "rendering compose config from $ENV_FILE"
compose_config="$(docker compose --profile metadata --env-file "$ENV_FILE" config)"

assert_contains 'AIRFLOW__API__BASE_URL: https://openmetadata-ingestion:8080' "$compose_config"
assert_contains 'AIRFLOW__API__SSL_CERT: /etc/openmetadata/certs/openmetadata-ingestion/tls.crt' "$compose_config"
assert_contains 'AIRFLOW__API__SSL_KEY: /etc/openmetadata/certs/openmetadata-ingestion/tls.key' "$compose_config"
assert_contains 'AIRFLOW_HOST: https://openmetadata-ingestion:8080' "$compose_config"
assert_contains 'PIPELINE_SERVICE_CLIENT_ENDPOINT: https://openmetadata-ingestion:8080' "$compose_config"
assert_contains 'airflow api-server -p 8080' "$compose_config"
assert_not_contains 'airflow users create' "$compose_config"
assert_not_contains 'AIRFLOW_HOST: http://openmetadata-ingestion:8080' "$compose_config"
assert_not_contains 'PIPELINE_SERVICE_CLIENT_ENDPOINT: http://openmetadata-ingestion:8080' "$compose_config"

success "$my_name" "openmetadata ingestion compose wiring stays HTTPS-only"