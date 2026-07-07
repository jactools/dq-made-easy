# Create certs for local development and testing. These are used by the local Kong and Keycloak instances, and can be trusted by the local browser to avoid SSL warnings.
# Version: 1.4
# Last modified: 2026-04-25
# Usage: ./scripts/create_certs.sh
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

	mkdir -p "$trust_dir"
	cp "$source_file" "$CERTS_DIR/internal-ca-bundle.pem"
	cp "$source_file" "$trust_dir/internal-ca-bundle.pem"
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
	generate_cert "$service_dir/tls.crt" "$service_dir/tls.key" "$@"
}

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
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

echo "internal service DNS: api"
generate_service_cert "api" api localhost 127.0.0.1 ::1
echo "internal service DNS: airflow-server"
generate_service_cert "airflow-server" airflow-server localhost 127.0.0.1 ::1
echo "internal service DNS: aistor"
generate_service_cert "aistor" aistor minio dq-made-easy-aistor localhost 127.0.0.1 ::1
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
generate_service_cert "keycloak" keycloak keycloak.jac.dot host.docker.internal localhost 127.0.0.1 ::1
echo "internal service DNS: kong"
generate_service_cert "kong" kong localhost 127.0.0.1 ::1
echo "internal service DNS: observability"
generate_service_cert "observability" observability localhost 127.0.0.1 ::1
echo "internal service DNS: openmetadata-db"
generate_service_cert "openmetadata-db" openmetadata-db localhost 127.0.0.1 ::1
echo "internal service DNS: openmetadata-ingestion"
generate_service_cert "openmetadata-ingestion" openmetadata-ingestion localhost 127.0.0.1 ::1
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

echo "kafka.jac.dot"
generate_cert "$CERTS_DIR/kafka.jac.dot+3.pem" "$CERTS_DIR/kafka.jac.dot+3-key.pem" "kafka.jac.dot" localhost 127.0.0.1 ::1
echo "itsm.jac.dot"
generate_cert "$CERTS_DIR/itsm.jac.dot+3.pem" "$CERTS_DIR/itsm.jac.dot+3-key.pem" "itsm.jac.dot" localhost 127.0.0.1 ::1
echo "support.jac.dot"
generate_cert "$CERTS_DIR/support.jac.dot+3.pem" "$CERTS_DIR/support.jac.dot+3-key.pem" "support.jac.dot" localhost 127.0.0.1 ::1
echo "dq-made-easy.jac.dot"
generate_cert "$CERTS_DIR/dq-made-easy.jac.dot+3.pem" "$CERTS_DIR/dq-made-easy.jac.dot+3-key.pem" "dq-made-easy.jac.dot" localhost 127.0.0.1 ::1
echo "keycloak.jac.dot"
generate_cert "$CERTS_DIR/keycloak.jac.dot+3.pem" "$CERTS_DIR/keycloak.jac.dot+3-key.pem" "keycloak.jac.dot" keycloak "host.docker.internal" localhost 127.0.0.1 ::1
echo "kong.jac.dot"
generate_cert "$CERTS_DIR/kong.jac.dot+3.pem" "$CERTS_DIR/kong.jac.dot+3-key.pem" "kong.jac.dot" localhost 127.0.0.1 ::1
echo "observability.jac.dot"
generate_cert "$CERTS_DIR/observability.jac.dot+3.pem" "$CERTS_DIR/observability.jac.dot+3-key.pem" "observability.jac.dot" localhost 127.0.0.1 ::1
echo "api.jac.dot"
generate_cert "$CERTS_DIR/api.jac.dot+3.pem" "$CERTS_DIR/api.jac.dot+3-key.pem" "api.jac.dot" localhost 127.0.0.1 ::1
echo "grafana.jac.dot"
generate_cert "$CERTS_DIR/grafana.jac.dot+3.pem" "$CERTS_DIR/grafana.jac.dot+3-key.pem" "grafana.jac.dot" localhost 127.0.0.1 ::1
echo "openmetadata.jac.dot"
generate_cert "$CERTS_DIR/openmetadata.jac.dot+3.pem" "$CERTS_DIR/openmetadata.jac.dot+3-key.pem" "openmetadata.jac.dot" "openmetadata-server" localhost 127.0.0.1 ::1
create_openmetadata_keystore "$CERTS_DIR/openmetadata.jac.dot+3.pem" "$CERTS_DIR/openmetadata.jac.dot+3-key.pem"
echo "airflow.jac.dot"
generate_cert "$CERTS_DIR/airflow.jac.dot+3.pem" "$CERTS_DIR/airflow.jac.dot+3-key.pem" "airflow.jac.dot" "airflow-server" localhost 127.0.0.1 ::1

echo "*.jac.dot"
generate_cert "$CERTS_DIR/jac.dot-wildcard.pem" "$CERTS_DIR/jac.dot-wildcard-key.pem" "*.jac.dot" "jac.dot" localhost 127.0.0.1 ::1

echo "Certificates created in $CERTS_DIR."
