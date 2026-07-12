#!/bin/sh
set -eu

: "${REDIS_URL:?REDIS_URL is required}"

cd /opt/zammad

max_attempts=60
sleep_seconds=2

attempt=1
while [ "$attempt" -le "$max_attempts" ]; do
  set +e
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
  ' >/dev/null 2>&1
  probe_rc=$?
  set -e

  if [ "$probe_rc" -eq 0 ]; then
    printf '%s\n' "Redis is ready, running zammad-init..."
    exec bash /opt/zammad/bin/docker-entrypoint zammad-init
  fi

  if [ "$attempt" -eq 1 ] || [ $((attempt % 5)) -eq 0 ]; then
    printf '%s\n' "Waiting for Redis... (${attempt}/${max_attempts})"
  fi

  attempt=$((attempt + 1))
  sleep "$sleep_seconds"
done

printf '%s\n' "Redis did not become ready after ${max_attempts} attempts" >&2
exit 1
