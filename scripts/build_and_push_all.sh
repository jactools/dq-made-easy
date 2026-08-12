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
SKIP_SPARK_WARMUP=false
VERSION_TAG=""
BUILD_SCOPE="core"
SELECTED_IMAGES=()
REPO_BUILD_PLATFORMS="${REPO_BUILD_PLATFORMS:-linux/amd64,linux/arm64}"
LOCAL_BUILD_PLATFORM="${LOCAL_BUILD_PLATFORM:-}"
BUILDX_BUILDER_NAME="${BUILDX_BUILDER_NAME:-dqbuilder}"
OVERRIDE_REGISTRY=""
BUILT_IMAGES=0
PUSHED_IMAGES=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build repository Docker images.

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file
  --source local|corporate  Use public PyPI or corporate Nexus for dependency resolution

Default scope (core):
  1) dq-made-easy-base
  2) dq-made-easy-api
  3) dq-made-easy-engine
  4) dq-made-easy-profiling
  5) dq-made-easy-frontend
  6) dq-made-easy-db

Repo scope (repo) builds the core set plus auxiliary repo-managed images:
  7) dq-made-easy-db-seed
  8) dq-made-easy-keycloak-seed-artifacts
  9) dq-made-easy-openmetadata-db
 10) dq-made-easy-openmetadata-server
 11) dq-made-easy-metadata-configure
 12) dq-made-easy-zammad-seed
 13) dq-made-easy-kafka-consumer
 14) dq-made-easy-edge
 15) dq-made-easy-zammad-origin

Options:
  --scope <core|repo>  Select image scope (default: core)
  --all-repo-images    Alias for: --scope repo
  --image <name>       Build only the named repo-managed image (repeatable)
  --no-cache           Build without Docker cache
  --no-push            Build only, do not push images
  --skip-spark-warmup  Skip the Spark jar warmup layer for dq-made-easy-engine
  --version <tag>      Use a specific version tag for all built images
  --registry <target>  Override target registry: LOCAL, CORPORATE, or PUBLIC
  -h, --help           Show this help message

Target registries:
  LOCAL      Push to LOCAL_DOCKER_REGISTRY (default from REPO_SWITCH)
  CORPORATE  Push to CORPORATE_DOCKER_REGISTRY
  PUBLIC     Push to PUBLIC_DOCKER_REGISTRY (docker.io)

Notes:
  - By default, tags are generated from actual Docker build inputs per image.
  - Frontend image expects dq-ui/dist to exist before building.
  - Existing per-service build scripts are used for the core publishable images.
  - Auxiliary repo images are built directly from this script in repo scope.
  - Repo-managed wrapper images publish as multi-arch manifests for linux/amd64 and linux/arm64.
  - --no-push keeps repo-managed wrapper images local-only via a single-platform build/load.
EOF
}

if [ "$#" -eq 0 ]; then
  usage
  exit 0
fi

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
      # Convert short names to full names (e.g. dq-kafka-consumer -> dq-made-easy-kafka-consumer)
      image_name="$2"
      case "$image_name" in
        dq-base|dq-api|dq-engine|dq-profiling|dq-frontend|dq-db|dq-kafka|dq-kafka-consumer|dq-edge|dq-db-seed|dq-keycloak-seed-artifacts|dq-openmetadata-db|dq-openmetadata-server|dq-metadata-configure|dq-container-metrics|dq-zammad-seed)
          image_name="dq-made-easy-${image_name#dq-}"
          ;;
      esac
      append_unique_selected_image "$image_name"
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
    --skip-spark-warmup)
      SKIP_SPARK_WARMUP=true
      shift
      ;;
    --registry)
      if [[ -z "${2:-}" ]]; then
        error "$my_name" "--registry requires a target (LOCAL, CORPORATE, or PUBLIC)"
        exit 1
      fi
      OVERRIDE_REGISTRY="${2^^}"  # uppercase
      if [[ "$OVERRIDE_REGISTRY" != "LOCAL" && "$OVERRIDE_REGISTRY" != "CORPORATE" && "$OVERRIDE_REGISTRY" != "PUBLIC" ]]; then
        error "$my_name" "Invalid registry target '$OVERRIDE_REGISTRY' (expected LOCAL, CORPORATE, or PUBLIC)"
        exit 1
      fi
      shift 2
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

# Override registry vars when --registry is specified
if [ -n "$OVERRIDE_REGISTRY" ]; then
  case "$OVERRIDE_REGISTRY" in
    LOCAL)     target="LOCAL_DOCKER_REGISTRY" ;;
    CORPORATE) target="CORPORATE_DOCKER_REGISTRY" ;;
    PUBLIC)    target="PUBLIC_DOCKER_REGISTRY" ;;
  esac
  local_registry="${!target}"
  if [ -z "$local_registry" ]; then
    error "$my_name" "$target is not set in $ROOT_ENV_FILE"
    exit 1
  fi
  REPO_SWITCH="$OVERRIDE_REGISTRY"
  info "$my_name" "Override: all registries -> $target ($local_registry)"

  # Override all image registry vars
  export REGISTRY="$local_registry"
  for var in PG_REGISTRY KEYCLOAK_REGISTRY NODE_REGISTRY REDIS_REGISTRY \
             DQ_BASE_REGISTRY DQ_API_REGISTRY DQ_ENGINE_REGISTRY DQ_PROFILING_REGISTRY \
             DQ_DB_REGISTRY DQ_FRONTEND_REGISTRY DQ_DB_SEED_REGISTRY DQ_KEYCLOAK_SEED_REGISTRY \
             DQ_KAFKA_CONSUMER_REGISTRY DQ_OPENMETADATA_DB_REGISTRY DQ_OPENMETADATA_SERVER_REGISTRY \
             DQ_METADATA_CONFIGURE_REGISTRY DQ_CONTAINER_METRICS_REGISTRY DQ_ZAMMAD_SEED_REGISTRY \
             DQ_ZAMMAD_ORIGIN_REGISTRY DQ_KAFKA_REGISTRY PYTHON_DOCKER_REGISTRY; do
    export "$var=$local_registry"
  done
fi

source "$ROOT_DIR/scripts/supporting/setup_env.sh"

# Export PIP_INDEX_URL so child build scripts can inherit it
export PIP_INDEX_URL="${PIP_INDEX_URL:-}"
export PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL:-}"
export PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-}"
debug "$my_name" "Using root env file: $ROOT_ENV_FILE"
debug "$my_name" "ROOT_DIR: $ROOT_DIR"

export ROOT_ENV_FILE

expand_selected_image_dependencies

derive_docker_domain() {
  local host="${NEXUSCLOUD_HOSTNAME:-}"
  if [ -z "$host" ] && [ -n "${NEXUSCLOUD_DNS:-}" ]; then
    host="${NEXUSCLOUD_DNS#//}"
  fi
  if [ -z "$host" ]; then
    return 1
  fi
  local suffix
  suffix="$(printf '%s' "$host" | sed 's/^[^.]*\.//')"
  if [ -z "$suffix" ] || [ "$suffix" = "$host" ]; then
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
  local builder_container_name="buildx_buildkit_${BUILDX_BUILDER_NAME}0"
  local builder_network_mode=""
  local buildkitd_config_path="$ROOT_DIR/tmp/buildkitd.${BUILDX_BUILDER_NAME}.toml"
  local registry_authority="${PYTHON_DOCKER_REGISTRY:-${REGISTRY:-}}"
  local registry_ca_file="$ROOT_DIR/certs/mkcert-rootCA.pem"
  local create_args=(--use --name "$BUILDX_BUILDER_NAME" --driver-opt network=host)

  registry_authority="${registry_authority%/}"
  if [ -n "$registry_authority" ] && [ -f "$registry_ca_file" ]; then
    mkdir -p "$ROOT_DIR/tmp"
    cat > "$buildkitd_config_path" <<EOF
[registry."$registry_authority"]
  ca=["$registry_ca_file"]
EOF
    create_args+=(--buildkitd-config "$buildkitd_config_path")
  fi

  if ! docker buildx version >/dev/null 2>&1; then
    error "$my_name" "docker buildx is required to publish repo-managed images"
    exit 1
  fi

  if ! docker buildx inspect "$BUILDX_BUILDER_NAME" >/dev/null 2>&1; then
    info "$my_name" "Creating docker buildx builder '$BUILDX_BUILDER_NAME'..."
    docker buildx create "${create_args[@]}" >/dev/null
  else
    builder_network_mode="$(docker inspect "$builder_container_name" --format '{{.HostConfig.NetworkMode}}' 2>/dev/null || true)"
    if [ "$builder_network_mode" != "host" ] || ! docker exec "$builder_container_name" test -f /etc/buildkit/buildkitd.toml >/dev/null 2>&1; then
      warning "$my_name" "Recreating docker buildx builder '$BUILDX_BUILDER_NAME' with local registry access and CA trust"
      docker buildx rm "$BUILDX_BUILDER_NAME" >/dev/null 2>&1 || true
      docker buildx create "${create_args[@]}" >/dev/null
      return 0
    fi
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

refresh_docker_hub_description() {
  local image_name="$1"

  if [ "$NO_PUSH" = true ]; then
    return 0
  fi

  # Only update Docker Hub description when pushing to Docker Hub
  case "${REPO_SWITCH:-LOCAL}" in
    CORPORATE|PUBLIC) ;;
    *) return 0 ;;
  esac

  if [ -z "${DOCKER_HUB_TOKEN:-}" ]; then
    debug "$my_name" "Skipping Docker Hub description update (DOCKER_HUB_TOKEN not set)"
    return 0
  fi

  info "$my_name" "Refreshing Docker Hub description for $image_name..."
  bash "$ROOT_DIR/scripts/update_docker_hub.sh" --image "$image_name" || true
}

run_script_step() {
  local step_name="$1"
  local step_script="$2"
  local tag_var
  local -a step_args=("${SCRIPT_ARGS[@]}")
  if [ "$step_name" = "dq-made-easy-engine" ] && [ "${#ENGINE_SCRIPT_ARGS[@]}" -gt 0 ]; then
    step_args+=("${ENGINE_SCRIPT_ARGS[@]}")
  fi
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
  "$step_script" "${step_args[@]}"

  BUILT_IMAGES=$((BUILT_IMAGES + 1))
  if [ "$NO_PUSH" = false ]; then
    PUSHED_IMAGES=$((PUSHED_IMAGES + 1))
  fi

  refresh_docker_hub_description "$step_name"
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

  # Also tag with base version (e.g. 0.11-b3f8d57 -> 0.11)
  local base_tag="${tag_value%%-*}"
  local version_name=""
  if [ "$base_tag" != "$tag_value" ]; then
      version_name="${image_repo}:${base_tag}"
  fi

  emit_step_header "$step_name" "$dockerfile_path" "$tag_value"
  [ -n "$version_name" ] && info "$my_name" "Version tag: $version_name"

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

  local pypi_build_host="${PYPI_SERVER_HOST_DNS:-${PYPI_SERVER_DNS:-}}"
  local mkcert_root_ca_file=""
  local internal_root_ca_file="${ROOT_DIR}/tmp/certs/internal-root-ca-2024.crt"
  local internal_ca_bundle_file="${INTERNAL_CA_BUNDLE_FILE:-}"
  if [[ -z "${DOCKER_HOST_IP:-}" ]]; then
    error "$my_name" "DOCKER_HOST_IP is required for local image builds"
    return 1
  fi
  if [[ -z "$pypi_build_host" ]]; then
    error "$my_name" "PYPI_SERVER_HOST_DNS or PYPI_SERVER_DNS is required for local image builds"
    return 1
  fi

  docker_cmd+=(--add-host "${pypi_build_host}=${DOCKER_HOST_IP}")
  if [[ -n "${PYPI_SERVER_DNS:-}" && "${PYPI_SERVER_DNS}" != "$pypi_build_host" ]]; then
    docker_cmd+=(--add-host "${PYPI_SERVER_DNS}=${DOCKER_HOST_IP}")
  fi

  if [[ -f "$ROOT_DIR/certs/mkcert-rootCA.pem" ]]; then
    mkcert_root_ca_file="$ROOT_DIR/certs/mkcert-rootCA.pem"
  elif [[ -f "$ROOT_DIR/tmp/certs/mkcert-rootCA.pem" ]]; then
    mkcert_root_ca_file="$ROOT_DIR/tmp/certs/mkcert-rootCA.pem"
  fi
  if [[ -n "$mkcert_root_ca_file" ]]; then
    docker_cmd+=(--secret "id=internal_mkcert_root_ca,src=$mkcert_root_ca_file")
  fi
  if [[ -f "$internal_root_ca_file" ]]; then
    docker_cmd+=(--secret "id=internal_root_ca,src=$internal_root_ca_file")
  fi
  if [[ -n "$internal_ca_bundle_file" && -f "$internal_ca_bundle_file" ]]; then
    docker_cmd+=(--secret "id=internal_ca_bundle,src=$internal_ca_bundle_file")
  fi

  # Handle pip_index_url secret for BuildKit mounts
  local pip_index_url_secret=""
  for build_arg in "$@"; do
    if [[ "$build_arg" == PIP_INDEX_URL=* ]]; then
      local pip_url="${build_arg#PIP_INDEX_URL=}"
      if [[ -n "$pip_url" ]]; then
        pip_index_url_secret=$(mktemp /tmp/pip_index.XXXXXX)
        echo "$pip_url" > "$pip_index_url_secret"
        docker_cmd+=(--secret "id=pip_index_url,src=$pip_index_url_secret")
      fi
    else
      docker_cmd+=(--build-arg "$build_arg")
    fi
  done

  docker_cmd+=(-f "$dockerfile_path" -t "$image_name" -t "$latest_name")
  [ -n "$version_name" ] && docker_cmd+=(-t "$version_name")
  docker_cmd+=("$build_context")

  # Cleanup pip_index_url secret after build
  local cleanup_secret="$pip_index_url_secret"
  "${docker_cmd[@]}"
  if [[ -n "$cleanup_secret" && -f "$cleanup_secret" ]]; then
    rm -f "$cleanup_secret"
  fi

  # Ensure local tags exist after push (push --platform doesn't create local tags)
  if [ "$NO_PUSH" = false ]; then
    docker tag "$image_name" "$latest_name" >/dev/null 2>&1 || true
    [ -n "$version_name" ] && docker tag "$image_name" "$version_name" >/dev/null 2>&1 || true
  fi

  BUILT_IMAGES=$((BUILT_IMAGES + 1))
  if [ "$NO_PUSH" = false ]; then
    PUSHED_IMAGES=$((PUSHED_IMAGES + 1))
  fi

  if [ "$NO_PUSH" = true ]; then
    info "$my_name" "Skipping push (--no-push specified); loaded local image for platform ${build_platform}"
  else
    refresh_docker_hub_description "$step_name"
  fi
}

docker_login



# Kafka broker is managed by platform-foundation (platform-kafka).

# Trino image/container lifecycle managed by platform-foundation (platform-trino).

# Airflow image/container lifecycle managed by platform-foundation (platform-airflow).

export DQ_DB_SEED_REGISTRY DQ_DB_SEED_NAMESPACE DQ_DB_SEED_IMAGE
export DQ_KEYCLOAK_SEED_REGISTRY DQ_KEYCLOAK_SEED_NAMESPACE DQ_KEYCLOAK_SEED_IMAGE
# Kafka broker is managed by platform-foundation (platform-kafka).
export DQ_KAFKA_CONSUMER_REGISTRY DQ_KAFKA_CONSUMER_NAMESPACE DQ_KAFKA_CONSUMER_IMAGE
# Trino image/container lifecycle managed by platform-foundation (platform-trino).
export DQ_EDGE_REGISTRY DQ_EDGE_NAMESPACE DQ_EDGE_IMAGE
export DQ_OPENMETADATA_DB_REGISTRY DQ_OPENMETADATA_DB_NAMESPACE DQ_OPENMETADATA_DB_IMAGE
export DQ_OPENMETADATA_SERVER_REGISTRY DQ_OPENMETADATA_SERVER_NAMESPACE DQ_OPENMETADATA_SERVER_IMAGE
export DQ_METADATA_CONFIGURE_REGISTRY DQ_METADATA_CONFIGURE_NAMESPACE DQ_METADATA_CONFIGURE_IMAGE
export DQ_CONTAINER_METRICS_REGISTRY DQ_CONTAINER_METRICS_NAMESPACE DQ_CONTAINER_METRICS_IMAGE
export DQ_ZAMMAD_SEED_REGISTRY DQ_ZAMMAD_SEED_NAMESPACE DQ_ZAMMAD_SEED_IMAGE
export DQ_ZAMMAD_ORIGIN_REGISTRY DQ_ZAMMAD_ORIGIN_NAMESPACE DQ_ZAMMAD_ORIGIN_IMAGE

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
  # Kong image/container lifecycle managed by platform-foundation
  export DQ_DB_TAG="$VERSION_TAG"
  # Keycloak image/container lifecycle managed by platform-foundation
  export DQ_DB_SEED_TAG="$VERSION_TAG"
  export DQ_KEYCLOAK_SEED_TAG="$VERSION_TAG"
  # Kafka broker is managed by platform-foundation (platform-kafka).
  export DQ_KAFKA_CONSUMER_TAG="$VERSION_TAG"
  # Trino image/container lifecycle managed by platform-foundation (platform-trino).
  export DQ_EDGE_TAG="$VERSION_TAG"
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
ENGINE_SCRIPT_ARGS=()
if [ "$SKIP_SPARK_WARMUP" = true ]; then
  ENGINE_SCRIPT_ARGS+=("--skip-spark-warmup")
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
# Kong image/container lifecycle managed by platform-foundation
# (bootstrap_kong.sh retained in dq-made-easy for route/ACL deployment)
if image_selected "dq-made-easy-db"; then
  run_script_step "dq-made-easy-db" "$ROOT_DIR/dq-db/scripts/build_and_push.sh"
fi
# Keycloak image/container lifecycle managed by platform-foundation
# (seed artifacts retained in dq-made-easy for realm/user generation)

if [ "$BUILD_SCOPE" = "repo" ]; then
  ensure_buildx_builder

  if image_selected "dq-made-easy-db-seed"; then
    run_direct_build_step \
      "dq-made-easy-db-seed" \
      "DQ_DB_SEED_TAG" \
      "${DQ_DB_SEED_REGISTRY}${DQ_DB_SEED_NAMESPACE}${DQ_DB_SEED_IMAGE}" \
      "$ROOT_DIR/dq-db/Dockerfile.dq-db.seed" \
      "$ROOT_DIR" \
      "PYTHON_DOCKER_REGISTRY=${PYTHON_DOCKER_REGISTRY}" \
      "PYTHON_DOCKER_NAMESPACE=${PYTHON_DOCKER_NAMESPACE}" \
      "PYTHON_DOCKER_IMAGE=${PYTHON_DOCKER_IMAGE}" \
      "PYTHON_DOCKER_TAG=${PYTHON_DOCKER_TAG}" \
      "PIP_INDEX_URL=${PIP_INDEX_URL}" \
      "PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}" \
      "PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}"
  fi

  if image_selected "dq-made-easy-keycloak-seed-artifacts"; then
    run_direct_build_step \
      "dq-made-easy-keycloak-seed-artifacts" \
      "DQ_KEYCLOAK_SEED_TAG" \
      "${DQ_KEYCLOAK_SEED_REGISTRY}${DQ_KEYCLOAK_SEED_NAMESPACE}${DQ_KEYCLOAK_SEED_IMAGE}" \
      "$ROOT_DIR/dq-keycloak/Dockerfile.keycloak.seed" \
      "$ROOT_DIR" \
      "PYTHON_DOCKER_REGISTRY=${PYTHON_DOCKER_REGISTRY}" \
      "PYTHON_DOCKER_NAMESPACE=${PYTHON_DOCKER_NAMESPACE}" \
      "PYTHON_DOCKER_IMAGE=${PYTHON_DOCKER_IMAGE}" \
      "PYTHON_DOCKER_TAG=${PYTHON_DOCKER_TAG}"
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
      "OPENMETADATA_BASE_IMAGE=${OPENMETADATA_REGISTRY}${OPENMETADATA_NAMESPACE}${OPENMETADATA_IMAGE}:${OPENMETADATA_TAG}" \
        "OTEL_JAVAAGENT_HELPER_IMAGE=${OTEL_JAVAAGENT_HELPER_IMAGE?OTEL_JAVAAGENT_HELPER_IMAGE is required}" \
      "OTEL_JAVAAGENT_VERSION=${OTEL_JAVAAGENT_VERSION:-2.16.0}"
  fi

  if image_selected "dq-made-easy-metadata-configure"; then
    run_direct_build_step \
      "dq-made-easy-metadata-configure" \
      "DQ_METADATA_CONFIGURE_TAG" \
      "${DQ_METADATA_CONFIGURE_REGISTRY}${DQ_METADATA_CONFIGURE_NAMESPACE}${DQ_METADATA_CONFIGURE_IMAGE}" \
      "$ROOT_DIR/dq-metadata/Dockerfile.configure" \
      "$ROOT_DIR" \
      "PYTHON_DOCKER_REGISTRY=${PYTHON_DOCKER_REGISTRY}" \
      "PYTHON_DOCKER_NAMESPACE=${PYTHON_DOCKER_NAMESPACE}" \
      "PYTHON_DOCKER_IMAGE=${PYTHON_DOCKER_IMAGE}" \
      "PYTHON_DOCKER_TAG=${PYTHON_DOCKER_TAG}" \
      "PIP_INDEX_URL=${PIP_INDEX_URL}" \
      "PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}" \
      "PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}"
  fi

  if image_selected "dq-made-easy-zammad-seed"; then
    run_direct_build_step \
      "dq-made-easy-zammad-seed" \
      "DQ_ZAMMAD_SEED_TAG" \
      "${DQ_ZAMMAD_SEED_REGISTRY}${DQ_ZAMMAD_SEED_NAMESPACE}${DQ_ZAMMAD_SEED_IMAGE}" \
      "$ROOT_DIR/docker/Dockerfile.zammad.seed" \
      "$ROOT_DIR" \
      "PYTHON_DOCKER_REGISTRY=${PYTHON_DOCKER_REGISTRY}" \
      "PYTHON_DOCKER_NAMESPACE=${PYTHON_DOCKER_NAMESPACE}" \
      "PYTHON_DOCKER_IMAGE=${PYTHON_DOCKER_IMAGE}" \
      "PYTHON_DOCKER_TAG=${PYTHON_DOCKER_TAG}" \
      "PIP_INDEX_URL=${PIP_INDEX_URL}" \
      "PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}" \
      "PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}"
  fi

  # DQ-specific consumer remains here.
  if image_selected "dq-made-easy-kafka-consumer"; then
    run_direct_build_step \
      "dq-made-easy-kafka-consumer" \
      "DQ_KAFKA_CONSUMER_TAG" \
      "${DQ_KAFKA_CONSUMER_REGISTRY}${DQ_KAFKA_CONSUMER_NAMESPACE}${DQ_KAFKA_CONSUMER_IMAGE}" \
      "$ROOT_DIR/dq-kafka-consumer/Dockerfile.kafka-consumer" \
      "$ROOT_DIR/dq-kafka-consumer" \
      "PYTHON_DOCKER_REGISTRY=${PYTHON_DOCKER_REGISTRY}" \
      "PYTHON_DOCKER_NAMESPACE=${PYTHON_DOCKER_NAMESPACE}" \
      "PYTHON_DOCKER_IMAGE=${PYTHON_DOCKER_IMAGE}" \
      "PYTHON_DOCKER_TAG=${PYTHON_DOCKER_TAG}" \
        "PIP_INDEX_URL=${PIP_INDEX_URL}" \
      "PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}" \
      "PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}"
  fi

  # Trino image/container lifecycle managed by platform-foundation (platform-trino).
  if image_selected "dq-made-easy-edge"; then
    run_direct_build_step \
      "dq-made-easy-edge" \
      "DQ_EDGE_TAG" \
      "${DQ_EDGE_REGISTRY}${DQ_EDGE_NAMESPACE}${DQ_EDGE_IMAGE}" \
      "$ROOT_DIR/dq-edge/Dockerfile.edge" \
      "$ROOT_DIR/dq-edge"
  fi

  # Airflow image/container lifecycle managed by platform-foundation (platform-airflow).
  if image_selected "dq-made-easy-zammad-origin"; then
    run_direct_build_step \
      "dq-made-easy-zammad-origin" \
      "DQ_ZAMMAD_ORIGIN_TAG" \
      "${DQ_ZAMMAD_ORIGIN_REGISTRY}${DQ_ZAMMAD_ORIGIN_NAMESPACE}${DQ_ZAMMAD_ORIGIN_IMAGE}" \
      "$ROOT_DIR/docker/Dockerfile.zammad-origin" \
      "$ROOT_DIR" \
      "ZAMMAD_IMAGE=${ZAMMAD_REGISTRY}${ZAMMAD_NAMESPACE}${ZAMMAD_IMAGE}:${ZAMMAD_TAG}"
  fi
fi

info "$my_name" ""
info "$my_name" "========================================"
success "$my_name" "Build/push steps completed successfully"
info "$my_name" "Scope: $BUILD_SCOPE"
info "$my_name" "Images built: $BUILT_IMAGES"
info "$my_name" "Images pushed: $PUSHED_IMAGES (target: $REGISTRY)"
if [ -z "$VERSION_TAG" ]; then
  info "$my_name" "Images were tagged from Docker-input content hashes"
else
  info "$my_name" "Version used: $VERSION_TAG"
fi
info "$my_name" "========================================"

exit 0
