#!/usr/bin/env bash
set -euo pipefail

# Purpose: Unified operator entrypoint for repo image and compose lifecycle actions.
# What it does:
# - Provides one command surface for build, pull, push, start, restart, stop, and seed.
# - Uses canonical env selection (`--env` / `--env-file`) across all actions.
# - Supports explicit selectors for profiles, services, images, and seed targets.
# Version: 1.3
# Last modified: 2026-07-01
# - 1.2 (2026-06-30): Made service-only lifecycle commands safe under set -u.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
source "$ROOT_DIR/scripts/supporting/dependency_planning.sh"
source "$ROOT_DIR/scripts/supporting/teardown.sh"
source "$ROOT_DIR/scripts/stack_catalog.sh"
init_root_env_file "$ROOT_DIR"

ACTION="${1:-}"
if [ -z "$ACTION" ]; then
  ACTION="help"
else
  shift
fi

ALL=false
REMOVE_ORPHANS=false
NO_CACHE=false
DRY_RUN=false
IMAGE_SCOPE="repo"
VERSION_TAG=""
PURGE_BUCKET=false
WIPE_AISTOR=false
INIT_DB=false

SELECTED_PROFILES=()
SELECTED_SERVICES=()
SELECTED_IMAGES=()
SELECTED_SEED_TARGETS=()
RECONCILE_PROFILES=()
RECONCILE_ARGS=()

usage() {
  cat <<EOF
Usage: $(basename "$0") <action> [OPTIONS]

Actions:
  build         Build local repo-managed images
  pull          Pull repo-managed images from the configured registry
  push          Build and push repo-managed images
  start         Start compose services
  restart       Restart compose services
  stop          Stop compose services without removing containers
  reconcile     Run explicit post-start reconciliation actions
  seed          Run seed actions
  list-targets  Show supported profiles, images, seed targets, and compose services
  help          Show this help message

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file

Selectors:
  --all                    Select the full action-specific default set
  --profile NAME           Select a runtime compose profile (repeatable)
  --service NAME           Select a compose service (repeatable)
  --image NAME             Select a repo-managed image (repeatable)
  --seed-target NAME       Select a seed target (repeatable)

Plan options:
  --dry-run                Show the resolved plan without changing runtime state

Image action options:
  --scope core|repo        Default image scope for --all (stack_ctl defaults to repo)
  --version TAG            Override image tags for pull/build/push
  --no-cache               Disable Docker build cache for build/push

Container action options:
  --remove-orphans         Pass through to docker compose up -d for start

Seed action options:
  --purge-bucket           Purge delivery bucket before delivery seeding
  --wipe-aistor           Wipe AIStor before delivery seeding
  --init-db                Include init-db flag in seed flow

Examples:
  $(basename "$0") build --all
  $(basename "$0") build --image dq-api --image dq-frontend --no-cache
  $(basename "$0") pull --profile core --profile gateway
  $(basename "$0") start --profile core --profile gateway --profile auth
  $(basename "$0") restart --service api --service frontend
  $(basename "$0") stop --profile support
  $(basename "$0") seed --seed-target postgres --seed-target deliveries --wipe-aistor
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

append_unique_image() {
  local value="$1"
  if ! contains_value "$value" "${SELECTED_IMAGES[@]}"; then
    SELECTED_IMAGES+=("$value")
  fi
}

append_unique_seed_target() {
  local value="$1"
  if ! contains_value "$value" "${SELECTED_SEED_TARGETS[@]}"; then
    SELECTED_SEED_TARGETS+=("$value")
  fi
}

fail() {
  error "$1"
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

resolve_image_selection() {
  local profile=""
  local image=""
  local profile_images=""

  if [ "$ALL" = true ]; then
    case "$IMAGE_SCOPE" in
      core)
        while IFS= read -r image; do
          append_unique_image "$image"
        done < <(core_repo_image_values)
        ;;
      repo)
        while IFS= read -r image; do
          append_unique_image "$image"
        done < <(repo_image_values)
        ;;
      *)
        fail "Unsupported image scope '$IMAGE_SCOPE'"
        ;;
    esac
  fi

  for profile in "${SELECTED_PROFILES[@]}"; do
    if profile_images="$(image_targets_for_profile "$profile" 2>/dev/null)"; then
      while IFS= read -r image; do
        if [ -n "$image" ]; then
          append_unique_image "$image"
        fi
      done <<EOF
$profile_images
EOF
    else
      case "$?" in
        2)
          fail "Profile '$profile' has no repo-managed images for build/pull/push"
          ;;
        *)
          fail "Unsupported profile '$profile' for image actions"
          ;;
      esac
    fi
  done

  if [ "${#SELECTED_IMAGES[@]}" -eq 0 ]; then
    fail "Select --all, --image, or --profile for $ACTION"
  fi
}

resolve_services_from_profiles() {
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

  if ! planned="$(stack_dependency_plan_services "$ROOT_ENV_FILE" "$profile_csv" "$service_csv" "$ACTION")"; then
    fail "Unable to resolve dependency plan for $ACTION"
  fi

  while IFS= read -r service; do
    if [ -n "$service" ] && ! contains_value "$service" ${RESOLVED_SERVICES[@]+"${RESOLVED_SERVICES[@]}"}; then
      RESOLVED_SERVICES+=("$service")
    fi
  done <<EOF
$planned
EOF

  if [ "${#RESOLVED_SERVICES[@]}" -eq 0 ]; then
    fail "Select --all, --profile, or --service for $ACTION"
  fi
}

is_reconciliation_profile() {
  case "$1" in
    gateway|auth|metadata)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

resolve_reconciliation_profiles() {
  local profile=""

  RECONCILE_PROFILES=()

  if [ "$ALL" = true ]; then
    RECONCILE_PROFILES=(gateway auth metadata)
    return 0
  fi

  for profile in "${SELECTED_PROFILES[@]}"; do
    if ! is_reconciliation_profile "$profile"; then
      fail "reconcile accepts only --all, --profile gateway, --profile auth, and --profile metadata"
    fi
    if ! contains_value "$profile" "${RECONCILE_PROFILES[@]}"; then
      RECONCILE_PROFILES+=("$profile")
    fi
  done

  if [ "${#RECONCILE_PROFILES[@]}" -eq 0 ]; then
    fail "Select --all, --profile gateway, --profile auth, or --profile metadata for reconcile"
  fi
}

collect_reconciliation_args() {
  RECONCILE_ARGS=(--env-file "$ROOT_ENV_FILE")

  if contains_value gateway "${RECONCILE_PROFILES[@]}"; then
    RECONCILE_ARGS+=(--gateway)
  fi
  if contains_value auth "${RECONCILE_PROFILES[@]}"; then
    RECONCILE_ARGS+=(--keycloak)
  fi
  if contains_value metadata "${RECONCILE_PROFILES[@]}"; then
    RECONCILE_ARGS+=(--metadata)
  fi
}

show_resolved_plan() {
  local planned_command=""
  local planned_args=()
  local item=""
  local env_validation_mode="full"

  case "$ACTION" in
    build|push)
      resolve_image_selection
      planned_args=("$ROOT_DIR/scripts/build_and_push_all.sh" --env-file "$ROOT_ENV_FILE" --scope "$IMAGE_SCOPE")
      if [ "$NO_CACHE" = true ]; then
        planned_args+=(--no-cache)
      fi
      if [ "$ACTION" = "build" ]; then
        planned_args+=(--no-push)
      fi
      if [ -n "$VERSION_TAG" ]; then
        planned_args+=(--version "$VERSION_TAG")
      fi
      for item in "${SELECTED_IMAGES[@]}"; do
        planned_args+=(--image "$item")
      done
      planned_command="$(printf '%s ' "${planned_args[@]}")"
      info "Plan: ${planned_command% }"
      info "Resolved images:"
      for item in "${SELECTED_IMAGES[@]}"; do
        info "  - $item"
      done
      ;;
    pull)
      resolve_image_selection
      planned_args=("$ROOT_DIR/scripts/pull_images.sh" --env-file "$ROOT_ENV_FILE" --scope "$IMAGE_SCOPE")
      if [ -n "$VERSION_TAG" ]; then
        planned_args+=(--version "$VERSION_TAG")
      fi
      for item in "${SELECTED_IMAGES[@]}"; do
        planned_args+=(--image "$item")
      done
      planned_command="$(printf '%s ' "${planned_args[@]}")"
      info "Plan: ${planned_command% }"
      info "Resolved images:"
      for item in "${SELECTED_IMAGES[@]}"; do
        info "  - $item"
      done
      ;;
    start|restart|stop)
      if [ "$ACTION" = "stop" ]; then
        env_validation_mode="stop"
      fi
      validate_selected_root_env_file "$ROOT_DIR" "$env_validation_mode"
      resolve_services_from_profiles
      planned_args=(docker compose --env-file "$ROOT_ENV_FILE")
      case "$ACTION" in
        start)
          planned_args+=(up -d)
          if [ "$REMOVE_ORPHANS" = true ]; then
            planned_args+=(--remove-orphans)
          fi
          ;;
        restart)
          planned_args+=(restart)
          ;;
        stop)
          planned_args+=(stop)
          ;;
      esac
      planned_args+=(${RESOLVED_SERVICES[@]+"${RESOLVED_SERVICES[@]}"})
      planned_command="$(printf '%s ' "${planned_args[@]}")"
      info "Plan: ${planned_command% }"
      info "Ordered services:"
      for item in ${RESOLVED_SERVICES[@]+"${RESOLVED_SERVICES[@]}"}; do
        info "  - $item"
      done
      ;;
    reconcile)
      validate_selected_root_env_file "$ROOT_DIR" full
      resolve_reconciliation_profiles
      profile_csv="$(join_csv "${RECONCILE_PROFILES[@]}")"
      if ! planned="$(stack_dependency_plan_services "$ROOT_ENV_FILE" "$profile_csv" "" start)"; then
        fail "Unable to resolve dependency plan for reconcile"
      fi
      while IFS= read -r service; do
        if [ -n "$service" ] && ! contains_value "$service" "${RESOLVED_SERVICES[@]}"; then
          RESOLVED_SERVICES+=("$service")
        fi
      done <<EOF
$planned
EOF
      collect_reconciliation_args
      planned_command="$(printf '%s ' "$ROOT_DIR/scripts/reconcile_stack.sh" "${RECONCILE_ARGS[@]}")"
      info "Plan: ${planned_command% }"
      info "Ordered services:"
      for item in "${RESOLVED_SERVICES[@]}"; do
        info "  - $item"
      done
      ;;
    seed)
      validate_selected_root_env_file "$ROOT_DIR" full
      planned_args=("$ROOT_DIR/scripts/seed_stack.sh" --env-file "$ROOT_ENV_FILE")
      if [ "$ALL" = true ]; then
        planned_args+=(--seed-all)
      else
        if [ "${#SELECTED_SEED_TARGETS[@]}" -eq 0 ]; then
          fail "Select --all or --seed-target for seed"
        fi
        for item in "${SELECTED_SEED_TARGETS[@]}"; do
          planned_args+=("$(seed_flag_for_target "$item")")
        done
      fi
      if [ "$PURGE_BUCKET" = true ]; then
        planned_args+=(--purge-bucket)
      fi
      if [ "$WIPE_AISTOR" = true ]; then
        planned_args+=(--wipe-aistor)
      fi
      if [ "$INIT_DB" = true ]; then
        planned_args+=(--init-db)
      fi
      planned_command="$(printf '%s ' "${planned_args[@]}")"
      info "Plan: ${planned_command% }"
      info "Seed targets:"
      if [ "$ALL" = true ]; then
        info "  - all"
      else
        for item in "${SELECTED_SEED_TARGETS[@]}"; do
          info "  - $item"
        done
      fi
      ;;
  esac
}

validate_action_selectors() {
  case "$ACTION" in
    build|pull|push)
      if [ "${#SELECTED_SERVICES[@]}" -gt 0 ] || [ "${#SELECTED_SEED_TARGETS[@]}" -gt 0 ]; then
        fail "$ACTION accepts only --all, --profile, --image, --scope, --version, and --no-cache"
      fi
      ;;
    start|restart|stop)
      if [ "${#SELECTED_IMAGES[@]}" -gt 0 ] || [ "${#SELECTED_SEED_TARGETS[@]}" -gt 0 ]; then
        fail "$ACTION accepts only --all, --profile, --service, and lifecycle options"
      fi
      ;;
    reconcile)
      if [ "${#SELECTED_IMAGES[@]}" -gt 0 ] || [ "${#SELECTED_SERVICES[@]}" -gt 0 ] || [ "${#SELECTED_SEED_TARGETS[@]}" -gt 0 ]; then
        fail "reconcile accepts only --all, --profile, and reconciliation options"
      fi
      ;;
    seed)
      if [ "${#SELECTED_IMAGES[@]}" -gt 0 ] || [ "${#SELECTED_SERVICES[@]}" -gt 0 ] || [ "${#SELECTED_PROFILES[@]}" -gt 0 ]; then
        fail "seed accepts only --all, --seed-target, and seed-specific options"
      fi
      ;;
    list-targets|help)
      ;;
    *)
      fail "Unsupported action '$ACTION'"
      ;;
  esac
}

show_targets() {
  echo "Runtime profiles:"
  runtime_profile_values | sed 's/^/  - /'
  echo ""
  echo "Repo-managed images:"
  repo_image_values | sed 's/^/  - /'
  echo ""
  echo "Seed targets:"
  seed_target_values | sed 's/^/  - /'
  echo ""
  if ensure_selected_root_env_file_exists >/dev/null 2>&1; then
    echo "Compose services for $ROOT_ENV_FILE:"
    docker_compose config --services | sed 's/^/  - /'
  else
    echo "Compose services: env file not found ($ROOT_ENV_FILE)"
  fi
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
    --image)
      if [[ -z "${2:-}" ]]; then
        fail "--image requires a repo-managed image name"
      fi
      if ! is_repo_managed_image "$2"; then
        fail "Unsupported image '$2'"
      fi
      append_unique_image "$2"
      shift 2
      ;;
    --seed-target)
      if [[ -z "${2:-}" ]]; then
        fail "--seed-target requires one of: $(seed_target_values | paste -sd ',' -)"
      fi
      if ! is_seed_target "$2"; then
        fail "Unsupported seed target '$2'"
      fi
      append_unique_seed_target "$2"
      shift 2
      ;;
    --scope)
      if [[ -z "${2:-}" ]]; then
        fail "--scope requires core or repo"
      fi
      case "$2" in
        core|repo)
          IMAGE_SCOPE="$2"
          ;;
        *)
          fail "Unsupported scope '$2'"
          ;;
      esac
      shift 2
      ;;
    --version)
      if [[ -z "${2:-}" ]]; then
        fail "--version requires a tag value"
      fi
      VERSION_TAG="$2"
      shift 2
      ;;
    --no-cache)
      NO_CACHE=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --remove-orphans)
      REMOVE_ORPHANS=true
      shift
      ;;
    --purge-bucket)
      PURGE_BUCKET=true
      shift
      ;;
    --wipe-aistor)
      WIPE_AISTOR=true
      shift
      ;;
    --init-db)
      INIT_DB=true
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

validate_action_selectors

case "$ACTION" in
  help)
    usage
    ;;
  list-targets)
    show_targets
    ;;
  build|push)
    if [ "$DRY_RUN" = true ]; then
      show_resolved_plan
      exit 0
    fi
    resolve_image_selection
    build_args=(--env-file "$ROOT_ENV_FILE" --scope "$IMAGE_SCOPE")
    if [ "$NO_CACHE" = true ]; then
      build_args+=(--no-cache)
    fi
    if [ "$ACTION" = "build" ]; then
      build_args+=(--no-push)
    fi
    if [ -n "$VERSION_TAG" ]; then
      build_args+=(--version "$VERSION_TAG")
    fi
    for image in "${SELECTED_IMAGES[@]}"; do
      build_args+=(--image "$image")
    done
    "$ROOT_DIR/scripts/build_and_push_all.sh" "${build_args[@]}"
    ;;
  pull)
    resolve_image_selection
    pull_args=(--env-file "$ROOT_ENV_FILE" --scope "$IMAGE_SCOPE")
    if [ -n "$VERSION_TAG" ]; then
      pull_args+=(--version "$VERSION_TAG")
    fi
    for image in "${SELECTED_IMAGES[@]}"; do
      pull_args+=(--image "$image")
    done
    "$ROOT_DIR/scripts/pull_images.sh" "${pull_args[@]}"
    ;;
  start)
    if [ "$DRY_RUN" = true ]; then
      show_resolved_plan
      exit 0
    fi
    validate_selected_root_env_file "$ROOT_DIR" full
    resolve_services_from_profiles
    stack_dependency_validate_service_health "$ROOT_ENV_FILE" ${RESOLVED_SERVICES[@]+"${RESOLVED_SERVICES[@]}"}
    start_args=()
    if [ "$REMOVE_ORPHANS" = true ]; then
      start_args+=(up -d --remove-orphans)
    else
      start_args+=(up -d)
    fi
    start_args+=(${RESOLVED_SERVICES[@]+"${RESOLVED_SERVICES[@]}"})
    docker_compose "${start_args[@]}"
    ;;
  restart)
    if [ "$DRY_RUN" = true ]; then
      show_resolved_plan
      exit 0
    fi
    validate_selected_root_env_file "$ROOT_DIR" full
    resolve_services_from_profiles
    stack_dependency_validate_service_health "$ROOT_ENV_FILE" ${RESOLVED_SERVICES[@]+"${RESOLVED_SERVICES[@]}"}
    docker_compose restart ${RESOLVED_SERVICES[@]+"${RESOLVED_SERVICES[@]}"}
    ;;
  stop)
    if [ "$DRY_RUN" = true ]; then
      show_resolved_plan
      exit 0
    fi
    validate_selected_root_env_file "$ROOT_DIR" stop
    profile_csv="$(join_csv ${SELECTED_PROFILES[@]+"${SELECTED_PROFILES[@]}"})"
    service_csv="$(join_csv ${SELECTED_SERVICES[@]+"${SELECTED_SERVICES[@]}"})"
    if ! teardown_collect_targets "$ROOT_ENV_FILE" "$ACTION" "$profile_csv" "$service_csv"; then
      exit 1
    fi
    teardown_validate_targets "$ROOT_ENV_FILE" "${TEARDOWN_SERVICES[@]}"
    teardown_execute_targets
    ;;
  reconcile)
    if [ "$DRY_RUN" = true ]; then
      show_resolved_plan
      exit 0
    fi
    validate_selected_root_env_file "$ROOT_DIR" full
    resolve_reconciliation_profiles
    profile_csv="$(join_csv "${RECONCILE_PROFILES[@]}")"
    if ! planned="$(stack_dependency_plan_services "$ROOT_ENV_FILE" "$profile_csv" "" start)"; then
      fail "Unable to resolve dependency plan for reconcile"
    fi
    while IFS= read -r service; do
      if [ -n "$service" ] && ! contains_value "$service" "${RESOLVED_SERVICES[@]}"; then
        RESOLVED_SERVICES+=("$service")
      fi
    done <<EOF
$planned
EOF
    stack_dependency_validate_service_health "$ROOT_ENV_FILE" "${RESOLVED_SERVICES[@]}"
    collect_reconciliation_args
    "$ROOT_DIR/scripts/reconcile_stack.sh" "${RECONCILE_ARGS[@]}"
    ;;
  seed)
    if [ "$DRY_RUN" = true ]; then
      show_resolved_plan
      exit 0
    fi
    validate_selected_root_env_file "$ROOT_DIR" full
    seed_args=(--env-file "$ROOT_ENV_FILE")
    if [ "$ALL" = true ]; then
      seed_args+=(--seed-all)
    else
      if [ "${#SELECTED_SEED_TARGETS[@]}" -eq 0 ]; then
        fail "Select --all or --seed-target for seed"
      fi
      for seed_target in "${SELECTED_SEED_TARGETS[@]}"; do
        seed_args+=("$(seed_flag_for_target "$seed_target")")
      done
    fi
    if [ "$PURGE_BUCKET" = true ]; then
      seed_args+=(--purge-bucket)
    fi
    if [ "$WIPE_AISTOR" = true ]; then
      seed_args+=(--wipe-aistor)
    fi
    if [ "$INIT_DB" = true ]; then
      seed_args+=(--init-db)
    fi
    "$ROOT_DIR/scripts/seed_stack.sh" "${seed_args[@]}"
    ;;
 esac
