#!/usr/bin/env bash
set -euo pipefail

# Purpose: Pull repo-managed dq-made-easy Docker images from the configured registry.
# What it does:
# - Loads image registry/tag configuration from the selected canonical root env file.
# - Supports pulling either the default image scope or an explicit image subset.
# - Supports semantic version overrides via calculate_versions.sh.
# Version: 2.1
# Last modified: 2026-07-01

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/stack_catalog.sh"
init_root_env_file "$ROOT_DIR"

my_name="pull_images.sh"

PULL_SCOPE="core"
VERSION=""
SELECTED_IMAGES=()
FAILED_IMAGES=()

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] [VERSION]

Pull repo-managed Docker images.

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file

Options:
  --scope <core|repo>      Pull the default core or full repo-managed image scope (default: core)
  --image <name>           Pull only the named repo-managed image (repeatable)
  --version <tag>          Override tags for this pull operation
  -h, --help               Show this help message

Core images:
  dq-made-easy-base dq-made-easy-api dq-made-easy-engine dq-made-easy-profiling dq-made-easy-frontend dq-made-easy-kong dq-made-easy-db dq-made-easy-keycloak

Auxiliary repo images:
  dq-made-easy-db-seed dq-made-easy-keycloak-seed-artifacts dq-made-easy-openmetadata-db dq-made-easy-openmetadata-server
  dq-made-easy-metadata-configure dq-made-easy-container-metrics dq-made-easy-zammad-seed dq-made-easy-llm

Examples:
  $(basename "$0")
  $(basename "$0") --scope repo
  $(basename "$0") --image dq-made-easy-api --image dq-made-easy-frontend
  $(basename "$0") --env prod --scope repo --version 0.9.0
EOF
}

append_unique_image() {
  local candidate="$1"
  local existing

  for existing in "${SELECTED_IMAGES[@]}"; do
    if [ "$existing" = "$candidate" ]; then
      return 0
    fi
  done

  SELECTED_IMAGES+=("$candidate")
}

set_aux_image_defaults() {
  DQ_DB_SEED_REGISTRY="${DQ_DB_SEED_REGISTRY:-${DQ_DB_REGISTRY:-docker.io/}}"
  DQ_DB_SEED_NAMESPACE="${DQ_DB_SEED_NAMESPACE:-${DQ_DB_NAMESPACE:-jacbeekers/}}"
  DQ_DB_SEED_IMAGE="${DQ_DB_SEED_IMAGE:-dq-made-easy-db-seed}"

  DQ_KEYCLOAK_SEED_REGISTRY="${DQ_KEYCLOAK_SEED_REGISTRY:-${DQ_KEYCLOAK_REGISTRY:-docker.io/}}"
  DQ_KEYCLOAK_SEED_NAMESPACE="${DQ_KEYCLOAK_SEED_NAMESPACE:-${DQ_KEYCLOAK_NAMESPACE:-jacbeekers/}}"
  DQ_KEYCLOAK_SEED_IMAGE="${DQ_KEYCLOAK_SEED_IMAGE:-dq-made-easy-keycloak-seed-artifacts}"

  DQ_OPENMETADATA_DB_REGISTRY="${DQ_OPENMETADATA_DB_REGISTRY:-docker.io/}"
  DQ_OPENMETADATA_DB_NAMESPACE="${DQ_OPENMETADATA_DB_NAMESPACE:-jacbeekers/}"
  DQ_OPENMETADATA_DB_IMAGE="${DQ_OPENMETADATA_DB_IMAGE:-dq-made-easy-openmetadata-db}"

  DQ_OPENMETADATA_SERVER_REGISTRY="${DQ_OPENMETADATA_SERVER_REGISTRY:-docker.io/}"
  DQ_OPENMETADATA_SERVER_NAMESPACE="${DQ_OPENMETADATA_SERVER_NAMESPACE:-jacbeekers/}"
  DQ_OPENMETADATA_SERVER_IMAGE="${DQ_OPENMETADATA_SERVER_IMAGE:-dq-made-easy-openmetadata}"

  DQ_METADATA_CONFIGURE_REGISTRY="${DQ_METADATA_CONFIGURE_REGISTRY:-docker.io/}"
  DQ_METADATA_CONFIGURE_NAMESPACE="${DQ_METADATA_CONFIGURE_NAMESPACE:-jacbeekers/}"
  DQ_METADATA_CONFIGURE_IMAGE="${DQ_METADATA_CONFIGURE_IMAGE:-dq-made-easy-metadata-configure}"

  DQ_CONTAINER_METRICS_REGISTRY="${DQ_CONTAINER_METRICS_REGISTRY:-docker.io/}"
  DQ_CONTAINER_METRICS_NAMESPACE="${DQ_CONTAINER_METRICS_NAMESPACE:-jacbeekers/}"
  DQ_CONTAINER_METRICS_IMAGE="${DQ_CONTAINER_METRICS_IMAGE:-dq-made-easy-container-metrics}"

  DQ_ZAMMAD_SEED_REGISTRY="${DQ_ZAMMAD_SEED_REGISTRY:-docker.io/}"
  DQ_ZAMMAD_SEED_NAMESPACE="${DQ_ZAMMAD_SEED_NAMESPACE:-jacbeekers/}"
  DQ_ZAMMAD_SEED_IMAGE="${DQ_ZAMMAD_SEED_IMAGE:-dq-made-easy-zammad-seed}"

  DQ_LLM_REGISTRY="${DQ_LLM_REGISTRY:-docker.io/}"
  DQ_LLM_NAMESPACE="${DQ_LLM_NAMESPACE:-jacbeekers/}"
  DQ_LLM_IMAGE="${DQ_LLM_IMAGE:-dq-made-easy-llm}"
}

set_override_tags() {
  local image=""
  local vars=()
  local tag_var=""

  if [ -z "$VERSION" ]; then
    return 0
  fi

  if [[ "$VERSION" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]]; then
    MAJOR_MINOR_OVERRIDE="$VERSION" source "$ROOT_DIR/scripts/calculate_versions.sh"
    return 0
  fi

  while IFS= read -r image; do
    vars=( $(repo_image_env_vars "$image") )
    tag_var="${vars[3]}"
    printf -v "$tag_var" '%s' "$VERSION"
    export "$tag_var"
  done < <(repo_image_values)
}

resolve_selected_images() {
  local image=""

  if [ "${#SELECTED_IMAGES[@]}" -gt 0 ]; then
    return 0
  fi

  case "$PULL_SCOPE" in
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
      error "$my_name" "Unsupported scope '$PULL_SCOPE'"
      exit 1
      ;;
  esac
}

resolve_full_image_name() {
  local image="$1"
  local vars=()
  local registry_var=""
  local namespace_var=""
  local image_var=""
  local tag_var=""
  local registry=""
  local namespace=""
  local image_name=""
  local tag=""

  vars=( $(repo_image_env_vars "$image") )
  registry_var="${vars[0]}"
  namespace_var="${vars[1]}"
  image_var="${vars[2]}"
  tag_var="${vars[3]}"

  registry="${!registry_var:-}"
  namespace="${!namespace_var:-}"
  image_name="${!image_var:-}"
  tag="${!tag_var:-}"

  if [ -z "$registry" ] || [ -z "$image_name" ] || [ -z "$tag" ]; then
    error "$my_name" "Missing image configuration for $image"
    error "$my_name" "  $registry_var=${registry:-<empty>}"
    error "$my_name" "  $namespace_var=${namespace:-<empty>}"
    error "$my_name" "  $image_var=${image_name:-<empty>}"
    error "$my_name" "  $tag_var=${tag:-<empty>}"
    exit 1
  fi

  printf '%s' "${registry}${namespace}${image_name}:${tag}"
}

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  usage
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scope)
      if [[ -z "${2:-}" ]]; then
        error "$my_name" "--scope requires core or repo"
        exit 1
      fi
      case "$2" in
        core|repo)
          PULL_SCOPE="$2"
          ;;
        *)
          error "$my_name" "Unsupported scope '$2'"
          exit 1
          ;;
      esac
      shift 2
      ;;
    --image)
      if [[ -z "${2:-}" ]]; then
        error "$my_name" "--image requires a repo-managed image name"
        exit 1
      fi
      if ! is_repo_managed_image "$2"; then
        error "$my_name" "Unsupported image '$2'"
        exit 1
      fi
      append_unique_image "$2"
      if ! is_core_repo_image "$2"; then
        PULL_SCOPE="repo"
      fi
      shift 2
      ;;
    --version)
      if [[ -z "${2:-}" ]]; then
        error "$my_name" "--version requires a tag value"
        exit 1
      fi
      VERSION="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      error "$my_name" "Unknown option '$1'"
      usage
      exit 1
      ;;
    *)
      if [ -n "$VERSION" ]; then
        error "$my_name" "Multiple VERSION values supplied"
        exit 1
      fi
      VERSION="$1"
      shift
      ;;
  esac
 done

if ! source_selected_root_env_file; then
  exit 1
fi

source "$SCRIPT_DIR/supporting/setup_env.sh"
set_aux_image_defaults
resolve_selected_images
set_override_tags

info "$my_name" "========================================"
info "$my_name" "Pulling dq-made-easy images"
info "$my_name" "========================================"
info "$my_name" "Env file: $ROOT_ENV_FILE"
info "$my_name" "Scope: $PULL_SCOPE"
if [ -n "$VERSION" ]; then
  info "$my_name" "Version override: $VERSION"
fi
info "$my_name" "Images: ${SELECTED_IMAGES[*]}"
info "$my_name" "========================================"

success_count=0
fail_count=0

for image in "${SELECTED_IMAGES[@]}"; do
  full_image="$(resolve_full_image_name "$image")"
  info "$my_name" "Pulling: $full_image"

  if docker pull "$full_image"; then
    success "$my_name" "pulled $image"
    success_count=$((success_count+1))
  else
    error "$my_name" "unable to pull $image"
    FAILED_IMAGES+=("$image")
    fail_count=$((fail_count+1))
  fi
  info "$my_name" ""
done

info "$my_name" "========================================"
info "$my_name" "Pull summary"
info "$my_name" "========================================"
info "$my_name" "Successful: $success_count"
info "$my_name" "Failed: $fail_count"

if [ "$fail_count" -gt 0 ]; then
  error "$my_name" "Failed images: ${FAILED_IMAGES[*]}"
  exit 1
fi

success "$my_name" "All selected images pulled successfully."
