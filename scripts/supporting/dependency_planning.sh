# Purpose: Resolve compose service dependency closures for stack lifecycle actions.
# What it does:
# - Expands selected runtime profiles and explicit services into an ordered service plan.
# - Reverses stop ordering so teardown respects dependency edges.
# - Fails fast when a planned service container is unhealthy or cannot be inspected.
# Version: 1.1
# Last modified: 2026-06-30
# - 1.1 (2026-06-30): Made service-only planning safe under set -u.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/logging.sh"
source "$SCRIPT_DIR/compose/invocation.sh"

join_csv() {
  local IFS=,
  printf '%s' "$*"
}

stack_dependency_plan_services() {
  local env_file="$1"
  local selected_profiles_csv="${2:-}"
  local selected_services_csv="${3:-}"
  local mode="${4:-start}"
  local profile=""
  local profile_args=()
  local compose_json=""
  local planned_services=""
  local ROOT_ENV_FILE="$env_file"

  if ! command -v python3 >/dev/null 2>&1; then
    error "python3 is required for dependency planning"
    return 1
  fi

  if [ -n "$selected_profiles_csv" ]; then
    local old_ifs="$IFS"
    IFS=,
    for profile in $selected_profiles_csv; do
      if [ -n "$profile" ]; then
        profile_args+=(--profile "$profile")
      fi
    done
    IFS="$old_ifs"
  fi

  if ! compose_json="$(docker_compose ${profile_args[@]+"${profile_args[@]}"} config --format json)"; then
    error "docker compose config failed while planning dependencies"
    return 1
  fi

  if ! planned_services="$(SELECTED_PROFILES_CSV="$selected_profiles_csv" \
    SELECTED_SERVICES_CSV="$selected_services_csv" \
    PLAN_MODE="$mode" \
    python3 -c '
import json
import os
import sys

compose = json.load(sys.stdin)
services = compose.get("services") or {}
selected_profiles = [item for item in os.getenv("SELECTED_PROFILES_CSV", "").split(",") if item]
selected_services = [item for item in os.getenv("SELECTED_SERVICES_CSV", "").split(",") if item]
mode = os.getenv("PLAN_MODE", "start")

if not selected_profiles and not selected_services:
    raise SystemExit("Select --all, --profile, or --service for dependency planning")

missing_services = sorted(service for service in selected_services if service not in services)
if missing_services:
    raise SystemExit("Unknown compose service(s): " + ", ".join(missing_services))

dependencies = {}
profile_match_count = 0
initial = set(selected_services)

for name, service in services.items():
    raw_depends_on = service.get("depends_on") or {}
    if isinstance(raw_depends_on, list):
        dependency_names = list(raw_depends_on)
    elif isinstance(raw_depends_on, dict):
        dependency_names = list(raw_depends_on.keys())
    else:
        dependency_names = []

    dependencies[name] = dependency_names

    if selected_profiles:
        profiles = service.get("profiles") or []
        if profiles and any(profile in selected_profiles for profile in profiles):
            initial.add(name)
            profile_match_count += 1

if selected_profiles and profile_match_count == 0:
    raise SystemExit("No compose services matched the selected profile(s): " + ", ".join(selected_profiles))

visited = set()
visiting = set()
ordered = []

def visit(name):
    if name in visited:
        return
    if name in visiting:
        raise SystemExit("Cycle detected while resolving dependency plan at service: " + name)
    if name not in services:
        raise SystemExit("Unknown compose service in dependency plan: " + name)

    visiting.add(name)
    for dependency in dependencies.get(name, []):
        if dependency not in services:
            raise SystemExit("Service '" + name + "' depends on missing compose service '" + dependency + "'")
        visit(dependency)
    visiting.remove(name)
    visited.add(name)
    ordered.append(name)

for name in sorted(initial):
    visit(name)

if mode == "stop":
    ordered.reverse()
elif mode not in ("start", "restart"):
    raise SystemExit("Unsupported dependency planning mode: " + mode)

sys.stdout.write("\n".join(ordered))
if ordered:
    sys.stdout.write("\n")
' <<<"$compose_json")"; then
    return 1
  fi

  printf '%s' "$planned_services"
}

stack_dependency_validate_service_health() {
  local env_file="$1"
  shift
  local ROOT_ENV_FILE="$env_file"

  local service=""
  local container_ids=""
  local container_id=""
  local health_status=""

  for service in "$@"; do
    if ! container_ids="$(docker_compose ps -q "$service")"; then
      error "Failed to inspect running containers for service '$service'"
      return 1
    fi

    [ -z "$container_ids" ] && continue

    while IFS= read -r container_id; do
      [ -z "$container_id" ] && continue

      if ! health_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}' "$container_id")"; then
        error "Failed to inspect container '$container_id' for service '$service'"
        return 1
      fi

      if [ "$health_status" = "unhealthy" ]; then
        error "Required service '$service' is unhealthy"
        return 1
      fi
    done <<EOF
$container_ids
EOF
  done
}