#!/usr/bin/env bash
set -euo pipefail

if [[ "${KAFKA_TLS_ENABLED:-true}" == "true" ]]; then
  cert_file="${KAFKA_TLS_CERT_FILE:-/etc/kafka/certs/kafka.jac.dot+3.pem}"
  key_file="${KAFKA_TLS_KEY_FILE:-/etc/kafka/certs/kafka.jac.dot+3-key.pem}"
  keystore_password="${KAFKA_TLS_KEYSTORE_PASSWORD:-changeit}"
  keystore_file="/etc/kafka/secrets/kafka.keystore.p12"
  keystore_creds_file="/etc/kafka/secrets/kafka_keystore_creds"
  key_creds_file="/etc/kafka/secrets/kafka_key_creds"

  if [[ ! -f "$cert_file" ]]; then
    echo "Kafka TLS cert file not found: $cert_file" >&2
    exit 1
  fi

  if [[ ! -f "$key_file" ]]; then
    echo "Kafka TLS key file not found: $key_file" >&2
    exit 1
  fi

  mkdir -p /etc/kafka/secrets

  openssl pkcs12 -export \
    -in "$cert_file" \
    -inkey "$key_file" \
    -name kafka \
    -out "$keystore_file" \
    -passout "pass:$keystore_password"

  printf '%s' "$keystore_password" > "$keystore_creds_file"
  printf '%s' "$keystore_password" > "$key_creds_file"
  chmod 600 "$keystore_file" "$keystore_creds_file" "$key_creds_file"
fi

exec /etc/kafka/docker/run "$@"
