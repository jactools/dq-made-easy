#!/usr/bin/env bash
# Purpose: Orchestrator for the compose stack lifecycle.
#
# What it does:
#   Dispatches to the single-responsibility scripts (stack_destroy, stack_start,
#   stack_stop, stack_restart, stack_seed) based on the requested action.
#
# Actions:
#   destroy   — full teardown (containers, volumes, artifacts)
#   stop      — stop containers only (keeps volumes and artifacts)
#   start     — start stack, seed if --seed is given
#   restart   — stop then start (reuse admin passwords, rotate service/user)
#   init      — destroy → start → seed (full clean reset)
#   seed      — seed the running stack
#
# Password semantics:
#   destroy   : remove all
#   start     : generate new admin + service/user passwords on fresh start;
#               reuse admin passwords, rotate service/user on warm start
#   restart   : reuse admin passwords, rotate service/user passwords
#   stop      : keep everything
#   seed      : rotate user passwords (via Keycloak seeding)
#
# Usage:
#   ./scripts/stack.sh <env> <action> [OPTIONS]
#
# Examples:
#   ./scripts/stack.sh dev init
#   ./scripts/stack.sh dev start --seed
#   ./scripts/stack.sh test restart
#   ./scripts/stack.sh prod stop
#   ./scripts/stack.sh dev seed --seed-postgres
#
# Version: 1.0
# Last modified: 2026-07-14

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="stack.sh"

print_usage() {
  cat <<EOF
Usage: $(basename "$0") <env> <action> [OPTIONS]

Orchestrator for the compose stack lifecycle.

Environments:
  dev         Use .env.dev.local
  test        Use .env.test.local
  prod        Use .env.prod.local

Actions:
  destroy     Full teardown (containers, volumes, all generated artifacts)
  stop        Stop containers only (keeps volumes, secrets, credentials)
  start       Start stack (generate secrets, start containers)
  restart     Stop then start (reuse admin passwords, rotate service/user)
  init        Destroy → start → seed (full clean reset)
  seed        Seed the running stack

Options:
  --seed          Also run seeding after start/restart/init
  --force-build   Build images from scratch (no cache)
  --no-build      Skip image builds
  --init-db       Initialize DB schema (implies postgres seeding)
  -h, --help      Show this help

Password policy:
  Admin passwords  (DB, Keycloak admin):  reused when volumes exist
  Service passwords (OIDC secrets, keys): rotated on every start/restart
  User passwords:                         rotated on every seed

Examples:
  $(basename "$0") dev init
  $(basename "$0") dev start --seed
  $(basename "$0") test restart
  $(basename "$0") prod stop
  $(basename "$0") dev seed
EOF
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
ENV=""
ACTION=""
SEED=false
FORCE_BUILD=false
NO_BUILD=false
INIT_DB=false

if [ $# -eq 0 ]; then
  print_usage
  exit 1
fi

# First arg: environment
case "$1" in
  dev|test|prod)
    ENV="$1"
    shift
    ;;
  -h|--help)
    print_usage
    exit 0
    ;;
  *)
    error "$my_name" "Invalid environment: $1 (must be dev, test, or prod)"
    exit 1
    ;;
esac

# Second arg: action
case "${1:-}" in
  destroy|stop|start|restart|init|seed)
    ACTION="$1"
    shift
    ;;
  "")
    error "$my_name" "Action is required (destroy, stop, start, restart, init, seed)"
    print_usage
    exit 1
    ;;
  -h|--help)
    print_usage
    exit 0
    ;;
  *)
    error "$my_name" "Invalid action: $1"
    print_usage
    exit 1
    ;;
esac

# Remaining args
EXTRA_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED=true; shift ;;
    --force-build) FORCE_BUILD=true; shift ;;
    --no-build) NO_BUILD=true; shift ;;
    --init-db) INIT_DB=true; shift ;;
    -h|--help) print_usage; exit 0 ;;
    *) EXTRA_ARGS+=("$1"); shift ;;
  esac
done

# ---------------------------------------------------------------------------
# Build argument arrays for child scripts
# ---------------------------------------------------------------------------
ENV_FLAG=(--env "$ENV")

if [ "$FORCE_BUILD" = true ]; then
  BUILD_FLAG=(--force-build)
elif [ "$NO_BUILD" = true ]; then
  BUILD_FLAG=(--no-build)
else
  BUILD_FLAG=()
fi

if [ "$INIT_DB" = true ]; then
  INIT_FLAG=(--init-db)
else
  INIT_FLAG=()
fi

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

case "$ACTION" in
  destroy)
    info "$my_name" "Action: destroy"
    ./scripts/stack_destroy.sh "${ENV_FLAG[@]}"
    ;;

  stop)
    info "$my_name" "Action: stop"
    ./scripts/stack_stop.sh "${ENV_FLAG[@]}"
    ;;

  start)
    info "$my_name" "Action: start"
    ./scripts/stack_start.sh "${ENV_FLAG[@]}" "${BUILD_FLAG[@]}"
    if [ "$SEED" = true ] || [ "$INIT_DB" = true ]; then
      info "$my_name" "Running seed after start..."
      ./scripts/stack_seed.sh "${ENV_FLAG[@]}" "${INIT_FLAG[@]}"
    fi
    ;;

  restart)
    info "$my_name" "Action: restart"
    ./scripts/stack_restart.sh "${ENV_FLAG[@]}" "${BUILD_FLAG[@]}"
    if [ "$SEED" = true ] || [ "$INIT_DB" = true ]; then
      info "$my_name" "Running seed after restart..."
      ./scripts/stack_seed.sh "${ENV_FLAG[@]}" "${INIT_FLAG[@]}"
    fi
    ;;

  init)
    info "$my_name" "Action: init (destroy → start → seed)"
    ./scripts/stack_destroy.sh "${ENV_FLAG[@]}"
    ./scripts/stack_start.sh "${ENV_FLAG[@]}" "${BUILD_FLAG[@]}"
    ./scripts/stack_seed.sh "${ENV_FLAG[@]}" "${INIT_FLAG[@]}"
    ;;

  seed)
    info "$my_name" "Action: seed"
    ./scripts/stack_seed.sh "${ENV_FLAG[@]}" "${INIT_FLAG[@]}"
    ;;
esac

success "$my_name" "Done"
