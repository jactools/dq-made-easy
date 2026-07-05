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

IMAGE_TAG_VARS=(
  DQ_BASE_TAG
  DQ_API_TAG
  DQ_ENGINE_TAG
  DQ_PROFILING_TAG
  DQ_FRONTEND_TAG
  DQ_KONG_TAG
  DQ_DB_TAG
  DQ_KEYCLOAK_TAG
  DQ_LLM_TAG
  DQ_OPENMETADATA_DB_TAG
  DQ_OPENMETADATA_SERVER_TAG
  DQ_METADATA_CONFIGURE_TAG
)

ensure_calculated_image_tags() {
  if [ "${COMPOSE_TAGS_AUTO_LOADED:-false}" = "true" ]; then
    return 0
  fi

  local needs_calculated_tags=false
  local tag_var=""
  local saved_tags_file=""
  local line=""
  local calculate_rc=0
  local calculated_tag_lines=""

  for tag_var in "${IMAGE_TAG_VARS[@]}"; do
    if [ -z "${!tag_var:-}" ]; then
      needs_calculated_tags=true
      break
    fi
  done

  if [ "$needs_calculated_tags" != "true" ]; then
    COMPOSE_TAGS_AUTO_LOADED=true
    return 0
  fi

  saved_tags_file="$(mktemp)"
  for tag_var in "${IMAGE_TAG_VARS[@]}"; do
    if [ -n "${!tag_var:-}" ]; then
      printf '%s=%s\n' "$tag_var" "${!tag_var}" >> "$saved_tags_file"
    fi
  done

  calculated_tag_lines="$(
    ROOT_ENV_FILE="$ROOT_ENV_FILE" LOG_LEVEL=1 bash -c '
      source "$1" >/dev/null 2>&1
      shift
      for tag_var in "$@"; do
        eval "tag_value=\${$tag_var-}"
        printf "%s=%s\n" "$tag_var" "$tag_value"
      done
    ' "$ROOT_DIR/scripts/calculate_versions.sh" "$ROOT_DIR/scripts/calculate_versions.sh" "${IMAGE_TAG_VARS[@]}"
  )" || calculate_rc=$?

  if [ "$calculate_rc" -ne 0 ]; then
    warning "compose/invocation.sh" "Unable to auto-calculate image tags via scripts/calculate_versions.sh"
  else
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      export "$line"
    done <<EOF
$calculated_tag_lines
EOF
  fi

  while IFS= read -r line; do
    [ -z "$line" ] && continue
    export "$line"
  done < "$saved_tags_file"
  rm -f "$saved_tags_file"

  COMPOSE_TAGS_AUTO_LOADED=true
}

docker_compose() {
  if [ -z "${ROOT_ENV_FILE:-}" ]; then
    error "compose/invocation.sh" "ROOT_ENV_FILE must be set before calling docker_compose"
    return 1
  fi

  ensure_calculated_image_tags
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
