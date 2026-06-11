#!/usr/bin/env bash

# Purpose: Shared readiness and health polling helpers for stack orchestration.
#
# What it does:
# - Polls HTTP endpoints until an acceptable status code is returned.
# - Waits for Kong proxy health via the host-local probe helper.
# - Waits for Zammad support containers and application database readiness.
# - Fails fast when required commands or dependencies are unavailable.
#
# Version: 1.0
# Last modified: 2026-05-08

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"

readiness_status_matches() {
  local candidate="$1"
  local acceptable_codes_csv="$2"
  local acceptable_code
  local IFS=','

  for acceptable_code in $acceptable_codes_csv; do
    if [ "$candidate" = "$acceptable_code" ]; then
      return 0
    fi
  done

  return 1
}

wait_for_http_ready() {
  local service_label="$1"
  local ready_url="$2"
  local acceptable_codes_csv="$3"
  local max_attempts="${4:-30}"
  local sleep_seconds="${5:-1}"
  shift 5

  local probe_command=("$@")
  local attempt
  local probe_output
  local probe_rc
  local http_code=""
  local last_error=""

  if [ "${#probe_command[@]}" -eq 0 ]; then
    probe_command=(curl -sS -o /dev/null -w '%{http_code}')
  fi

  if ! command -v "${probe_command[0]}" >/dev/null 2>&1; then
    error "readiness.sh" "${service_label} readiness helper requires command: ${probe_command[0]}"
    return 127
  fi

  for attempt in $(seq 1 "$max_attempts"); do
    set +e
    probe_output="$("${probe_command[@]}" "$ready_url" 2>&1)"
    probe_rc=$?
    set -e

    http_code="$(printf '%s' "$probe_output" | tr -d '\r\n')"
    if [ "$probe_rc" -eq 0 ] && readiness_status_matches "$http_code" "$acceptable_codes_csv"; then
      return 0
    fi

    if [ "$probe_rc" -ne 0 ]; then
      last_error="$probe_output"
      http_code="000"
    else
      last_error=""
    fi

    if (( attempt % 10 == 0 )); then
      info "readiness.sh" "Waiting for ${service_label}... (${attempt}/${max_attempts})"
      info "readiness.sh" "  last status: code=${http_code} rc=${probe_rc} url=${ready_url}"
      if [ -n "$last_error" ]; then
        info "readiness.sh" "  last error: ${last_error}"
      fi
    fi

    sleep "$sleep_seconds"
  done

  error "readiness.sh" "${service_label} did not become ready after ${max_attempts} attempts"
  error "readiness.sh" "  last status: code=${http_code:-000} rc=${probe_rc:-1} url=${ready_url}"
  error "readiness.sh" "  acceptable codes: ${acceptable_codes_csv}"
  if [ -n "$last_error" ]; then
    error "readiness.sh" "  last error: ${last_error}"
  fi

  return 1
}

wait_for_kong_admin_ready() {
  local ready_url="$1"
  local service_label="${2:-Kong Admin API}"
  local max_attempts="${3:-30}"
  local sleep_seconds="${4:-1}"

  wait_for_http_ready "$service_label" "$ready_url" "200" "$max_attempts" "$sleep_seconds" curl -sS -o /dev/null -w '%{http_code}'
}

wait_for_kong_proxy_ready() {
  local ready_url="$1"
  local service_label="${2:-Kong Gateway}"
  local max_attempts="${3:-30}"
  local sleep_seconds="${4:-1}"

  if ! command -v curl_kong_host_probe >/dev/null 2>&1; then
    error "readiness.sh" "Kong proxy readiness requires curl_kong_host_probe from scripts/supporting/setup_env.sh"
    return 127
  fi

  wait_for_http_ready "$service_label" "$ready_url" "200,401" "$max_attempts" "$sleep_seconds" curl_kong_host_probe --max-time 2 -sS -o /dev/null -w '%{http_code}'
}

find_running_container_id() {
  local service_name="$1"

  docker ps \
    --filter "label=com.docker.compose.service=${service_name}" \
    --format '{{.ID}}' \
    | head -n 1
}

wait_for_zammad_support_services_ready() {
  local max_attempts="${1:-60}"
  local sleep_seconds="${2:-2}"
  local attempt
  local zammad_postgres_id
  local redis_id
  local memcached_id
  local railsserver_id
  local postgres_health
  local redis_health
  local memcached_running
  local railsserver_running

  if ! command -v docker >/dev/null 2>&1; then
    error "readiness.sh" "docker is required for Zammad readiness checks"
    return 127
  fi

  for attempt in $(seq 1 "$max_attempts"); do
    zammad_postgres_id="$(find_running_container_id zammad-postgresql)"
    redis_id="$(find_running_container_id redis)"
    memcached_id="$(find_running_container_id zammad-memcached)"
    railsserver_id="$(find_running_container_id zammad-railsserver)"

    postgres_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$zammad_postgres_id" 2>/dev/null || true)"
    redis_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$redis_id" 2>/dev/null || true)"
    memcached_running="$(docker inspect -f '{{.State.Running}}' "$memcached_id" 2>/dev/null || true)"
    railsserver_running="$(docker inspect -f '{{.State.Running}}' "$railsserver_id" 2>/dev/null || true)"

    if [ "$postgres_health" = "healthy" ] \
      && [ "$redis_health" = "healthy" ] \
      && [ "$memcached_running" = "true" ] \
      && [ "$railsserver_running" = "true" ]; then
      return 0
    fi

    if (( attempt % 10 == 0 )); then
      info "readiness.sh" "Waiting for Zammad support services... (${attempt}/${max_attempts})"
      info "readiness.sh" "  postgres=${postgres_health:-missing} redis=${redis_health:-missing} memcached=${memcached_running:-missing} railsserver=${railsserver_running:-missing}"
    fi

    sleep "$sleep_seconds"
  done

  error "readiness.sh" "Zammad support services did not become ready in time"
  error "readiness.sh" "  postgres=${postgres_health:-missing} redis=${redis_health:-missing} memcached=${memcached_running:-missing} railsserver=${railsserver_running:-missing}"
  return 1
}

wait_for_zammad_app_database_ready() {
  local database_url="${1:-${DQ_DB_INTERNAL_URL:-}}"
  local max_attempts="${2:-60}"
  local sleep_seconds="${3:-2}"
  local attempt

  if [ -z "$database_url" ]; then
    error "readiness.sh" "DQ_DB_INTERNAL_URL is required for Zammad database readiness checks"
    return 1
  fi

  if ! command -v python >/dev/null 2>&1; then
    error "readiness.sh" "python is required for Zammad database readiness checks"
    return 127
  fi

  for attempt in $(seq 1 "$max_attempts"); do
    if DQ_DB_INTERNAL_URL="$database_url" python - <<'PY' >/dev/null 2>&1
import os
import psycopg

conn = psycopg.connect(os.environ["DQ_DB_INTERNAL_URL"])
conn.close()
PY
    then
      return 0
    fi

    if (( attempt % 10 == 0 )); then
      info "readiness.sh" "Waiting for application database... (${attempt}/${max_attempts})"
      info "readiness.sh" "  database_url=${database_url}"
    fi

    sleep "$sleep_seconds"
  done

  error "readiness.sh" "Application database did not become ready in time"
  error "readiness.sh" "  database_url=${database_url}"
  return 1
}