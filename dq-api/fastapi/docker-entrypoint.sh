#!/usr/bin/env bash
set -euo pipefail

# Entrypoint for API image:
# - start uvicorn after the compose-level api-migrate one-shot service has
#   applied Alembic migrations.

ROOT_DIR="/app"
API_HTTPS_CERT_FILE="${API_HTTPS_CERT_FILE:-/etc/api/certs/tls.crt}"
API_HTTPS_KEY_FILE="${API_HTTPS_KEY_FILE:-/etc/api/certs/tls.key}"
API_HTTPS_ENABLED="${API_HTTPS_ENABLED:-true}"

cd "$ROOT_DIR"

if [ "$API_HTTPS_ENABLED" = "true" ]; then
	if [ ! -f "$API_HTTPS_CERT_FILE" ]; then
		echo "Missing API HTTPS certificate: $API_HTTPS_CERT_FILE" >&2
		exit 1
	fi

	if [ ! -f "$API_HTTPS_KEY_FILE" ]; then
		echo "Missing API HTTPS key: $API_HTTPS_KEY_FILE" >&2
		exit 1
	fi

	echo "Starting uvicorn with HTTPS"
	exec uvicorn app.main:app --host 0.0.0.0 --port 4010 --ssl-certfile "$API_HTTPS_CERT_FILE" --ssl-keyfile "$API_HTTPS_KEY_FILE"
fi

echo "Starting uvicorn with HTTP"
exec uvicorn app.main:app --host 0.0.0.0 --port 4010
