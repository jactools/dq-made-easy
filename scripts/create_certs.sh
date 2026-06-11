# Create certs for local development and testing. These are used by the local Kong and Keycloak instances, and can be trusted by the local browser to avoid SSL warnings.
# Version: 1.3
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

echo "support.jac.dot"
generate_cert "$CERTS_DIR/support.jac.dot+3.pem" "$CERTS_DIR/support.jac.dot+3-key.pem" "support.jac.dot" localhost 127.0.0.1 ::1
echo "dq-made-easy.jac.dot"
generate_cert "$CERTS_DIR/dq-made-easy.jac.dot+3.pem" "$CERTS_DIR/dq-made-easy.jac.dot+3-key.pem" "dq-made-easy.jac.dot" localhost 127.0.0.1 ::1
echo "keycloak.jac.dot"
generate_cert "$CERTS_DIR/keycloak.jac.dot+3.pem" "$CERTS_DIR/keycloak.jac.dot+3-key.pem" "keycloak.jac.dot" "host.docker.internal" localhost 127.0.0.1 ::1
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
