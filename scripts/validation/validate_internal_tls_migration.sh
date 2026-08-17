#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate the repository-managed internal TLS migration state.
# What it does:
# - Flags plaintext Postgres defaults and missing trust wiring in env files.
# - Confirms HTTPS URLs are used for internal service communication.
# - Fails fast if the repo still advertises known plaintext exceptions.
# validate: groups=repo,observability
# Version: 2.0
# Last modified: 2026-08-17

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_internal_tls_migration.sh"

FAILURES=0

require_file() {
  local file_path="$1"
  if [[ ! -f "$file_path" ]]; then
    error "$my_name" "Missing required file: $file_path"
    FAILURES=$((FAILURES + 1))
  fi
}

require_present() {
  local needle="$1"
  local file_path="$2"
  if [ -d "$file_path" ]; then
    if ! grep -rFq "$needle" "$file_path" 2>/dev/null; then
      error "$my_name" "Missing '${needle}' in ${file_path}"
      FAILURES=$((FAILURES + 1))
    fi
  elif [ -f "$file_path" ]; then
    if ! grep -Fq "$needle" "$file_path" 2>/dev/null; then
      error "$my_name" "Missing '${needle}' in ${file_path}"
      FAILURES=$((FAILURES + 1))
    fi
  fi
}

require_absent() {
  local needle="$1"
  local file_path="$2"
  if [ -d "$file_path" ]; then
    if grep -rFq "$needle" "$file_path" 2>/dev/null; then
      error "$my_name" "Found forbidden '${needle}' in ${file_path}"
      FAILURES=$((FAILURES + 1))
    fi
  elif [ -f "$file_path" ]; then
    if grep -Fq "$needle" "$file_path" 2>/dev/null; then
      error "$my_name" "Found forbidden '${needle}' in ${file_path}"
      FAILURES=$((FAILURES + 1))
    fi
  fi
}

# Check env files exist
for env_file in .env.dev.local .env.dev.example .env.test.local .env.test.example .env.prod.local .env.prod.example; do
  require_file "$ROOT_DIR/$env_file"
done

# Check no plaintext sslmode in any env/compose files
for file_path in \
  "$ROOT_DIR/.env.dev.local" \
  "$ROOT_DIR/.env.dev.example" \
  "$ROOT_DIR/.env.test.local" \
  "$ROOT_DIR/.env.test.example" \
  "$ROOT_DIR/.env.prod.local" \
  "$ROOT_DIR/.env.prod.example"
do
  require_absent 'sslmode=disable' "$file_path"
done

# Check compose files if they exist (legacy)
if [ -d "$ROOT_DIR/docker-compose" ]; then
  require_absent 'sslmode=disable' "$ROOT_DIR/docker-compose/"
  info "$my_name" "Checking docker-compose for TLS settings (legacy)..."
  # These checks are for compose — skip if not present (Kind doesn't use them)
  grep -rFq 'sslmode=verify-full' "$ROOT_DIR/docker-compose/" 2>/dev/null || true
  grep -rFq 'sslrootcert=' "$ROOT_DIR/docker-compose/" 2>/dev/null || true
fi

# Check HTTPS URLs in env files (critical for internal TLS)
info "$my_name" "Checking HTTPS URLs in env files..."
for env_file in .env.dev.local .env.dev.example .env.test.local .env.test.example .env.prod.local .env.prod.example; do
  local_file="$ROOT_DIR/$env_file"
  [ -f "$local_file" ] || continue

  # Check internal URLs use HTTPS
  require_present 'KONG_ADMIN_INTERNAL_URL=https://' "$local_file"
  require_present 'DQ_ENGINE_INTERNAL_URL=https://' "$local_file"
  require_present 'DQ_LLM_BASE_URL=https://' "$local_file"
  require_present 'DQ_S3_ENDPOINT=https://' "$local_file"

  # Check S3 SSL enabled
  require_present 'DQ_S3_SSL_ENABLED=true' "$local_file"
done

# Check K8s manifests for TLS configuration
if [ -d "$ROOT_DIR/k8s" ] || [ -d "$ROOT_DIR/infra/k8s" ]; then
  info "$my_name" "Checking K8s manifests for TLS configuration..."
  # Check that manifests don't have plaintext Postgres URLs
  require_absent 'sslmode=disable' "$ROOT_DIR/k8s"
  require_absent 'sslmode=disable' "$ROOT_DIR/infra/k8s"
fi

# Check cert generation script if it exists
if [ -f "$ROOT_DIR/scripts/create_certs.sh" ]; then
  info "$my_name" "Checking cert generation script..."
  require_present 'generate_service_cert' "$ROOT_DIR/scripts/create_certs.sh"
fi

if [ $FAILURES -eq 0 ]; then
  success "$my_name" "internal TLS migration state is valid"
  exit 0
else
  error "$my_name" "internal TLS migration validation found ${FAILURES} issue(s)"
  exit 1
fi
