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

if [ "$1" = "zammad-nginx" ]; then
  # Run readiness checks ourselves; do NOT delegate to the upstream entrypoint
  # because its sed corrupts "proxy_ssl_server_name on" -> "proxy_ssl_server_name <fqdn>"
  # due to the greedy pattern: s#server_name .*#server_name ${NGINX_SERVER_NAME}#g

  # Check PostgreSQL
  echo 'Checking if PostgreSQL is ready...'
  CLEAN_POSTGRESQL_HOST="${POSTGRESQL_HOST#[}"
  CLEAN_POSTGRESQL_HOST="${CLEAN_POSTGRESQL_HOST%]}"
  until pg_isready -q -h "$CLEAN_POSTGRESQL_HOST" -p "$POSTGRESQL_PORT"; do
    echo "  waiting for postgresql server to be ready..."
    sleep 1
  done

  # Check Zammad is ready (migrations + seeds done)
  echo 'Checking if Zammad is ready...'
  until bundle exec rails r 'ActiveRecord::Migration.check_all_pending!; Translation.any? || raise' &> /dev/null; do
    echo "  waiting for init container to finish install or update..."
    sleep 2
  done

  # Install our pre-configured SSL nginx config (no upstream sed needed)
  cp /opt/zammad/contrib/nginx/zammad.conf /etc/nginx/sites-enabled/default

  echo "starting nginx..."
  exec /usr/sbin/nginx -g 'daemon off;'
fi

# For non-nginx commands, delegate to the upstream entrypoint
exec /opt/zammad/bin/docker-entrypoint "$@"
