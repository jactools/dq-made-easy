#!/usr/bin/env bash
set -euo pipefail

# Purpose: Build and optionally push repository Docker images.
#
# What it does:
# - Builds core product images by default in a fixed order.
# - Can optionally build all repo-managed custom images, including seed and metadata helpers.
# - Optionally skips push and/or disables build cache.
# - Supports automatic content-hash version tags (or a manual override).
# - Publishes repo-managed wrapper images as multi-arch manifests when pushing.
#
# Version: 1.5
# Last modified: 2026-07-01
# Changelog:
# - 1.3 (2026-04-27): Rewrote the repo build flow to use buildx multi-arch publishing and preserve a local-only --no-push path.
# - 1.4 (2026-06-10): Require explicit OpenMetadata base and helper image settings instead of falling back to registry defaults.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/stack_catalog.sh"
init_root_env_file "$ROOT_DIR"

my_name="build_and_push_all.sh"

NO_CACHE=false
NO_PUSH=false
VERSION_TAG=""
BUILD_SCOPE="core"
SELECTED_IMAGES=()
REPO_BUILD_PLATFORMS="${REPO_BUILD_PLATFORMS:-linux/amd64,linux/arm64}"
LOCAL_BUILD_PLATFORM="${LOCAL_BUILD_PLATFORM:-}"
BUILDX_BUILDER_NAME="${BUILDX_BUILDER_NAME:-dqbuilder}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build repository Docker images.

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file

Default scope (core):
  1) dq-made-easy-base
  2) dq-made-easy-api
  3) dq-made-easy-engine
  4) dq-made-easy-profiling
  5) dq-made-easy-frontend
  6) dq-made-easy-kong
  7) dq-made-easy-db
  8) dq-made-easy-keycloak

Repo scope (repo) builds the core set plus auxiliary repo-managed images:
  9) dq-made-easy-db-seed
 10) dq-made-easy-keycloak-seed-artifacts
 11) dq-made-easy-openmetadata-db
 12) dq-made-easy-openmetadata-server
 13) dq-made-easy-metadata-configure
 14) dq-made-easy-container-metrics
 15) dq-made-easy-zammad-seed
 16) dq-made-easy-llm
 17) dq-made-easy-kafka
 18) dq-made-easy-kafka-consumer
 19) dq-made-easy-trino
 20) dq-made-easy-edge
 21) dq-made-easy-airflow

Options:
  --scope <core|repo>  Select image scope (default: core)
  --all-repo-images    Alias for: --scope repo
  --image <name>       Build only the named repo-managed image (repeatable)
  --no-cache           Build without Docker cache
  --no-push            Build only, do not push images
  --version <tag>      Use a specific version tag for all built images
  -h, --help           Show this help message

Notes:
  - By default, tags are generated from actual Docker build inputs per image.
  - Frontend image expects dq-ui/dist to exist before building.
  - Existing per-service build scripts are used for the core publishable images.
  - Auxiliary repo images are built directly from this script in repo scope.
  - Repo-managed wrapper images publish as multi-arch manifests for linux/amd64 and linux/arm64.
  - --no-push keeps repo-managed wrapper images local-only via a single-platform build/load.
EOF
}

image_selected() {
  local candidate="$1"
  local selected_image

  if [ "${#SELECTED_IMAGES[@]}" -eq 0 ]; then
    return 0
  fi

  for selected_image in "${SELECTED_IMAGES[@]}"; do
    if [ "$selected_image" = "$candidate" ]; then
      return 0
    fi
  done

  return 1
}

append_unique_selected_image() {
  local candidate="$1"
  local selected_image

  for selected_image in "${SELECTED_IMAGES[@]}"; do
    if [ "$selected_image" = "$candidate" ]; then
      return 0
    fi
  done

  SELECTED_IMAGES+=("$candidate")
}

expand_selected_image_dependencies() {
  local requested_images=()
  local image=""

  if [ "${#SELECTED_IMAGES[@]}" -eq 0 ]; then
    return 0
  fi

  requested_images=("${SELECTED_IMAGES[@]}")
  SELECTED_IMAGES=()

  for image in "${requested_images[@]}"; do
    case "$image" in
      dq-made-easy-api|dq-made-easy-profiling)
        append_unique_selected_image "dq-made-easy-base"
        ;;
    esac
    append_unique_selected_image "$image"
  done
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
        core|repo) BUILD_SCOPE="$2" ;;
        *)
          error "$my_name" "Unsupported scope '$2' (expected: core or repo)"
          exit 1
          ;;
      esac
      shift 2
      ;;
    --all-repo-images)
      BUILD_SCOPE="repo"
      shift
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
      append_unique_selected_image "$2"
      if ! is_core_repo_image "$2"; then
        BUILD_SCOPE="repo"
      fi
      shift 2
      ;;
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
      info "$my_name" "Use --help for usage information"
      exit 1
      ;;
  esac
done

if ! source_selected_root_env_file; then
  exit 1
fi

export ROOT_ENV_FILE

expand_selected_image_dependencies

derive_docker_domain() {
  local dns="${NEXUSCLOUD_DNS:-}"
  dns="${dns#//}"
  if [ -z "$dns" ]; then
    return 1
  fi
  local suffix
  suffix="$(printf '%s' "$dns" | sed 's/^[^.]*\.//')"
  if [ -z "$suffix" ] || [ "$suffix" = "$dns" ]; then
    return 1
  fi
  printf '%s' "group-docker-19.${suffix}"
}

detect_local_platform() {
  local platform
  local os_name
  local architecture

  platform="$(docker info --format '{{.OSType}}/{{.Architecture}}' 2>/dev/null || true)"
  if [ -n "$platform" ] && [ "$platform" != "/" ]; then
    os_name="${platform%%/*}"
    architecture="${platform##*/}"
  else
    os_name="$(uname -s | tr '[:upper:]' '[:lower:]')"
    architecture="$(uname -m)"
  fi

  case "$architecture" in
    x86_64) architecture="amd64" ;;
    aarch64) architecture="arm64" ;;
  esac

  case "$architecture" in
    amd64|arm64) : ;;
    *)
      error "$my_name" "Unsupported local architecture for buildx load path: $architecture"
      exit 1
      ;;
  esac

  printf '%s/%s' "$os_name" "$architecture"
}

ensure_buildx_builder() {
  if ! docker buildx version >/dev/null 2>&1; then
    error "$my_name" "docker buildx is required to publish repo-managed images"
    exit 1
  fi

  if ! docker buildx inspect "$BUILDX_BUILDER_NAME" >/dev/null 2>&1; then
    info "$my_name" "Creating docker buildx builder '$BUILDX_BUILDER_NAME'..."
    docker buildx create --use --name "$BUILDX_BUILDER_NAME" >/dev/null
  else
    docker buildx use "$BUILDX_BUILDER_NAME" >/dev/null 2>&1 || true
  fi
}

docker_login() {
  local docker_domain="${DOCKER_DOMAIN:-}"
  if [ -z "$docker_domain" ]; then
    docker_domain="$(derive_docker_domain || true)"
  fi

  if [ -n "$docker_domain" ] && [ -n "${NEXUSCLOUD_USERNAME:-}" ] && [ -n "${NEXUSCLOUD_PASSWORD:-}" ]; then
    info "$my_name" "Logging in to Nexus group Docker registry: ${docker_domain}"
    printf '%s' "${NEXUSCLOUD_PASSWORD}" | docker login "${docker_domain}" --username "${NEXUSCLOUD_USERNAME}" --password-stdin >/dev/null
  fi

  if [ "$NO_PUSH" = true ]; then
    return
  fi

  if [ -n "${DOCKER_HUB_USERNAME:-}" ] && [ -n "${DOCKER_HUB_TOKEN:-}" ]; then
    info "$my_name" "Logging in to Docker Hub as ${DOCKER_HUB_USERNAME}"
    printf '%s' "${DOCKER_HUB_TOKEN}" | docker login --username "${DOCKER_HUB_USERNAME}" --password-stdin >/dev/null
  fi
}

emit_step_header() {
  local step_name="$1"
  local step_source="$2"
  local tag_value="$3"

  info "$my_name" ""
  info "$my_name" "========================================"
  info "$my_name" "Step: $step_name"
  info "$my_name" "Source: $step_source"
  info "$my_name" "Tag: $tag_value"
  info "$my_name" "========================================"
}

run_script_step() {
  local step_name="$1"
  local step_script="$2"
  local tag_var
  tag_var="$(printf '%s' "$step_name" | tr '[:lower:]-' '[:upper:]_')_TAG"

  if [ "$step_name" = "dq-made-easy-frontend" ]; then
    tag_var="DQ_FRONTEND_TAG"
  fi

  local tag_value="${!tag_var:-latest}"
  emit_step_header "$step_name" "$step_script" "$tag_value"

  if [ ! -x "$step_script" ]; then
    if [ -f "$step_script" ]; then
      chmod +x "$step_script"
    else
        error "$my_name" "Script not found: $step_script"
      exit 1
    fi
  fi

  export "$tag_var=$tag_value"
  "$step_script" "${SCRIPT_ARGS[@]}"
}

run_direct_build_step() {
  local step_name="$1"
  local tag_var="$2"
  local image_repo="$3"
  local dockerfile_path="$4"
  local build_context="$5"
  shift 5

  if [ -z "$image_repo" ]; then
    error "$my_name" "Image repository is empty for step $step_name"
    exit 1
  fi

  local tag_value="${!tag_var:-latest}"
  local image_name="${image_repo}:${tag_value}"
  local latest_name="${image_repo}:latest"
  local -a docker_cmd
  local build_platform=""

  emit_step_header "$step_name" "$dockerfile_path" "$tag_value"

  if [ "$NO_PUSH" = true ]; then
    if [ -z "$LOCAL_BUILD_PLATFORM" ]; then
      LOCAL_BUILD_PLATFORM="$(detect_local_platform)"
    fi
    build_platform="$LOCAL_BUILD_PLATFORM"
    docker_cmd=(docker buildx build --load --platform "$build_platform")
  else
    docker_cmd=(docker buildx build --push --platform "$REPO_BUILD_PLATFORMS")
  fi

  if [ "$NO_CACHE" = true ]; then
    docker_cmd+=(--no-cache)
  fi
  for build_arg in "$@"; do
    docker_cmd+=(--build-arg "$build_arg")
  done
  docker_cmd+=(-f "$dockerfile_path" -t "$image_name" -t "$latest_name" "$build_context")

  "${docker_cmd[@]}"

  if [ "$NO_PUSH" = true ]; then
    info "$my_name" "Skipping push (--no-push specified); loaded local image for platform ${build_platform}"
  fi
}

docker_login

DQ_DB_SEED_REGISTRY="${DQ_DB_SEED_REGISTRY:-${DQ_DB_REGISTRY:-docker.io/}}"
DQ_DB_SEED_NAMESPACE="${DQ_DB_SEED_NAMESPACE:-${DQ_DB_NAMESPACE:-jacbeekers/}}"
DQ_DB_SEED_IMAGE="${DQ_DB_SEED_IMAGE:-dq-made-easy-db-seed}"

DQ_KEYCLOAK_SEED_REGISTRY="${DQ_KEYCLOAK_SEED_REGISTRY:-${DQ_KEYCLOAK_REGISTRY:-docker.io/}}"
DQ_KEYCLOAK_SEED_NAMESPACE="${DQ_KEYCLOAK_SEED_NAMESPACE:-${DQ_KEYCLOAK_NAMESPACE:-jacbeekers/}}"
DQ_KEYCLOAK_SEED_IMAGE="${DQ_KEYCLOAK_SEED_IMAGE:-dq-made-easy-keycloak-seed-artifacts}"

DQ_KAFKA_REGISTRY="${DQ_KAFKA_REGISTRY:-docker.io/}"
DQ_KAFKA_NAMESPACE="${DQ_KAFKA_NAMESPACE:-jacbeekers/}"
DQ_KAFKA_IMAGE="${DQ_KAFKA_IMAGE:-dq-made-easy-kafka}"

DQ_KAFKA_CONSUMER_REGISTRY="${DQ_KAFKA_CONSUMER_REGISTRY:-docker.io/}"
DQ_KAFKA_CONSUMER_NAMESPACE="${DQ_KAFKA_CONSUMER_NAMESPACE:-jacbeekers/}"
DQ_KAFKA_CONSUMER_IMAGE="${DQ_KAFKA_CONSUMER_IMAGE:-dq-made-easy-kafka-consumer}"

DQ_TRINO_REGISTRY="${DQ_TRINO_REGISTRY:-docker.io/}"
DQ_TRINO_NAMESPACE="${DQ_TRINO_NAMESPACE:-jacbeekers/}"
DQ_TRINO_IMAGE="${DQ_TRINO_IMAGE:-dq-made-easy-trino}"

DQ_EDGE_REGISTRY="${DQ_EDGE_REGISTRY:-docker.io/}"
DQ_EDGE_NAMESPACE="${DQ_EDGE_NAMESPACE:-jacbeekers/}"
DQ_EDGE_IMAGE="${DQ_EDGE_IMAGE:-dq-made-easy-edge}"

DQ_AIRFLOW_REGISTRY="${DQ_AIRFLOW_REGISTRY:-docker.io/}"
DQ_AIRFLOW_NAMESPACE="${DQ_AIRFLOW_NAMESPACE:-jacbeekers/}"
DQ_AIRFLOW_IMAGE="${DQ_AIRFLOW_IMAGE:-dq-made-easy-airflow}"

DQ_LLM_REGISTRY="${DQ_LLM_REGISTRY:-docker.io/}"
DQ_LLM_NAMESPACE="${DQ_LLM_NAMESPACE:-jacbeekers/}"
DQ_LLM_IMAGE="${DQ_LLM_IMAGE:-dq-made-easy-llm}"

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

export DQ_DB_SEED_REGISTRY DQ_DB_SEED_NAMESPACE DQ_DB_SEED_IMAGE
export DQ_KEYCLOAK_SEED_REGISTRY DQ_KEYCLOAK_SEED_NAMESPACE DQ_KEYCLOAK_SEED_IMAGE
export DQ_KAFKA_REGISTRY DQ_KAFKA_NAMESPACE DQ_KAFKA_IMAGE
export DQ_KAFKA_CONSUMER_REGISTRY DQ_KAFKA_CONSUMER_NAMESPACE DQ_KAFKA_CONSUMER_IMAGE
export DQ_TRINO_REGISTRY DQ_TRINO_NAMESPACE DQ_TRINO_IMAGE
export DQ_EDGE_REGISTRY DQ_EDGE_NAMESPACE DQ_EDGE_IMAGE
export DQ_AIRFLOW_REGISTRY DQ_AIRFLOW_NAMESPACE DQ_AIRFLOW_IMAGE
export DQ_LLM_REGISTRY DQ_LLM_NAMESPACE DQ_LLM_IMAGE
export DQ_OPENMETADATA_DB_REGISTRY DQ_OPENMETADATA_DB_NAMESPACE DQ_OPENMETADATA_DB_IMAGE
export DQ_OPENMETADATA_SERVER_REGISTRY DQ_OPENMETADATA_SERVER_NAMESPACE DQ_OPENMETADATA_SERVER_IMAGE
export DQ_METADATA_CONFIGURE_REGISTRY DQ_METADATA_CONFIGURE_NAMESPACE DQ_METADATA_CONFIGURE_IMAGE
export DQ_CONTAINER_METRICS_REGISTRY DQ_CONTAINER_METRICS_NAMESPACE DQ_CONTAINER_METRICS_IMAGE
export DQ_ZAMMAD_SEED_REGISTRY DQ_ZAMMAD_SEED_NAMESPACE DQ_ZAMMAD_SEED_IMAGE

if [ -z "$VERSION_TAG" ]; then
  source "$ROOT_DIR/scripts/calculate_versions.sh"
  info "$my_name" "Auto-detected version tags based on Docker build inputs:"
  "$ROOT_DIR/scripts/calculate_versions.sh" --display >&2
else
  export DQ_BASE_TAG="$VERSION_TAG"
  export DQ_API_TAG="$VERSION_TAG"
  export DQ_ENGINE_TAG="$VERSION_TAG"
  export DQ_PROFILING_TAG="$VERSION_TAG"
  export DQ_FRONTEND_TAG="$VERSION_TAG"
  export DQ_KONG_TAG="$VERSION_TAG"
  export DQ_DB_TAG="$VERSION_TAG"
  export DQ_KEYCLOAK_TAG="$VERSION_TAG"
  export DQ_DB_SEED_TAG="$VERSION_TAG"
  export DQ_KEYCLOAK_SEED_TAG="$VERSION_TAG"
  export DQ_KAFKA_TAG="$VERSION_TAG"
  export DQ_KAFKA_CONSUMER_TAG="$VERSION_TAG"
  export DQ_TRINO_TAG="$VERSION_TAG"
  export DQ_EDGE_TAG="$VERSION_TAG"
  export DQ_AIRFLOW_TAG="$VERSION_TAG"
  export DQ_LLM_TAG="$VERSION_TAG"
  export DQ_OPENMETADATA_DB_TAG="$VERSION_TAG"
  export DQ_OPENMETADATA_SERVER_TAG="$VERSION_TAG"
  export DQ_METADATA_CONFIGURE_TAG="$VERSION_TAG"
  export DQ_CONTAINER_METRICS_TAG="$VERSION_TAG"
  export DQ_ZAMMAD_SEED_TAG="$VERSION_TAG"
fi

SCRIPT_ARGS=()
if [ "$NO_CACHE" = true ]; then
  SCRIPT_ARGS+=("--no-cache")
fi
if [ "$NO_PUSH" = true ]; then
  SCRIPT_ARGS+=("--no-push")
fi

info "$my_name" "========================================"
if [ "$BUILD_SCOPE" = "repo" ]; then
  info "$my_name" "Building all repo-managed Docker images"
else
  info "$my_name" "Building core product Docker images"
fi
info "$my_name" "========================================"
info "$my_name" "Root directory: $ROOT_DIR"
info "$my_name" "Env file: $ROOT_ENV_FILE"
info "$my_name" "Image scope: $BUILD_SCOPE"
if [ -z "$VERSION_TAG" ]; then
  info "$my_name" "Version strategy: Docker-input content hashing"
else
  info "$my_name" "Version tag: $VERSION_TAG (manual override)"
fi
cache_state="enabled"
push_state="yes"
if [ "$NO_CACHE" = true ]; then
  cache_state="disabled"
fi
if [ "$NO_PUSH" = true ]; then
  push_state="no"
fi
info "$my_name" "Cache: $cache_state"
info "$my_name" "Push to registry: $push_state"
if [ "${#SELECTED_IMAGES[@]}" -gt 0 ]; then
  info "$my_name" "Selected images: ${SELECTED_IMAGES[*]}"
fi
info "$my_name" "========================================"

if [ ! -d "$ROOT_DIR/dq-ui/dist" ]; then
  warning "$my_name" "Frontend dist directory not found at $ROOT_DIR/dq-ui/dist"
  warning "$my_name" "Frontend build may fail. Build UI assets first if needed."
fi

if image_selected "dq-made-easy-base"; then
  run_script_step "dq-made-easy-base" "$ROOT_DIR/dq-base/scripts/build_and_push.sh"
fi
if image_selected "dq-made-easy-api"; then
  run_script_step "dq-made-easy-api" "$ROOT_DIR/dq-api/scripts/build_and_push.sh"
fi
if image_selected "dq-made-easy-engine"; then
  run_script_step "dq-made-easy-engine" "$ROOT_DIR/dq-engine/scripts/build_and_push.sh"
fi
if image_selected "dq-made-easy-profiling"; then
  run_script_step "dq-made-easy-profiling" "$ROOT_DIR/dq-profiling/scripts/build_and_push.sh"
fi
if image_selected "dq-made-easy-frontend"; then
  run_script_step "dq-made-easy-frontend" "$ROOT_DIR/dq-ui/scripts/build_and_push.sh"
fi
if image_selected "dq-made-easy-kong"; then
  run_script_step "dq-made-easy-kong" "$ROOT_DIR/dq-kong/scripts/build_and_push.sh"
fi
if image_selected "dq-made-easy-db"; then
  run_script_step "dq-made-easy-db" "$ROOT_DIR/dq-db/scripts/build_and_push.sh"
fi
if image_selected "dq-made-easy-keycloak"; then
  run_script_step "dq-made-easy-keycloak" "$ROOT_DIR/dq-keycloak/scripts/build_and_push.sh"
fi

if [ "$BUILD_SCOPE" = "repo" ]; then
  ensure_buildx_builder

  if image_selected "dq-made-easy-db-seed"; then
    run_direct_build_step \
      "dq-made-easy-db-seed" \
      "DQ_DB_SEED_TAG" \
      "${DQ_DB_SEED_REGISTRY}${DQ_DB_SEED_NAMESPACE}${DQ_DB_SEED_IMAGE}" \
      "$ROOT_DIR/dq-db/Dockerfile.dq-db.seed" \
      "$ROOT_DIR" \
      "PIP_INDEX_URL=${PIP_INDEX_URL:-}"
  fi

  if image_selected "dq-made-easy-keycloak-seed-artifacts"; then
    run_direct_build_step \
      "dq-made-easy-keycloak-seed-artifacts" \
      "DQ_KEYCLOAK_SEED_TAG" \
      "${DQ_KEYCLOAK_SEED_REGISTRY}${DQ_KEYCLOAK_SEED_NAMESPACE}${DQ_KEYCLOAK_SEED_IMAGE}" \
      "$ROOT_DIR/dq-keycloak/Dockerfile.keycloak.seed" \
      "$ROOT_DIR"
  fi

  if image_selected "dq-made-easy-openmetadata-db"; then
    run_direct_build_step \
      "dq-made-easy-openmetadata-db" \
      "DQ_OPENMETADATA_DB_TAG" \
      "${DQ_OPENMETADATA_DB_REGISTRY}${DQ_OPENMETADATA_DB_NAMESPACE}${DQ_OPENMETADATA_DB_IMAGE}" \
      "$ROOT_DIR/dq-metadata/Dockerfile.openmetadata-db" \
      "$ROOT_DIR" \
      "OPENMETADATA_DB_BASE_IMAGE=${OPENMETADATA_DB_BASE_IMAGE?OPENMETADATA_DB_BASE_IMAGE is required}"
  fi

  if image_selected "dq-made-easy-openmetadata-server"; then
    run_direct_build_step \
      "dq-made-easy-openmetadata-server" \
      "DQ_OPENMETADATA_SERVER_TAG" \
      "${DQ_OPENMETADATA_SERVER_REGISTRY}${DQ_OPENMETADATA_SERVER_NAMESPACE}${DQ_OPENMETADATA_SERVER_IMAGE}" \
      "$ROOT_DIR/dq-metadata/Dockerfile.openmetadata-server" \
      "$ROOT_DIR" \
      "OPENMETADATA_BASE_IMAGE=${OPENMETADATA_REGISTRY:-docker.io/}${OPENMETADATA_NAMESPACE:-}${OPENMETADATA_IMAGE:-openmetadata/server}:${OPENMETADATA_TAG:-latest}" \
        "OTEL_JAVAAGENT_HELPER_IMAGE=${OTEL_JAVAAGENT_HELPER_IMAGE?OTEL_JAVAAGENT_HELPER_IMAGE is required}" \
      "OTEL_JAVAAGENT_VERSION=${OTEL_JAVAAGENT_VERSION:-2.16.0}"
  fi

  if image_selected "dq-made-easy-metadata-configure"; then
    run_direct_build_step \
      "dq-made-easy-metadata-configure" \
      "DQ_METADATA_CONFIGURE_TAG" \
      "${DQ_METADATA_CONFIGURE_REGISTRY}${DQ_METADATA_CONFIGURE_NAMESPACE}${DQ_METADATA_CONFIGURE_IMAGE}" \
      "$ROOT_DIR/dq-metadata/Dockerfile.configure" \
      "$ROOT_DIR"
  fi

  if image_selected "dq-made-easy-container-metrics"; then
    run_direct_build_step \
      "dq-made-easy-container-metrics" \
      "DQ_CONTAINER_METRICS_TAG" \
      "${DQ_CONTAINER_METRICS_REGISTRY}${DQ_CONTAINER_METRICS_NAMESPACE}${DQ_CONTAINER_METRICS_IMAGE}" \
      "$ROOT_DIR/observability/container-metrics/Dockerfile.container-metrics" \
      "$ROOT_DIR/observability/container-metrics" \
      "PIP_INDEX_URL=${PIP_INDEX_URL:-}"
  fi

  if image_selected "dq-made-easy-zammad-seed"; then
    run_direct_build_step \
      "dq-made-easy-zammad-seed" \
      "DQ_ZAMMAD_SEED_TAG" \
      "${DQ_ZAMMAD_SEED_REGISTRY}${DQ_ZAMMAD_SEED_NAMESPACE}${DQ_ZAMMAD_SEED_IMAGE}" \
      "$ROOT_DIR/docker/Dockerfile.zammad.seed" \
      "$ROOT_DIR" \
      "PIP_INDEX_URL=${PIP_INDEX_URL:-}"
  fi

  if image_selected "dq-made-easy-llm"; then
    run_direct_build_step \
      "dq-made-easy-llm" \
      "DQ_LLM_TAG" \
      "${DQ_LLM_REGISTRY}${DQ_LLM_NAMESPACE}${DQ_LLM_IMAGE}" \
      "$ROOT_DIR/dq-llm/Dockerfile.llm" \
      "$ROOT_DIR/dq-llm" \
      "PIP_INDEX_URL=${PIP_INDEX_URL:-}"
  fi

  if image_selected "dq-made-easy-kafka"; then
    run_direct_build_step \
      "dq-made-easy-kafka" \
      "DQ_KAFKA_TAG" \
      "${DQ_KAFKA_REGISTRY}${DQ_KAFKA_NAMESPACE}${DQ_KAFKA_IMAGE}" \
      "$ROOT_DIR/dq-kafka/Dockerfile.kafka" \
      "$ROOT_DIR/dq-kafka"
  fi

  if image_selected "dq-made-easy-kafka-consumer"; then
    run_direct_build_step \
      "dq-made-easy-kafka-consumer" \
      "DQ_KAFKA_CONSUMER_TAG" \
      "${DQ_KAFKA_CONSUMER_REGISTRY}${DQ_KAFKA_CONSUMER_NAMESPACE}${DQ_KAFKA_CONSUMER_IMAGE}" \
      "$ROOT_DIR/dq-kafka-consumer/Dockerfile.kafka-consumer" \
      "$ROOT_DIR/dq-kafka-consumer" \
      "PIP_INDEX_URL=${PIP_INDEX_URL:-}"
  fi

  if image_selected "dq-made-easy-trino"; then
    run_direct_build_step \
      "dq-made-easy-trino" \
      "DQ_TRINO_TAG" \
      "${DQ_TRINO_REGISTRY}${DQ_TRINO_NAMESPACE}${DQ_TRINO_IMAGE}" \
      "$ROOT_DIR/dq-trino/Dockerfile.trino" \
      "$ROOT_DIR/dq-trino" \
      "TRINO_BASE_IMAGE=${TRINO_BASE_IMAGE:-trinodb/trino:482}"
  fi

  if image_selected "dq-made-easy-edge"; then
    run_direct_build_step \
      "dq-made-easy-edge" \
      "DQ_EDGE_TAG" \
      "${DQ_EDGE_REGISTRY}${DQ_EDGE_NAMESPACE}${DQ_EDGE_IMAGE}" \
      "$ROOT_DIR/dq-edge/Dockerfile.edge" \
      "$ROOT_DIR/dq-edge"
  fi

  if image_selected "dq-made-easy-airflow"; then
    info "$my_name" "Preparing Airflow build artifacts..."
    bash "$ROOT_DIR/scripts/package-releases/build_dq_airflow_wheels.sh"
    bash "$ROOT_DIR/scripts/build_dq_airflow_dag_artifact.sh"
    run_direct_build_step \
      "dq-made-easy-airflow" \
      "DQ_AIRFLOW_TAG" \
      "${DQ_AIRFLOW_REGISTRY}${DQ_AIRFLOW_NAMESPACE}${DQ_AIRFLOW_IMAGE}" \
      "$ROOT_DIR/docker/airflow/Dockerfile.airflow" \
      "$ROOT_DIR"
  fi
fi

info "$my_name" ""
info "$my_name" "========================================"
success "$my_name" "Build/push steps completed successfully"
info "$my_name" "Scope: $BUILD_SCOPE"
if [ -z "$VERSION_TAG" ]; then
  info "$my_name" "Images were tagged from Docker-input content hashes"
else
  info "$my_name" "Version used: $VERSION_TAG"
fi
info "$my_name" "========================================"

exit 0
