#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"

source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="profiling_validation_common.sh"

PROFILING_API_BASE="${DQ_API_LOCAL_URL:?DQ_API_LOCAL_URL is required}"
PROFILING_API_URL="${PROFILING_API_BASE%/}/rulebuilder/v1/profiling/enqueue"
DATABASE_NAME="${DATABASE_NAME:-dq}"
DATABASE_USER="${DATABASE_USER:-postgres}"
PROFILING_DB_CONTAINER="${PROFILING_DB_CONTAINER:-}"
PROFILING_WORKER_CONTAINER="${PROFILING_WORKER_CONTAINER:-${WORKER_CONTAINER:-${COMPOSE_PROJECT_NAME:-dq-made-easy}-profiling-worker-1}}"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: ${cmd}"
    exit 1
  fi
}

_running_container_for_service() {
  local service_name="$1"
  docker ps -q --filter "label=com.docker.compose.service=${service_name}" | head -1
}

db_psql_query() {
  local sql="$1"
  local db_container_id

  if [[ -n "$PROFILING_DB_CONTAINER" ]]; then
    docker exec "$PROFILING_DB_CONTAINER" psql -U "$DATABASE_USER" -d "$DATABASE_NAME" -At -c "$sql"
    return 0
  fi

  db_container_id="$(_running_container_for_service db)"
  if [[ -n "$db_container_id" ]]; then
    docker exec "$db_container_id" psql -U "$DATABASE_USER" -d "$DATABASE_NAME" -At -c "$sql"
    return 0
  fi

  if docker inspect "$PROFILING_WORKER_CONTAINER" >/dev/null 2>&1; then
    :
  fi

  error "$my_name" "Could not resolve a running Postgres target for profiling validation"
  exit 1
}

db_psql_exec() {
  local sql="$1"
  local db_container_id

  if [[ -n "$PROFILING_DB_CONTAINER" ]]; then
    docker exec "$PROFILING_DB_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$DATABASE_USER" -d "$DATABASE_NAME" -c "$sql" >/dev/null
    return 0
  fi

  db_container_id="$(_running_container_for_service db)"
  if [[ -n "$db_container_id" ]]; then
    docker exec "$db_container_id" psql -v ON_ERROR_STOP=1 -U "$DATABASE_USER" -d "$DATABASE_NAME" -c "$sql" >/dev/null
    return 0
  fi

  error "$my_name" "Could not resolve a running Postgres target for profiling validation"
  exit 1
}

resolve_fk_defaults() {
  if [[ -z "${DATA_SOURCE_ID:-}" ]]; then
    DATA_SOURCE_ID="$(db_psql_query "select data_source_id from data_source_metadata order by id limit 1;" | head -n 1)"
  fi

  if [[ -z "${REQUESTED_BY_USER_ID:-}" ]]; then
    REQUESTED_BY_USER_ID="$(db_psql_query "select id from users order by id limit 1;" | head -n 1)"
  fi

  if [[ -z "$DATA_SOURCE_ID" || -z "$REQUESTED_BY_USER_ID" ]]; then
    error "$my_name" "Unable to resolve FK-safe profiling defaults from the running database"
    exit 1
  fi
}

profiling_worker_logs() {
  local since_seconds="$1"
  local worker_cid

  worker_cid="$(_running_container_for_service profiling-worker)"
  if [[ -n "$worker_cid" ]]; then
    docker logs --since "${since_seconds}s" "$worker_cid" 2>&1
    return 0
  fi

  docker logs --since "${since_seconds}s" "$PROFILING_WORKER_CONTAINER" 2>&1
}