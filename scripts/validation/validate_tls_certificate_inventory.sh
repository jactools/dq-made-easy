#!/usr/bin/env bash
set -euo pipefail

# Purpose: Verify the TLS certificate inventory required by the repository-managed stack.
# What it does:
# - Confirms the mkcert root CA and shared trust bundle exist.
# - Confirms every TLS listener used by the supported stack has a leaf cert and key.
# - Fails fast before startup or health probing if a cert artifact is missing.
# validate: groups=repo
# validate: include=true
# Version: 1.0
# Last modified: 2026-07-08

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_tls_certificate_inventory.sh"

require_file() {
  local file_path="$1"
  if [[ ! -f "$file_path" ]]; then
    error "$my_name" "missing required certificate artifact: $file_path"
    exit 1
  fi
}

require_dir() {
  local dir_path="$1"
  if [[ ! -d "$dir_path" ]]; then
    error "$my_name" "missing required certificate directory: $dir_path"
    exit 1
  fi
}

require_file "$ROOT_DIR/tmp/certs/mkcert-rootCA.pem"
require_file "$ROOT_DIR/tmp/certs/internal-ca-bundle.pem"
require_file "$ROOT_DIR/tmp/certs/trust/internal-ca-bundle.pem"

assert_dns_san() {
  local cert_file="$1"
  local expected_dns="$2"

  if ! openssl x509 -in "$cert_file" -noout -text | grep -Fq "DNS:$expected_dns"; then
    error "$my_name" "missing DNS SAN '$expected_dns' in $cert_file"
    exit 1
  fi
}

assert_service_leaf_sans() {
  local service_name="$1"
  local cert_file="$ROOT_DIR/tmp/certs/services/$service_name/tls.crt"

  case "$service_name" in
    api)
      assert_dns_san "$cert_file" api
      assert_dns_san "$cert_file" localhost
      ;;
    engine)
      assert_dns_san "$cert_file" dq-made-easy-engine
      assert_dns_san "$cert_file" dq-made-easy-engine.local
      assert_dns_san "$cert_file" dq-made-easy-engine.jac.dot
      assert_dns_san "$cert_file" localhost
      ;;
    airflow-server)
      assert_dns_san "$cert_file" airflow-server
      assert_dns_san "$cert_file" localhost
      ;;
    aistor)
      assert_dns_san "$cert_file" aistor
      assert_dns_san "$cert_file" minio
      assert_dns_san "$cert_file" dq-made-easy-aistor
      assert_dns_san "$cert_file" localhost
      require_file "$ROOT_DIR/tmp/certs/services/aistor/public.crt"
      require_file "$ROOT_DIR/tmp/certs/services/aistor/private.key"
      ;;
    db)
      assert_dns_san "$cert_file" db
      assert_dns_san "$cert_file" localhost
      ;;
    grafana)
      assert_dns_san "$cert_file" grafana
      assert_dns_san "$cert_file" localhost
      ;;
    itsm)
      assert_dns_san "$cert_file" itsm
      assert_dns_san "$cert_file" localhost
      ;;
    kafka)
      assert_dns_san "$cert_file" kafka
      assert_dns_san "$cert_file" localhost
      ;;
    kong-db)
      assert_dns_san "$cert_file" kong-db
      assert_dns_san "$cert_file" localhost
      ;;
    keycloak)
      assert_dns_san "$cert_file" keycloak
      assert_dns_san "$cert_file" keycloak.jac.dot
      assert_dns_san "$cert_file" host.docker.internal
      assert_dns_san "$cert_file" localhost
      ;;
    kong)
      assert_dns_san "$cert_file" kong
      assert_dns_san "$cert_file" localhost
      ;;
    observability)
      assert_dns_san "$cert_file" observability
      assert_dns_san "$cert_file" localhost
      ;;
    openmetadata-db)
      assert_dns_san "$cert_file" openmetadata-db
      assert_dns_san "$cert_file" localhost
      ;;
    openmetadata-ingestion)
      assert_dns_san "$cert_file" openmetadata-ingestion
      assert_dns_san "$cert_file" localhost
      ;;
    openmetadata-search)
      assert_dns_san "$cert_file" openmetadata-search
      assert_dns_san "$cert_file" localhost
      ;;
    openmetadata-search-v9)
      assert_dns_san "$cert_file" openmetadata-search-v9
      assert_dns_san "$cert_file" localhost
      ;;
    openmetadata-server)
      assert_dns_san "$cert_file" openmetadata-server
      assert_dns_san "$cert_file" localhost
      ;;
    otel-collector)
      assert_dns_san "$cert_file" otel-collector
      assert_dns_san "$cert_file" dq-made-easy-otel-collector
      assert_dns_san "$cert_file" localhost
      ;;
    redis)
      assert_dns_san "$cert_file" redis
      assert_dns_san "$cert_file" localhost
      ;;
    support)
      assert_dns_san "$cert_file" support
      assert_dns_san "$cert_file" localhost
      ;;
    *)
      error "$my_name" "no SAN expectations configured for service leaf cert: $service_name"
      exit 1
      ;;
  esac
}

for service_name in \
  api \
  engine \
  airflow-server \
  aistor \
  db \
  grafana \
  itsm \
  kafka \
  kong-db \
  keycloak \
  kong \
  observability \
  openmetadata-db \
  openmetadata-ingestion \
  openmetadata-search \
  openmetadata-search-v9 \
  openmetadata-server \
  otel-collector \
  redis \
  support
do
  require_dir "$ROOT_DIR/tmp/certs/services/$service_name"
  require_file "$ROOT_DIR/tmp/certs/services/$service_name/tls.crt"
  require_file "$ROOT_DIR/tmp/certs/services/$service_name/tls.key"
  assert_service_leaf_sans "$service_name"
done

for file_name in \
  kafka.jac.dot+3.pem \
  kafka.jac.dot+3-key.pem \
  itsm.jac.dot+3.pem \
  itsm.jac.dot+3-key.pem \
  support.jac.dot+3.pem \
  support.jac.dot+3-key.pem \
  dq-made-easy.jac.dot+3.pem \
  dq-made-easy.jac.dot+3-key.pem \
  keycloak.jac.dot+3.pem \
  keycloak.jac.dot+3-key.pem \
  kong.jac.dot+3.pem \
  kong.jac.dot+3-key.pem \
  observability.jac.dot+3.pem \
  observability.jac.dot+3-key.pem \
  api.jac.dot+3.pem \
  api.jac.dot+3-key.pem \
  grafana.jac.dot+3.pem \
  grafana.jac.dot+3-key.pem \
  openmetadata.jac.dot+3.pem \
  openmetadata.jac.dot+3-key.pem \
  airflow.jac.dot+3.pem \
  airflow.jac.dot+3-key.pem \
  jac.dot-wildcard.pem \
  jac.dot-wildcard-key.pem \
  openmetadata.p12
do
  require_file "$ROOT_DIR/tmp/certs/$file_name"
done

for browser_cert in \
  api.jac.dot+3.pem:api.jac.dot \
  itsm.jac.dot+3.pem:itsm.jac.dot \
  support.jac.dot+3.pem:support.jac.dot \
  dq-made-easy.jac.dot+3.pem:dq-made-easy.jac.dot \
  keycloak.jac.dot+3.pem:keycloak.jac.dot \
  kong.jac.dot+3.pem:kong.jac.dot \
  observability.jac.dot+3.pem:observability.jac.dot \
  api.jac.dot+3.pem:api.jac.dot \
  grafana.jac.dot+3.pem:grafana.jac.dot \
  openmetadata.jac.dot+3.pem:openmetadata.jac.dot \
  airflow.jac.dot+3.pem:airflow.jac.dot \
  jac.dot-wildcard.pem:*.jac.dot
do
  cert_file="${browser_cert%%:*}"
  expected_dns="${browser_cert#*:}"
  assert_dns_san "$ROOT_DIR/tmp/certs/$cert_file" "$expected_dns"
done

success "$my_name" "TLS certificate inventory is complete"