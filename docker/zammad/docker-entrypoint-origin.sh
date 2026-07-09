#!/bin/sh
set -eu

cert_dir="${ZAMMAD_SSL_CERTS_DIR:-/etc/nginx/certs}"
cert_file_name="${ZAMMAD_SSL_CERT_FILE_NAME:?Missing ZAMMAD_SSL_CERT_FILE_NAME}"
key_file_name="${ZAMMAD_SSL_KEY_FILE_NAME:?Missing ZAMMAD_SSL_KEY_FILE_NAME}"

cert_file="${cert_dir}/${cert_file_name}"
key_file="${cert_dir}/${key_file_name}"

if [ ! -f "${cert_file}" ]; then
  echo "Missing Zammad TLS certificate: ${cert_file}" >&2
  exit 1
fi

if [ ! -f "${key_file}" ]; then
  echo "Missing Zammad TLS private key: ${key_file}" >&2
  exit 1
fi

mkdir -p /tmp/zammad-origin-certs
ln -sf "${cert_file}" /tmp/zammad-origin-certs/zammad-origin.crt
ln -sf "${key_file}" /tmp/zammad-origin-certs/zammad-origin.key

exec /opt/zammad/bin/docker-entrypoint "$@"