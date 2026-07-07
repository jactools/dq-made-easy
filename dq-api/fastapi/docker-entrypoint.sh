#!/usr/bin/env bash
set -euo pipefail

# Entrypoint for API image:
# - start uvicorn after the compose-level api-migrate one-shot service has
#   applied Alembic migrations.

ROOT_DIR="/app"
API_HTTPS_CERT_FILE="${API_HTTPS_CERT_FILE:-/etc/api/certs/tls.crt}"
API_HTTPS_KEY_FILE="${API_HTTPS_KEY_FILE:-/etc/api/certs/tls.key}"

cd "$ROOT_DIR"

if [ ! -f "$API_HTTPS_CERT_FILE" ]; then
	echo "Missing API HTTPS certificate: $API_HTTPS_CERT_FILE" >&2
	exit 1
fi

if [ ! -f "$API_HTTPS_KEY_FILE" ]; then
	echo "Missing API HTTPS key: $API_HTTPS_KEY_FILE" >&2
	exit 1
fi

echo "Starting uvicorn with HTTPS"
uvicorn app.main:app --host 0.0.0.0 --port 4010 --ssl-certfile "$API_HTTPS_CERT_FILE" --ssl-keyfile "$API_HTTPS_KEY_FILE"
