# Create certs for local development and testing. These are used by the local Kong and Keycloak instances, and can be trusted by the local browser to avoid SSL warnings.
# Version: 1.5
# Last modified: 2026-07-14
# Usage: ./scripts/create_certs.sh [--env-file PATH]
#!/usr/bin/env bash
set -euo pipefail

require_cmd() {
	local cmd="$1"
	if ! command -v "$cmd" >/dev/null 2>&1; then
		echo "Missing required command: $cmd" >&2
		exit 1
	fi
}

generate_cert() {
	local cert_file="$1"
	local key_file="$2"
	shift 2

	rm -f "$cert_file" "$key_file"
	mkcert -cert-file "$cert_file" -key-file "$key_file" "$@"
}

write_internal_ca_bundle() {
	local source_file="$1"
	local trust_dir="$CERTS_DIR/trust"
	local aistor_trust_dir="$CERTS_DIR/services/aistor/CAs"

	mkdir -p "$trust_dir"
	mkdir -p "$aistor_trust_dir"
	cp "$source_file" "$CERTS_DIR/internal-ca-bundle.pem"
	cp "$source_file" "$trust_dir/internal-ca-bundle.pem"
	cp "$source_file" "$aistor_trust_dir/internal-ca-bundle.pem"

	# Create placeholder files for the trust-bundle container to overwrite.
	# Compose validates bind mounts before containers start, so these files
	# must exist on the host. The trust-bundle container (runs first via
	# depends_on) will overwrite them with the real JKS/P12 at runtime.
	touch "$trust_dir/trust-bundle.jks"
	touch "$trust_dir/truststore-password.txt"
}

create_openmetadata_keystore() {
	local cert_file="$1"
	local key_file="$2"
	local keystore_file="$CERTS_DIR/openmetadata.p12"
	local keystore_password="changeit"

	rm -f "$keystore_file"

	openssl pkcs12 -export \
		-in "$cert_file" \
		-inkey "$key_file" \
		-name openmetadata \
		-out "$keystore_file" \
		-passout "pass:$keystore_password"
}

generate_service_cert() {
	local service_name="$1"
	shift

	local service_dir="$CERTS_DIR/services/$service_name"
	mkdir -p "$service_dir"
	cp "$CERTS_DIR/mkcert-rootCA.pem" "$service_dir/mkcert-rootCA.pem"
	generate_cert "$service_dir/tls.crt" "$service_dir/tls.key" "$@"
}

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Parse --env-file if given; default to dev env
EXPLICIT_ENV_FILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      EXPLICIT_ENV_FILE="$2"; shift 2 ;;
    --env)
      EXPLICIT_ENV_FILE="$ROOT_DIR/.env.${2}.local"; shift 2 ;;
    *) shift ;;
  esac
done

# Load hostname configuration from the selected env file (or use defaults)
if [ -n "$EXPLICIT_ENV_FILE" ] && [ -f "$EXPLICIT_ENV_FILE" ]; then
  set -a
  source "$EXPLICIT_ENV_FILE"
  set +a
fi

# Env-driven hostnames (fall back to known defaults so the script still works standalone)
EDGE_LOCAL_APP_HOST="${EDGE_LOCAL_APP_HOST:-dq-made-easy.local}"
EDGE_LOCAL_KONG_HOST="${EDGE_LOCAL_KONG_HOST:-kong.local}"
EDGE_LOCAL_KEYCLOAK_HOST="${EDGE_LOCAL_KEYCLOAK_HOST:-keycloak.local}"
EDGE_LOCAL_OPENMETADATA_HOST="${EDGE_LOCAL_OPENMETADATA_HOST:-openmetadata.local}"
EDGE_LOCAL_OBSERVABILITY_HOST="${EDGE_LOCAL_OBSERVABILITY_HOST:-observability.local}"
EDGE_LOCAL_SUPPORT_HOST="${EDGE_LOCAL_SUPPORT_HOST:-support.local}"
EDGE_LOCAL_AIRFLOW_HOST="${EDGE_LOCAL_AIRFLOW_HOST:-airflow.local}"
EDGE_LOCAL_API_HOST="${EDGE_LOCAL_API_HOST:-api.local}"
EDGE_LOCAL_GRAFANA_HOST="${EDGE_LOCAL_GRAFANA_HOST:-grafana.local}"
DQ_ENGINE_EDGE_HOST="${DQ_ENGINE_EDGE_HOST:-engine.local}"
DQ_LLM_EDGE_HOST="${DQ_LLM_EDGE_HOST:-llm.local}"
PUBLIC_CANONICAL_HOST="${PUBLIC_CANONICAL_HOST:-dq-made-easy.local}"
KAFKA_CERT_HOST="${KAFKA_CERT_HOST:-kafka.local}"
DQ_DB_HOST="${DQ_DB_HOST:-db.local}"

# Derive the wildcard domain from the canonical host (e.g. sub.example.com → *.example.com)
EDGE_WILDCARD_HOST="${EDGE_WILDCARD_HOST:-}"
if [ -z "$EDGE_WILDCARD_HOST" ]; then
  # Extract the last two domain parts from PUBLIC_CANONICAL_HOST
  # e.g. "sub.domain.example" → "*.domain.example"
  EDGE_WILDCARD_HOST="*.${PUBLIC_CANONICAL_HOST#*.}"
fi

CERTS_DIR="$ROOT_DIR/tmp/certs"
mkdir -p "$CERTS_DIR"

require_cmd mkcert
require_cmd openssl
# Create a self-signed CA certificate and copy the mkcert root CA for host-side clients.
mkcert -install

mkcert_root_ca="$(mkcert -CAROOT)/rootCA.pem"
if [ ! -f "$mkcert_root_ca" ]; then
	echo "Missing mkcert root CA certificate: $mkcert_root_ca" >&2
	exit 1
fi

cp "$mkcert_root_ca" "$CERTS_DIR/mkcert-rootCA.pem"
write_internal_ca_bundle "$mkcert_root_ca"

# Internal service certificates (DNS names used inside the Docker network)
echo "internal service DNS: api"
generate_service_cert "api" api localhost 127.0.0.1 ::1
echo "internal service DNS: llm"
generate_service_cert "llm" dq-made-easy-llm localhost 127.0.0.1 ::1
echo "internal service DNS: engine"
generate_service_cert "engine" dq-made-easy-engine dq-made-easy-engine.local "$DQ_ENGINE_EDGE_HOST" localhost 127.0.0.1 ::1
echo "internal service DNS: airflow-server"
generate_service_cert "airflow-server" airflow-server localhost 127.0.0.1 ::1
echo "internal service DNS: aistor"
generate_service_cert "aistor" aistor minio dq-made-easy-aistor localhost 127.0.0.1 ::1
cp "$CERTS_DIR/services/aistor/tls.crt" "$CERTS_DIR/services/aistor/public.crt"
cp "$CERTS_DIR/services/aistor/tls.key" "$CERTS_DIR/services/aistor/private.key"
echo "internal service DNS: db"
generate_service_cert "db" db localhost 127.0.0.1 ::1
echo "internal service DNS: grafana"
generate_service_cert "grafana" grafana localhost 127.0.0.1 ::1
echo "internal service DNS: itsm"
generate_service_cert "itsm" itsm localhost 127.0.0.1 ::1
echo "internal service DNS: kafka"
generate_service_cert "kafka" kafka localhost 127.0.0.1 ::1
echo "internal service DNS: kong-db"
generate_service_cert "kong-db" kong-db localhost 127.0.0.1 ::1
echo "internal service DNS: keycloak"
generate_service_cert "keycloak" keycloak "$EDGE_LOCAL_KEYCLOAK_HOST" host.docker.internal localhost 127.0.0.1 ::1
echo "internal service DNS: kong"
generate_service_cert "kong" kong localhost 127.0.0.1 ::1
echo "internal service DNS: observability"
generate_service_cert "observability" observability localhost 127.0.0.1 ::1
echo "internal service DNS: openmetadata-db"
generate_service_cert "openmetadata-db" openmetadata-db localhost 127.0.0.1 ::1
echo "internal service DNS: openmetadata-ingestion"
generate_service_cert "openmetadata-ingestion" openmetadata-ingestion localhost 127.0.0.1 ::1
echo "internal service DNS: openmetadata-search"
generate_service_cert "openmetadata-search" openmetadata-search localhost 127.0.0.1 ::1
echo "internal service DNS: openmetadata-search-v9"
generate_service_cert "openmetadata-search-v9" openmetadata-search-v9 localhost 127.0.0.1 ::1
echo "internal service DNS: openmetadata-server"
generate_service_cert "openmetadata-server" openmetadata-server localhost 127.0.0.1 ::1
echo "internal service DNS: otel-collector"
generate_service_cert "otel-collector" otel-collector dq-made-easy-otel-collector localhost 127.0.0.1 ::1
echo "internal service DNS: redis"
generate_service_cert "redis" redis localhost 127.0.0.1 ::1
echo "internal service DNS: support"
generate_service_cert "support" support localhost 127.0.0.1 ::1
echo "internal service DNS: zammad-railsserver (with edge SNI: ${EDGE_LOCAL_SUPPORT_HOST})"
generate_service_cert "zammad-railsserver" zammad-railsserver "${EDGE_LOCAL_SUPPORT_HOST}" localhost 127.0.0.1 ::1
echo "internal service DNS: zammad-websocket (with edge SNI: ${EDGE_LOCAL_SUPPORT_HOST})"
generate_service_cert "zammad-websocket" zammad-websocket "${EDGE_LOCAL_SUPPORT_HOST}" localhost 127.0.0.1 ::1
echo "internal service DNS: zammad-postgresql"
generate_service_cert "zammad-postgresql" zammad-postgresql localhost 127.0.0.1 ::1

# The compose file mounts ../tmp/certs/services/zammad-db but the cert
# script creates services/zammad-postgresql. Bridge the gap with a symlink.
ZAMMAD_DB_DIR="$CERTS_DIR/services/zammad-db"
if [ ! -e "$ZAMMAD_DB_DIR" ]; then
  ln -s "$(cd "$CERTS_DIR/services/zammad-postgresql" && pwd)" "$ZAMMAD_DB_DIR" 2>/dev/null || true
  echo "Created symlink $ZAMMAD_DB_DIR -> services/zammad-postgresql"
fi

# Edge-facing certificates (public-facing hostnames, env-driven)
echo "edge DNS: ${KAFKA_CERT_HOST}"
generate_cert "$CERTS_DIR/${KAFKA_CERT_HOST}+3.pem" "$CERTS_DIR/${KAFKA_CERT_HOST}+3-key.pem" "${KAFKA_CERT_HOST}" localhost 127.0.0.1 ::1
echo "edge DNS: ${EDGE_LOCAL_SUPPORT_HOST}"
generate_cert "$CERTS_DIR/${EDGE_LOCAL_SUPPORT_HOST}+3.pem" "$CERTS_DIR/${EDGE_LOCAL_SUPPORT_HOST}+3-key.pem" "${EDGE_LOCAL_SUPPORT_HOST}" localhost 127.0.0.1 ::1
echo "edge DNS: ${EDGE_LOCAL_APP_HOST}"
generate_cert "$CERTS_DIR/${EDGE_LOCAL_APP_HOST}+3.pem" "$CERTS_DIR/${EDGE_LOCAL_APP_HOST}+3-key.pem" "${EDGE_LOCAL_APP_HOST}" localhost 127.0.0.1 ::1
echo "edge DNS: ${EDGE_LOCAL_KEYCLOAK_HOST}"
generate_cert "$CERTS_DIR/${EDGE_LOCAL_KEYCLOAK_HOST}+3.pem" "$CERTS_DIR/${EDGE_LOCAL_KEYCLOAK_HOST}+3-key.pem" "${EDGE_LOCAL_KEYCLOAK_HOST}" keycloak "host.docker.internal" localhost 127.0.0.1 ::1
echo "edge DNS: ${EDGE_LOCAL_KONG_HOST}"
generate_cert "$CERTS_DIR/${EDGE_LOCAL_KONG_HOST}+3.pem" "$CERTS_DIR/${EDGE_LOCAL_KONG_HOST}+3-key.pem" "${EDGE_LOCAL_KONG_HOST}" kong localhost 127.0.0.1 ::1
echo "edge DNS: ${EDGE_LOCAL_OBSERVABILITY_HOST}"
generate_cert "$CERTS_DIR/${EDGE_LOCAL_OBSERVABILITY_HOST}+3.pem" "$CERTS_DIR/${EDGE_LOCAL_OBSERVABILITY_HOST}+3-key.pem" "${EDGE_LOCAL_OBSERVABILITY_HOST}" grafana localhost 127.0.0.1 ::1
echo "edge DNS: ${EDGE_LOCAL_API_HOST}"
generate_cert "$CERTS_DIR/${EDGE_LOCAL_API_HOST}+3.pem" "$CERTS_DIR/${EDGE_LOCAL_API_HOST}+3-key.pem" "${EDGE_LOCAL_API_HOST}" localhost 127.0.0.1 ::1
echo "edge DNS: ${EDGE_LOCAL_GRAFANA_HOST}"
generate_cert "$CERTS_DIR/${EDGE_LOCAL_GRAFANA_HOST}+3.pem" "$CERTS_DIR/${EDGE_LOCAL_GRAFANA_HOST}+3-key.pem" "${EDGE_LOCAL_GRAFANA_HOST}" grafana localhost 127.0.0.1 ::1
echo "edge DNS: ${EDGE_LOCAL_OPENMETADATA_HOST}"
generate_cert "$CERTS_DIR/${EDGE_LOCAL_OPENMETADATA_HOST}+3.pem" "$CERTS_DIR/${EDGE_LOCAL_OPENMETADATA_HOST}+3-key.pem" "${EDGE_LOCAL_OPENMETADATA_HOST}" "openmetadata-server" localhost 127.0.0.1 ::1
create_openmetadata_keystore "$CERTS_DIR/${EDGE_LOCAL_OPENMETADATA_HOST}+3.pem" "$CERTS_DIR/${EDGE_LOCAL_OPENMETADATA_HOST}+3-key.pem"
echo "edge DNS: ${EDGE_LOCAL_AIRFLOW_HOST}"
generate_cert "$CERTS_DIR/${EDGE_LOCAL_AIRFLOW_HOST}+3.pem" "$CERTS_DIR/${EDGE_LOCAL_AIRFLOW_HOST}+3-key.pem" "${EDGE_LOCAL_AIRFLOW_HOST}" "airflow-server" localhost 127.0.0.1 ::1

echo "wildcard: ${EDGE_WILDCARD_HOST}"
# Wildcard cert filename uses the base domain (strip the leading *. prefix)
_WILDCARD_BASE="${EDGE_WILDCARD_HOST#*.}"
generate_cert "$CERTS_DIR/${_WILDCARD_BASE}-wildcard.pem" "$CERTS_DIR/${_WILDCARD_BASE}-wildcard-key.pem" "${EDGE_WILDCARD_HOST}" "${_WILDCARD_BASE}" localhost 127.0.0.1 ::1

echo "Certificates created in $CERTS_DIR."
