# Purpose: Provide shared docker compose invocation helpers for shell scripts.
#
# What it does:
# - Wraps docker compose with the selected repo env file.
# - Fails fast when the env file has not been selected yet.
# - Keeps compose invocation consistent across startup and seeding scripts.
#
# Version: 1.0
# Last modified: 2026-05-08

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

docker_compose() {
  if [ -z "${ROOT_ENV_FILE:-}" ]; then
    error "compose/invocation.sh" "ROOT_ENV_FILE must be set before calling docker_compose"
    return 1
  fi

  docker compose --env-file "$ROOT_ENV_FILE" "$@"
}

wait_for_compose_service_healthy() {
  local service_name="$1"
  local service_label="${2:-$1}"
  local max_attempts="${3:-60}"
  local sleep_seconds="${4:-2}"
  local attempt
  local container_ids
  local container_id
  local container_status
  local health_status
  local all_ready

  if ! command -v docker >/dev/null 2>&1; then
    error "compose/invocation.sh" "docker is required to wait for compose service '$service_name'"
    return 127
  fi

  for attempt in $(seq 1 "$max_attempts"); do
    container_ids="$(docker_compose ps -q "$service_name" 2>/dev/null || true)"
    all_ready=true

    if [ -z "$container_ids" ]; then
      all_ready=false
    else
      while IFS= read -r container_id; do
        [ -z "$container_id" ] && continue

        container_status="$(docker inspect -f '{{.State.Status}}' "$container_id" 2>/dev/null || true)"
        health_status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id" 2>/dev/null || true)"

        case "$container_status" in
          exited|dead)
            error "compose/invocation.sh" "${service_label} container ${container_id} exited while starting (status=${container_status}, health=${health_status:-unknown})"
            docker_compose logs --no-color --tail 50 "$service_name" || true
            return 1
            ;;
        esac

        if [ "$health_status" = "unhealthy" ]; then
          error "compose/invocation.sh" "${service_label} container ${container_id} reported unhealthy"
          docker_compose logs --no-color --tail 50 "$service_name" || true
          return 1
        fi

        if [ "$health_status" != "healthy" ] && [ "$health_status" != "none" ]; then
          all_ready=false
        elif [ "$container_status" != "running" ]; then
          all_ready=false
        fi
      done <<EOF
$container_ids
EOF
    fi

    if [ "$all_ready" = true ]; then
      return 0
    fi

    if (( attempt % 10 == 0 )); then
      info "compose/invocation.sh" "Waiting for ${service_label} to become healthy... (${attempt}/${max_attempts})"
    fi

    sleep "$sleep_seconds"
  done

  error "compose/invocation.sh" "${service_label} did not become healthy after ${max_attempts} attempts"
  docker_compose logs --no-color --tail 50 "$service_name" || true
  return 1
}
