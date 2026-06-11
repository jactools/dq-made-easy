#!/usr/bin/env bash
set -euo pipefail

# Purpose: Start OpenMetadata with native HTTPS enabled.
# What it does:
# - Verifies the OpenMetadata keystore exists inside the container.
# - Rewrites the stock OpenMetadata server config to use HTTPS.
# - Launches the upstream OpenMetadata server startup script.
# Version: 1.1
# Last modified: 2026-04-16

CONFIG_FILE="${OPENMETADATA_CONFIG_FILE:-/opt/openmetadata/conf/openmetadata.yaml}"
KEYSTORE_PATH="${OPENMETADATA_KEYSTORE_PATH:-/opt/openmetadata/conf/openmetadata.p12}"

if [ ! -f "$KEYSTORE_PATH" ]; then
  echo "Missing OpenMetadata keystore: $KEYSTORE_PATH" >&2
  exit 1
fi

if ! grep -q '^      keyStorePath: ./conf/openmetadata.p12$' "$CONFIG_FILE"; then
  tmp_config="$(mktemp "${CONFIG_FILE}.XXXXXX")"

  awk '
    BEGIN {
      in_connectors = 0
      replaced = 0
    }

    /^[[:space:]]*applicationConnectors:/ {
      print
      print "    - type: https"
      print "      bindHost: ${SERVER_HOST:-0.0.0.0}"
      print "      port: ${SERVER_PORT:-8585}"
      print "      keyStorePath: ./conf/openmetadata.p12"
      print "      keyStorePassword: changeit"
      print "      keyStoreType: PKCS12"
      print "      supportedProtocols: [TLSv1.2, TLSv1.3]"
      print "      excludedProtocols: [SSL, SSLv2, SSLv2Hello, SSLv3]"
      print "      uriCompliance: UNSAFE"
      print "      acceptorThreads: ${SERVER_ACCEPTOR_THREADS:-2}"
      print "      selectorThreads: ${SERVER_SELECTOR_THREADS:-8}"
      print "      acceptQueueSize: ${SERVER_ACCEPT_QUEUE_SIZE:-256}"
      print "      idleTimeout: ${SERVER_IDLE_TIMEOUT:-60 seconds}"
      print "      outputBufferSize: ${SERVER_OUTPUT_BUFFER_SIZE:-32KiB}"
      print "      inputBufferSize: ${SERVER_INPUT_BUFFER_SIZE:-8KiB}"
      print "      maxRequestHeaderSize: ${SERVER_MAX_REQUEST_HEADER_SIZE:-8KiB}"
      print "      maxResponseHeaderSize: ${SERVER_MAX_RESPONSE_HEADER_SIZE:-8KiB}"
      print "      headerCacheSize: ${SERVER_HEADER_CACHE_SIZE:-512B}"
      print "      useServerHeader: false"
      print "      useDateHeader: true"
      print "      useForwardedHeaders: ${SERVER_USE_FORWARDED_HEADERS:-false}"
      print "      minRequestDataPerSecond: ${SERVER_MIN_REQUEST_DATA_RATE:-0B}"
      print "      minResponseDataPerSecond: ${SERVER_MIN_RESPONSE_DATA_RATE:-0B}"
      in_connectors = 1
      replaced = 1
      next
    }

    in_connectors && /^[[:space:]]*adminConnectors:/ {
      in_connectors = 0
      print
      next
    }

    in_connectors {
      next
    }

    {
      print
    }

    END {
      if (replaced == 0) {
        exit 1
      }
    }
  ' "$CONFIG_FILE" >"$tmp_config"

  mv "$tmp_config" "$CONFIG_FILE"
fi

cd /opt/openmetadata
exec ./bin/openmetadata-server-start.sh conf/openmetadata.yaml
