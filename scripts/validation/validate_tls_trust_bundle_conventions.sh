#!/usr/bin/env bash
set -euo pipefail

# Purpose: Verify the repository uses the canonical internal trust bundle and env hooks.
# What it does:
# - Checks the shared internal CA bundle is mounted at the documented paths.
# - Checks main TLS consumers expose the expected client trust variables.
# - Fails fast when a consumer falls back to an ad hoc bundle path.
# validate: groups=repo
# validate: include=true
# Version: 1.0
# Last modified: 2026-07-08

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_tls_trust_bundle_conventions.sh"

require_present() {
  local needle="$1"
  local file_path="$2"
  if ! grep -Fq "$needle" "$file_path"; then
    error "$my_name" "missing '${needle}' in ${file_path}"
    exit 1
  fi
}

require_absent() {
  local needle="$1"
  local file_path="$2"
  if grep -Fq "$needle" "$file_path"; then
    error "$my_name" "found forbidden '${needle}' in ${file_path}"
    exit 1
  fi
}

compose_file="$ROOT_DIR/docker-compose.yml"

require_present './tmp/certs/trust/internal-ca-bundle.pem:/etc/internal-certs/internal-ca-bundle.pem:ro' "$compose_file"
require_present './tmp/certs/trust/internal-ca-bundle.pem:/etc/openmetadata/certs/internal-ca-bundle.pem:ro' "$compose_file"
require_present 'OPENMETADATA_CA_BUNDLE: ${OPENMETADATA_CA_BUNDLE:-/etc/openmetadata/certs/mkcert-rootCA.pem}' "$compose_file"
require_present 'REQUESTS_CA_BUNDLE: ${OPENMETADATA_CA_BUNDLE:-/etc/openmetadata/certs/mkcert-rootCA.pem}' "$compose_file"
require_present 'SSL_CERT_FILE: ${OPENMETADATA_CA_BUNDLE:-/etc/openmetadata/certs/mkcert-rootCA.pem}' "$compose_file"
require_present 'REQUESTS_CA_BUNDLE: /etc/internal-certs/internal-ca-bundle.pem' "$compose_file"
require_present 'SSL_CERT_FILE: /etc/internal-certs/internal-ca-bundle.pem' "$compose_file"
require_present 'OPENMETADATA_CA_BUNDLE: /etc/openmetadata/certs/mkcert-rootCA.pem' "$compose_file"
require_present 'REDIS_URL: rediss://redis:6379/0?ssl_cert_reqs=required&ssl_ca_certs=/etc/internal-certs/internal-ca-bundle.pem&ssl_check_hostname=true' "$compose_file"

require_absent 'ssl_ca_certs=/tmp/' "$compose_file"
require_absent 'REQUESTS_CA_BUNDLE: /tmp/' "$compose_file"
require_absent 'SSL_CERT_FILE: /tmp/' "$compose_file"

success "$my_name" "trust bundle conventions match the canonical internal CA layout"