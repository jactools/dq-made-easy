#!/usr/bin/env bash
set -euo pipefail

# Purpose: Report compose service status for resolved runtime profiles and services.
# What it does:
# - Uses the canonical env selection contract shared by stack lifecycle scripts.
# - Resolves selected profiles and services into the dependency-ordered service set.
# - Inspects each container and reports whether it is running, completed, failed,
#   waiting, or in another state.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
source "$ROOT_DIR/scripts/supporting/dependency_planning.sh"
source "$ROOT_DIR/scripts/supporting/stay_awake.sh"
source "$ROOT_DIR/scripts/stack_catalog.sh"
init_root_env_file "$ROOT_DIR"

ALL=false
PER_CONTAINER=false
SELECTED_PROFILES=()
SELECTED_SERVICES=()
RESOLVED_SERVICES=()

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Show the status of services resolved from compose profiles and explicit services.

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file

Selectors:
  --all                    Select the full runtime profile set
  --profile NAME           Select a runtime compose profile (repeatable)
  --service NAME           Select a compose service (repeatable)

Output mode:
  --per-container          Show one line per container instead of one line per service

Examples:
  $(basename "$0") --env dev --profile core
  $(basename "$0") --profile gateway --profile auth
  $(basename "$0") --all
  $(basename "$0") --per-container --profile core
EOF
}

contains_value() {
  local needle="$1"
  shift
  local item=""

  for item in "$@"; do
    if [ "$item" = "$needle" ]; then
      return 0
    fi
  done

  return 1
}

join_csv() {
  local IFS=,
  printf '%s' "$*"
}

append_unique_profile() {
  local value="$1"
  if ! contains_value "$value" ${SELECTED_PROFILES[@]+"${SELECTED_PROFILES[@]}"}; then
    SELECTED_PROFILES+=("$value")
  fi
}

append_unique_service() {
  local value="$1"
  if ! contains_value "$value" ${SELECTED_SERVICES[@]+"${SELECTED_SERVICES[@]}"}; then
    SELECTED_SERVICES+=("$value")
  fi
}

fail() {
  error "stack_status.sh" "$1"
  exit 1
}

validate_runtime_profiles() {
  local profile=""
  for profile in ${SELECTED_PROFILES[@]+"${SELECTED_PROFILES[@]}"}; do
    if ! is_runtime_profile "$profile"; then
      fail "Unsupported runtime profile '$profile'"
    fi
  done
}

populate_all_runtime_profiles() {
  local profile=""
  while IFS= read -r profile; do
    append_unique_profile "$profile"
  done < <(default_runtime_profile_values)
}

resolve_services_for_status() {
  local planned=""
  local service=""
  local profile_csv=""
  local service_csv=""

  RESOLVED_SERVICES=()

  if [ "$ALL" = true ]; then
    populate_all_runtime_profiles
  fi

  validate_runtime_profiles

  profile_csv="$(join_csv ${SELECTED_PROFILES[@]+"${SELECTED_PROFILES[@]}"})"
  service_csv="$(join_csv ${SELECTED_SERVICES[@]+"${SELECTED_SERVICES[@]}"})"

  if ! planned="$(stack_dependency_plan_services "$ROOT_ENV_FILE" "$profile_csv" "$service_csv" start)"; then
    fail "Unable to resolve dependency plan for status"
  fi

  while IFS= read -r service; do
    if [ -n "$service" ] && ! contains_value "$service" ${RESOLVED_SERVICES[@]+"${RESOLVED_SERVICES[@]}"}; then
      RESOLVED_SERVICES+=("$service")
    fi
  done <<EOF
$planned
EOF

  if [ "${#RESOLVED_SERVICES[@]}" -eq 0 ]; then
    fail "Select --all, --profile, or --service for status"
  fi
}

describe_container_status() {
  local service_name="$1"
  local container_id="$2"
  local inspection=""
  local container_status=""
  local health_status=""
  local exit_code=""
  local container_error=""
  local short_id="${container_id:0:12}"

  if ! inspection="$(docker inspect -f '{{.State.Status}}\t{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}\t{{.State.ExitCode}}\t{{.State.Error}}' "$container_id" 2>/dev/null)"; then
    printf '%s [%s]: error: unable to inspect container\n' "$service_name" "$short_id"
    return 0
  fi

  IFS=$'\t' read -r container_status health_status exit_code container_error <<<"$inspection"

  case "$container_status" in
    running)
      case "$health_status" in
        healthy|none|"")
          printf '%s [%s]: up-and-running\n' "$service_name" "$short_id"
          ;;
        starting)
          printf '%s [%s]: waiting for the health check to become healthy\n' "$service_name" "$short_id"
          ;;
        unhealthy)
          if [ -n "$container_error" ]; then
            printf '%s [%s]: failed: health check reported unhealthy (error: %s)\n' "$service_name" "$short_id" "$container_error"
          else
            printf '%s [%s]: failed: health check reported unhealthy\n' "$service_name" "$short_id"
          fi
          ;;
        *)
          printf '%s [%s]: other status: running (health=%s)\n' "$service_name" "$short_id" "$health_status"
          ;;
      esac
      ;;
    exited)
      if [ "$exit_code" = "0" ]; then
        printf '%s [%s]: completed\n' "$service_name" "$short_id"
      elif [ -n "$container_error" ]; then
        printf '%s [%s]: failed: exited with code %s (error: %s)\n' "$service_name" "$short_id" "$exit_code" "$container_error"
      else
        printf '%s [%s]: failed: exited with code %s\n' "$service_name" "$short_id" "$exit_code"
      fi
      ;;
    created)
      printf '%s [%s]: waiting for the container to start\n' "$service_name" "$short_id"
      ;;
    restarting)
      if [ -n "$container_error" ]; then
        printf '%s [%s]: waiting for the container to restart (error: %s)\n' "$service_name" "$short_id" "$container_error"
      else
        printf '%s [%s]: waiting for the container to restart\n' "$service_name" "$short_id"
      fi
      ;;
    paused)
      printf '%s [%s]: other status: paused\n' "$service_name" "$short_id"
      ;;
    dead)
      if [ -n "$container_error" ]; then
        printf '%s [%s]: failed: container is dead (error: %s)\n' "$service_name" "$short_id" "$container_error"
      else
        printf '%s [%s]: failed: container is dead\n' "$service_name" "$short_id"
      fi
      ;;
    removing)
      printf '%s [%s]: waiting for the container to be removed\n' "$service_name" "$short_id"
      ;;
    *)
      if [ -n "$container_error" ]; then
        printf '%s [%s]: other status: %s (error: %s)\n' "$service_name" "$short_id" "${container_status:-unknown}" "$container_error"
      else
        printf '%s [%s]: other status: %s\n' "$service_name" "$short_id" "${container_status:-unknown}"
      fi
      ;;
  esac
}

aggregate_service_status() {
  local service_name="$1"
  shift
  local container_lines=()
  local container_info=""
  local container_status=""
  local health_status=""
  local exit_code=""
  local container_error=""
  local failed_message=""
  local waiting_message=""
  local other_message=""
  local service_state=""
  local short_id=""

  for container_info in "$@"; do
    IFS=$'\t' read -r short_id container_status health_status exit_code container_error <<<"$container_info"
    case "$container_status" in
      running)
        case "$health_status" in
          healthy|none|"")
            container_lines+=(up)
            ;;
          starting)
            waiting_message="health check to become healthy"
            container_lines+=(waiting)
            ;;
          unhealthy)
            if [ -n "$container_error" ]; then
              failed_message="health check reported unhealthy (error: $container_error)"
            else
              failed_message="health check reported unhealthy"
            fi
            container_lines+=(failed)
            ;;
          *)
            other_message="running (health=${health_status:-unknown})"
            container_lines+=(other)
            ;;
        esac
        ;;
      exited)
        if [ "$exit_code" = "0" ]; then
          container_lines+=(completed)
        elif [ -n "$container_error" ]; then
          failed_message="exited with code $exit_code (error: $container_error)"
          container_lines+=(failed)
        else
          failed_message="exited with code $exit_code"
          container_lines+=(failed)
        fi
        ;;
      created)
        waiting_message="the container to start"
        container_lines+=(waiting)
        ;;
      restarting)
        if [ -n "$container_error" ]; then
          waiting_message="the container to restart (error: $container_error)"
        else
          waiting_message="the container to restart"
        fi
        container_lines+=(waiting)
        ;;
      paused)
        other_message="paused"
        container_lines+=(other)
        ;;
      dead)
        if [ -n "$container_error" ]; then
          failed_message="container is dead (error: $container_error)"
        else
          failed_message="container is dead"
        fi
        container_lines+=(failed)
        ;;
      removing)
        waiting_message="the container to be removed"
        container_lines+=(waiting)
        ;;
      *)
        if [ -n "$container_error" ]; then
          other_message="${container_status:-unknown} (error: $container_error)"
        else
          other_message="${container_status:-unknown}"
        fi
        container_lines+=(other)
        ;;
    esac
  done

  service_state="up-and-running"
  if contains_value failed "${container_lines[@]}"; then
    service_state="failed"
  elif contains_value waiting "${container_lines[@]}"; then
    service_state="waiting"
  elif contains_value other "${container_lines[@]}"; then
    service_state="other"
  elif contains_value completed "${container_lines[@]}"; then
    service_state="completed"
  fi

  case "$service_state" in
    up-and-running)
      printf '%s: up-and-running\n' "$service_name"
      ;;
    completed)
      printf '%s: completed\n' "$service_name"
      ;;
    waiting)
      if [ -n "$waiting_message" ]; then
        printf '%s: waiting for %s\n' "$service_name" "$waiting_message"
      else
        printf '%s: waiting\n' "$service_name"
      fi
      ;;
    failed)
      if [ -n "$failed_message" ]; then
        printf '%s: failed: %s\n' "$service_name" "$failed_message"
      else
        printf '%s: failed\n' "$service_name"
      fi
      ;;
    other)
      if [ -n "$other_message" ]; then
        printf '%s: other status: %s\n' "$service_name" "$other_message"
      else
        printf '%s: other status\n' "$service_name"
      fi
      ;;
  esac
}

show_status() {
  local service=""
  local container_ids=""
  local container_id=""
  local container_rows=()
  local inspection=""
  local container_status=""
  local health_status=""
  local exit_code=""
  local container_error=""
  local short_id=""

  for service in "${RESOLVED_SERVICES[@]}"; do
    container_ids="$(docker_compose ps -aq "$service" 2>/dev/null || true)"
    if [ -z "$container_ids" ]; then
      printf '%s: waiting for the service container to be created\n' "$service"
      continue
    fi

    container_rows=()

    while IFS= read -r container_id; do
      [ -z "$container_id" ] && continue
      if [ "$PER_CONTAINER" = true ]; then
        describe_container_status "$service" "$container_id"
      else
        short_id="${container_id:0:12}"
        if ! inspection="$(docker inspect -f '{{.State.Status}}\t{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}\t{{.State.ExitCode}}\t{{.State.Error}}' "$container_id" 2>/dev/null)"; then
          container_rows+=("$short_id"$'\t''failed'$'\t''none'$'\t''1'$'\t''unable to inspect container')
          continue
        fi

        IFS=$'\t' read -r container_status health_status exit_code container_error <<<"$inspection"
        container_rows+=("$short_id"$'\t'"$container_status"$'\t'"$health_status"$'\t'"$exit_code"$'\t'"$container_error")
      fi
    done <<EOF
$container_ids
EOF

    if [ "$PER_CONTAINER" = false ]; then
      aggregate_service_status "$service" "${container_rows[@]}"
    fi
  done
}

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  usage
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      ALL=true
      shift
      ;;
    --profile)
      if [[ -z "${2:-}" ]]; then
        fail "--profile requires a runtime profile name"
      fi
      append_unique_profile "$2"
      shift 2
      ;;
    --service)
      if [[ -z "${2:-}" ]]; then
        fail "--service requires a compose service name"
      fi
      append_unique_service "$2"
      shift 2
      ;;
    --per-container)
      PER_CONTAINER=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument '$1'"
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  fail "docker is required for stack status inspection"
fi

validate_selected_root_env_file "$ROOT_DIR" full
start_stay_awake
trap stop_stay_awake EXIT INT TERM
resolve_services_for_status
show_status
stop_stay_awake