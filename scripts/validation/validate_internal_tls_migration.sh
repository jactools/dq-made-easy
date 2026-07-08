#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate the repository-managed internal TLS migration state.
# What it does:
# - Flags plaintext Postgres defaults and missing trust wiring in the active compose/env surfaces.
# - Confirms the Postgres-family TLS cutover is reflected in the cert-generation script.
# - Fails fast if the repo still advertises the known plaintext exceptions that Workstream 4 closed.
# validate: groups=repo,observability
# Version: 1.0
# Last modified: 2026-07-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_internal_tls_migration.sh"

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

require_file "$ROOT_DIR/docker-compose.yml"
require_file "$ROOT_DIR/.env.dev.example"
require_file "$ROOT_DIR/.env.test.example"
require_file "$ROOT_DIR/.env.prod.example"
require_file "$ROOT_DIR/.env.deployment.example"
require_file "$ROOT_DIR/scripts/create_certs.sh"

for file_path in \
  "$ROOT_DIR/docker-compose.yml" \
  "$ROOT_DIR/.env.dev.example" \
  "$ROOT_DIR/.env.test.example" \
  "$ROOT_DIR/.env.prod.example" \
  "$ROOT_DIR/.env.deployment.example"
do
  require_absent 'sslmode=disable' "$file_path"
done

require_present 'sslmode=verify-full' "$ROOT_DIR/docker-compose.yml"
require_present 'sslrootcert=' "$ROOT_DIR/docker-compose.yml"
require_present 'KONG_PG_SSL: on' "$ROOT_DIR/docker-compose.yml"
require_present 'KONG_PG_SSL_REQUIRED: on' "$ROOT_DIR/docker-compose.yml"
require_present 'KONG_PG_SSL_VERIFY: on' "$ROOT_DIR/docker-compose.yml"
require_present './tmp/certs/services/db:/etc/postgresql/certs:ro' "$ROOT_DIR/docker-compose.yml"
require_present './tmp/certs/services/kong-db:/etc/postgresql/certs:ro' "$ROOT_DIR/docker-compose.yml"
require_present './tmp/certs/services/openmetadata-db:/etc/postgresql/certs:ro' "$ROOT_DIR/docker-compose.yml"
require_present './tmp/certs/trust/internal-ca-bundle.pem:/etc/postgres-exporter/internal-ca-bundle.pem:ro' "$ROOT_DIR/docker-compose.yml"
require_present './tmp/certs/trust/internal-ca-bundle.pem:/etc/openmetadata/certs/internal-ca-bundle.pem:ro' "$ROOT_DIR/docker-compose.yml"
require_present 'KONG_LUA_SSL_TRUSTED_CERTIFICATE: /etc/kong/certs/trust/internal-ca-bundle.pem' "$ROOT_DIR/docker-compose.yml"
require_present 'generate_service_cert "kong-db" kong-db' "$ROOT_DIR/scripts/create_certs.sh"
require_present 'DQ_DB_INTERNAL_URL=postgresql://postgres:postgres@db:5432/dq?sslmode=verify-full&sslrootcert=/etc/openmetadata/certs/internal-ca-bundle.pem' "$ROOT_DIR/.env.dev.example"
require_present 'DQ_DB_INTERNAL_URL=postgresql://postgres:postgres@db:5432/dq?sslmode=verify-full&sslrootcert=/etc/openmetadata/certs/internal-ca-bundle.pem' "$ROOT_DIR/.env.dev.local"
require_present 'DQ_DB_INTERNAL_URL=postgresql://postgres:postgres@db:5432/dq?sslmode=verify-full&sslrootcert=/etc/openmetadata/certs/internal-ca-bundle.pem' "$ROOT_DIR/.env.prod.local"
require_present 'DQ_DB_INTERNAL_URL=postgresql://postgres:postgres@db:5432/dq?sslmode=verify-full&sslrootcert=/etc/openmetadata/certs/internal-ca-bundle.pem' "$ROOT_DIR/.env.test.local"
require_present 'ZAMMAD_REDIS_URL=rediss://redis:6379/1?ssl_cert_reqs=required&ssl_ca_certs=/etc/zammad/certs/mkcert-rootCA.pem&ssl_check_hostname=true' "$ROOT_DIR/.env.dev.example"
require_present 'ZAMMAD_REDIS_URL=rediss://redis:6379/1?ssl_cert_reqs=required&ssl_ca_certs=/etc/zammad/certs/mkcert-rootCA.pem&ssl_check_hostname=true' "$ROOT_DIR/.env.prod.example"
require_present 'ZAMMAD_REDIS_URL=rediss://redis:6379/1?ssl_cert_reqs=required&ssl_ca_certs=/etc/zammad/certs/mkcert-rootCA.pem&ssl_check_hostname=true' "$ROOT_DIR/.env.test.example"

success "$my_name" "internal TLS migration validation passed"
