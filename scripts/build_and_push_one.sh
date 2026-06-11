#!/usr/bin/env bash
set -euo pipefail


# Purpose: Build and optionally push a single service image.
#
# What it does:
# - Parses the target image name and build/push options.
# - Delegates to the service-specific build script.
# - Optionally overrides the version tag.
#
# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR"

my_name="build_and_push_one.sh"

NO_CACHE=false
NO_PUSH=false
VERSION_TAG=""
SERVICE=""

usage() {
  cat <<EOF
Usage: $(basename "$0") <image> [--no-cache] [--no-push] [--version <tag>]

Build and optionally push one image.

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file

Images:
  dq-base
  dq-api
  dq-engine
  dq-profiling
  dq-frontend
  dq-kong
  dq-db
  dq-keycloak
  dq-llm

Options:
  --no-cache         Build without Docker cache
  --no-push          Build only, do not push
  --version <tag>    Override tag (default: auto content-hash tag)
  -h, --help         Show help
EOF
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

SERVICE="$1"
shift

DIRECT_DQ_LLM=false

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  usage
  exit 1
fi

set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"
export ROOT_ENV_FILE

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-cache)
      NO_CACHE=true
      shift
      ;;
    --no-push)
      NO_PUSH=true
      shift
      ;;
    --version)
      if [[ -z "${2:-}" ]]; then
        error "$my_name" "--version requires a tag value"
        exit 1
      fi
      VERSION_TAG="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "$my_name" "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

# Map service -> script and tag variable
STEP_SCRIPT=""
TAG_VAR=""

case "$SERVICE" in
  dq-base)
    STEP_SCRIPT="$ROOT_DIR/dq-base/scripts/build_and_push.sh"
    TAG_VAR="DQ_BASE_TAG"
    ;;
  dq-api)
    STEP_SCRIPT="$ROOT_DIR/dq-api/scripts/build_and_push.sh"
    TAG_VAR="DQ_API_TAG"
    ;;
  dq-engine)
    STEP_SCRIPT="$ROOT_DIR/dq-engine/scripts/build_and_push.sh"
    TAG_VAR="DQ_ENGINE_TAG"
    ;;
  dq-profiling)
    STEP_SCRIPT="$ROOT_DIR/dq-profiling/scripts/build_and_push.sh"
    TAG_VAR="DQ_PROFILING_TAG"
    ;;
  dq-frontend)
    STEP_SCRIPT="$ROOT_DIR/dq-ui/scripts/build_and_push.sh"
    TAG_VAR="DQ_FRONTEND_TAG"
    ;;
  dq-kong)
    STEP_SCRIPT="$ROOT_DIR/dq-kong/scripts/build_and_push.sh"
    TAG_VAR="DQ_KONG_TAG"
    ;;
  dq-db)
    STEP_SCRIPT="$ROOT_DIR/dq-db/scripts/build_and_push.sh"
    TAG_VAR="DQ_DB_TAG"
    ;;
  dq-keycloak)
    STEP_SCRIPT="$ROOT_DIR/dq-keycloak/scripts/build_and_push.sh"
    TAG_VAR="DQ_KEYCLOAK_TAG"
    ;;
  dq-llm)
    DIRECT_DQ_LLM=true
    STEP_SCRIPT="$ROOT_DIR/scripts/build_and_push_all.sh"
    TAG_VAR="DQ_LLM_TAG"
    ;;
  *)
    error "$my_name" "Unknown image '$SERVICE'"
    usage
    exit 1
    ;;
esac

if [[ "$DIRECT_DQ_LLM" != true && ! -f "$STEP_SCRIPT" ]]; then
  error "$my_name" "Script not found: $STEP_SCRIPT"
  exit 1
fi
if [[ "$DIRECT_DQ_LLM" != true ]]; then
  [[ -x "$STEP_SCRIPT" ]] || chmod +x "$STEP_SCRIPT"
fi

# Resolve tag
if [[ -n "$VERSION_TAG" ]]; then
  export "$TAG_VAR=$VERSION_TAG"
else
  # Loads auto-calculated tags (same behavior as build_and_push_all.sh)
  # shellcheck disable=SC1091
  source "$ROOT_DIR/scripts/calculate_versions.sh"
fi

TAG_VALUE="${!TAG_VAR:-latest}"

SCRIPT_ARGS=()
[[ "$NO_CACHE" == true ]] && SCRIPT_ARGS+=("--no-cache")
[[ "$NO_PUSH" == true ]] && SCRIPT_ARGS+=("--no-push")

cache_state="enabled"
push_state="yes"
if [[ "$NO_CACHE" == true ]]; then
  cache_state="disabled"
fi
if [[ "$NO_PUSH" == true ]]; then
  push_state="no"
fi

info "$my_name" "========================================"
info "$my_name" "Building image: $SERVICE"
info "$my_name" "Script: $STEP_SCRIPT"
info "$my_name" "Tag var: $TAG_VAR"
info "$my_name" "Tag: $TAG_VALUE"
info "$my_name" "Cache: $cache_state"
info "$my_name" "Push:  $push_state"
info "$my_name" "========================================"

export "$TAG_VAR=$TAG_VALUE"
if [[ "$DIRECT_DQ_LLM" == true ]]; then
  "$ROOT_DIR/scripts/build_and_push_all.sh" --image dq-llm "${SCRIPT_ARGS[@]}"
else
  "$STEP_SCRIPT" "${SCRIPT_ARGS[@]}"
fi

info "$my_name" ""
success "$my_name" "Done: $SERVICE:$TAG_VALUE"