#!/usr/bin/env bash

# Purpose: Shared teardown helpers for stack stop flows.
# What it does:
# - Resolves the reverse-ordered service stop plan for selected profiles/services.
# - Validates running containers before attempting teardown.
# - Stops the resolved services with the canonical compose wrapper.
#
# Version: 1.0
# Last modified: 2026-05-09

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/logging.sh"
source "$SCRIPT_DIR/dependency_planning.sh"

append_unique_teardown_service() {
  local service_name="$1"

  if [ -z "$service_name" ]; then
    return 0
  fi

  local existing_service=""
  for existing_service in "${TEARDOWN_SERVICES[@]:-}"; do
    if [ "$existing_service" = "$service_name" ]; then
      return 0
    fi
  done

  TEARDOWN_SERVICES+=("$service_name")
}

teardown_collect_targets() {
  local env_file="$1"
  local action_name="$2"
  local selected_profiles_csv="${3:-}"
  local selected_services_csv="${4:-}"
  local planned_services=""
  local service=""

  TEARDOWN_SERVICES=()

  if ! planned_services="$(stack_dependency_plan_services "$env_file" "$selected_profiles_csv" "$selected_services_csv" stop)"; then
    error "teardown.sh" "Unable to resolve dependency plan for $action_name"
    return 1
  fi

  while IFS= read -r service; do
    append_unique_teardown_service "$service"
  done <<EOF
$planned_services
EOF

  if [ "${#TEARDOWN_SERVICES[@]}" -eq 0 ]; then
    error "teardown.sh" "Select --all, --profile, or --service for $action_name"
    return 1
  fi
}

teardown_validate_targets() {
  local env_file="$1"
  shift

  stack_dependency_validate_service_health "$env_file" "$@"
}

teardown_execute_targets() {
  if [ "${#TEARDOWN_SERVICES[@]}" -eq 0 ]; then
    error "teardown.sh" "No services were queued for teardown"
    return 1
  fi

  docker_compose stop "${TEARDOWN_SERVICES[@]}"
}