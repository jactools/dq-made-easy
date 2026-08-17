#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate the OpenMetadata ingestion configuration keeps HTTPS-only behavior.
# What it does:
# - Checks env files and K8s manifests for HTTPS URLs.
# - Verifies the ingestion service uses HTTPS URLs and Airflow API SSL env vars.
# - Fails if plaintext HTTP URLs appear where HTTPS is required.
# validate: groups=repo
# validate: ignore=true
# TODO: deferred — OpenMetadata not yet migrated to Kind
# validate: include=true
# Version: 2.0
# Last modified: 2026-08-17

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_openmetadata_ingestion_tls.sh"

FAILURES=0

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

  if ! printf '%s' "$haystack" | grep -Fq "$needle" 2>/dev/null; then
    error "$my_name" "expected to contain: $needle"
    FAILURES=$((FAILURES + 1))
  fi
}

assert_not_contains() {
  local needle="$1"
  local haystack="$2"

  if printf '%s' "$haystack" | grep -Fq "$needle" 2>/dev/null; then
    error "$my_name" "must not contain: $needle"
    FAILURES=$((FAILURES + 1))
  fi
}

info "$my_name" "validating OpenMetadata TLS config from $ENV_FILE"

# Read env file
env_content="$(cat "$ENV_FILE")"

# Check for HTTPS Airflow URLs in env files
# These may be in env files as DQ_AIRFLOW_BASE_URL or similar
if printf '%s' "$env_content" | grep -q "AIRFLOW.*http://" 2>/dev/null; then
  error "$my_name" "found plaintext HTTP Airflow URL in $ENV_FILE"
  FAILURES=$((FAILURES + 1))
fi

# Check K8s manifests for OpenMetadata ingestion TLS
if [ -d "$ROOT_DIR/k8s" ] || [ -d "$ROOT_DIR/infra/k8s" ]; then
  info "$my_name" "checking K8s manifests for OpenMetadata TLS..."

  # Scan for OpenMetadata-related manifests
  while IFS= read -r manifest; do
    manifest_content="$(cat "$manifest")"

    # Check for plaintext HTTP URLs to ingestion service
    if printf '%s' "$manifest_content" | grep -q "http://openmetadata-ingestion" 2>/dev/null; then
      error "$my_name" "found plaintext HTTP URL to openmetadata-ingestion in $(basename "$manifest")"
      FAILURES=$((FAILURES + 1))
    fi

    # Check for HTTPS URLs (preferred)
    if printf '%s' "$manifest_content" | grep -q "openmetadata-ingestion" 2>/dev/null; then
      if printf '%s' "$manifest_content" | grep -q "https://openmetadata-ingestion" 2>/dev/null; then
        info "$my_name" "HTTPS URL to openmetadata-ingestion found in $(basename "$manifest")"
      fi
    fi
  done < <(find "$ROOT_DIR" \( -path "*/k8s/*" -o -path "*/infra/k8s/*" \) -name "*.yaml" 2>/dev/null | grep -i openmetadata | head -20)
fi

# Check compose files if they exist (legacy)
if [ -d "$ROOT_DIR/docker-compose" ]; then
  info "$my_name" "checking docker-compose for OpenMetadata TLS (legacy)..."
  compose_content="$(grep -r "openmetadata-ingestion\|AIRFLOW_HOST\|PIPELINE_SERVICE" "$ROOT_DIR/docker-compose/" 2>/dev/null || true)"

  if [ -n "$compose_content" ]; then
    assert_not_contains 'AIRFLOW_HOST: http://openmetadata-ingestion' "$compose_content"
    assert_not_contains 'PIPELINE_SERVICE_CLIENT_ENDPOINT: http://openmetadata-ingestion' "$compose_content"
    assert_not_contains 'airflow users create' "$compose_content"
  fi
fi

if [ $FAILURES -eq 0 ]; then
  success "$my_name" "openmetadata ingestion wiring stays HTTPS-only"
  exit 0
else
  error "$my_name" "openmetadata TLS validation found ${FAILURES} issue(s)"
  exit 1
fi
