#!/bin/sh
set -eu

: "${REDIS_URL:?REDIS_URL is required}"
: "${SSL_CERT_FILE:?SSL_CERT_FILE is required}"
: "${CURL_CA_BUNDLE:?CURL_CA_BUNDLE is required}"

max_attempts=60
sleep_seconds=2

cd /opt/zammad

probe_redis() {
  bundle exec ruby -e '
    require "redis"

    redis = Redis.new(
      url: ENV.fetch("REDIS_URL"),
      connect_timeout: 2,
      read_timeout: 2,
      write_timeout: 2,
      reconnect_attempts: 0,
    )

    puts redis.ping
  '
}

attempt=1
while [ "$attempt" -le "$max_attempts" ]; do
  set +e
  probe_output="$(probe_redis 2>&1)"
  probe_rc=$?
  set -e

  if [ "$probe_rc" -eq 0 ]; then
    exec "$@"
  fi

  if [ "$attempt" -eq 1 ] || [ $((attempt % 5)) -eq 0 ]; then
    printf '%s\n' "Waiting for Redis... (${attempt}/${max_attempts})"
    printf '%s\n' "  url=${REDIS_URL}"
    if [ -n "$probe_output" ]; then
      printf '%s\n' "  last error: ${probe_output}"
    fi
  fi

  attempt=$((attempt + 1))
  sleep "$sleep_seconds"
done

printf '%s\n' "Redis did not become ready after ${max_attempts} attempts" >&2
printf '%s\n' "  url=${REDIS_URL}" >&2
if [ -n "${probe_output:-}" ]; then
  printf '%s\n' "  last error: ${probe_output}" >&2
fi
exit 1