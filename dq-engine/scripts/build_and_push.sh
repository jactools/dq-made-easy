#!/usr/bin/env bash
###
# Name: build_and_push.sh
# Description: Build and push image to configured registry
# Usage: ./build_and_push.sh [--no-cache] [--no-push] [--skip-spark-warmup]
###

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$(cd "$ENGINE_DIR/.." && pwd)"

source "$DOCKER_DIR/scripts/supporting/root_env_file.sh"
init_root_env_file "$DOCKER_DIR"

# Preserve TAG variables that may have been exported from parent
SAVED_DQ_ENGINE_TAG="${DQ_ENGINE_TAG:-}"

if ! source_selected_root_env_file; then
    exit 1
fi

ROOT_DIR="$DOCKER_DIR"
source "$DOCKER_DIR/scripts/supporting/setup_env.sh"

ensure_local_spark_expectations_package() {
    local package_index_url="${TWINE_REPOSITORY_URL:-}"
    local package_index_username="${TWINE_USERNAME:-}"
    local package_index_password="${TWINE_PASSWORD:-}"
    local package_name="spark-expectations"
    local package_version="2.10.1"
    local package_index_page=""

    if [ "${INFRA_SOURCE:-}" != "HOME" ]; then
        return 0
    fi

    if [ -z "$package_index_url" ] || [ -z "$package_index_username" ] || [ -z "$package_index_password" ]; then
        echo "ERROR: TWINE_REPOSITORY_URL/TWINE_USERNAME/TWINE_PASSWORD are required to publish local vendor packages" >&2
        exit 1
    fi

    package_index_page="${package_index_url%/}/simple/${package_name}/"
    if curl -skLf -u "$package_index_username:$package_index_password" "$package_index_page" | grep -q "spark_expectations-${package_version}-"; then
        return 0
    fi

    echo "Publishing vendored ${package_name} ${package_version} to local PyPI server..."
    PACKAGE_RELEASE_PRINT_WHEEL_PATH=false \
    "$DOCKER_DIR/scripts/release_python_package.sh" spark-expectations --publish --repository-url "$package_index_url"
}

ensure_local_spark_expectations_package

PYTHON_BASE_IMAGE_REF="${REGISTRY:?REGISTRY is required}dq-made-easy-python-base:latest"

if [ -n "${NEXUSCLOUD_DOCKER_IO_REGISTRY:-}" ]; then
    if ! docker image inspect "$PYTHON_BASE_IMAGE_REF" >/dev/null 2>&1; then
        if ! python3 "$DOCKER_DIR/dq-engine/scripts/import_nexus_python_image.py" \
            --registry-url "$NEXUSCLOUD_DOCKER_IO_REGISTRY" \
            --image-ref "$PYTHON_BASE_IMAGE_REF" \
            --image-path "dq-made-easy-python-base" \
            --tag "latest" \
            --username "${NEXUSCLOUD_USERNAME:-}" \
            --password "${NEXUSCLOUD_PASSWORD:-}"; then
            echo "ERROR: failed to import Nexus Python base image: $PYTHON_BASE_IMAGE_REF" >&2
            exit 1
        fi
    fi
fi

# Restore exported TAG if it was previously set
if [ -n "$SAVED_DQ_ENGINE_TAG" ]; then
    DQ_ENGINE_TAG="$SAVED_DQ_ENGINE_TAG"
fi

NO_CACHE=""
NO_PUSH=false
# CLI args always override env vars
# Save the env var value so we can restore it if CLI doesn't set --skip-spark-warmup
SAVED_SKIP_SPARK_WARMUP="${SKIP_SPARK_WARMUP:-false}"
SKIP_SPARK_WARMUP=false
SKIP_SPARK_WARMUP_FROM_CLI=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --no-push)
            NO_PUSH=true
            shift
            ;;
        --skip-spark-warmup)
            SKIP_SPARK_WARMUP=true
            SKIP_SPARK_WARMUP_FROM_CLI=true
            shift
            ;;
        -h|--help)
            cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build and push the dq-made-easy-engine Docker image.

Options:
    --no-cache             Build without using Docker cache
    --no-push              Build only, do not push to registry
    --skip-spark-warmup    Skip the Spark jar warmup layer during image build
    -h, --help             Show this help message

Environment variables (from the selected root env file):
    DQ_ENGINE_REGISTRY      Docker registry (current: ${DQ_ENGINE_REGISTRY:-not set})
    DQ_ENGINE_NAMESPACE     Docker namespace (current: ${DQ_ENGINE_NAMESPACE:-not set})
    DQ_ENGINE_IMAGE         Image name (current: ${DQ_ENGINE_IMAGE:-not set})
    DQ_ENGINE_TAG           Image tag (current: ${DQ_ENGINE_TAG:-not set})

Full image name: ${DQ_ENGINE_REGISTRY:-}${DQ_ENGINE_NAMESPACE:-}${DQ_ENGINE_IMAGE:-}:${DQ_ENGINE_TAG:-}

Before pushing to registry, make sure you're logged in:
    docker login <registry>

EOF
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# If CLI didn't specify --skip-spark-warmup, restore the env var value
if [ "$SKIP_SPARK_WARMUP_FROM_CLI" = false ]; then
    SKIP_SPARK_WARMUP="$SAVED_SKIP_SPARK_WARMUP"
fi

if [ -z "${DQ_ENGINE_REGISTRY:-}" ] || [ -z "${DQ_ENGINE_NAMESPACE:-}" ] || [ -z "${DQ_ENGINE_IMAGE:-}" ] || [ -z "${DQ_ENGINE_TAG:-}" ]; then
    echo "ERROR: Missing required environment variables"
    echo "  DQ_ENGINE_REGISTRY: ${DQ_ENGINE_REGISTRY:-not set}"
    echo "  DQ_ENGINE_NAMESPACE: ${DQ_ENGINE_NAMESPACE:-not set}"
    echo "  DQ_ENGINE_IMAGE: ${DQ_ENGINE_IMAGE:-not set}"
    echo "  DQ_ENGINE_TAG: ${DQ_ENGINE_TAG:-not set}"
    exit 1
fi

for variable in PIP_INDEX_URL PIP_EXTRA_INDEX_URL PIP_TRUSTED_HOST; do
    if [ -z "${!variable:-}" ]; then
        echo "ERROR: $variable is required for the dq-engine image build"
        exit 1
    fi
done

IMAGE_NAME="${DQ_ENGINE_REGISTRY}${DQ_ENGINE_NAMESPACE}${DQ_ENGINE_IMAGE}:${DQ_ENGINE_TAG}"
LATEST_NAME="${DQ_ENGINE_REGISTRY}${DQ_ENGINE_NAMESPACE}${DQ_ENGINE_IMAGE}:latest"

# Also tag with base version (e.g. 0.11-608c9b1 -> 0.11)
BASE_TAG="${DQ_ENGINE_TAG%%-*}"
if [ "$BASE_TAG" != "$DQ_ENGINE_TAG" ]; then
    VERSION_NAME="${DQ_ENGINE_REGISTRY}${DQ_ENGINE_NAMESPACE}${DQ_ENGINE_IMAGE}:${BASE_TAG}"
else
    VERSION_NAME=""
fi

echo "========================================"
echo "Building dq-made-easy-engine Docker image"
echo "========================================"
echo "Image: $IMAGE_NAME"
echo "Latest: $LATEST_NAME"
[ -n "$VERSION_NAME" ] && echo "Version: $VERSION_NAME"
echo "Build directory: $DOCKER_DIR"
echo "Cache: $([ -z "$NO_CACHE" ] && echo "enabled" || echo "disabled")"
echo "Push to registry: $([ "$NO_PUSH" = false ] && echo "yes" || echo "no")"
echo "Spark warmup: $([ "$SKIP_SPARK_WARMUP" = true ] && echo "skipped" || echo "enabled")"
echo "========================================"
echo ""

echo "Starting build..."
docker_build_tags=(-t "$IMAGE_NAME" -t "$LATEST_NAME")
[ -n "$VERSION_NAME" ] && docker_build_tags+=(-t "$VERSION_NAME")

pypi_build_host="${PYPI_BUILD_HOST_DNS:-$(resolve_pypi_build_host || true)}"
docker_host_args=()
if [ -n "$pypi_build_host" ]; then
    if [ -z "${DOCKER_HOST_IP:-}" ]; then
        echo "ERROR: DOCKER_HOST_IP is required when PYPI_BUILD_HOST_DNS is set for the dq-engine image build"
        exit 1
    fi
    docker_host_args=(--add-host "${pypi_build_host}=${DOCKER_HOST_IP}")
fi

if docker build "${docker_host_args[@]}" $NO_CACHE \
    --secret id=pip_index_url,env=PIP_INDEX_URL \
    --build-arg PYTHON_DOCKER_REGISTRY="${PYTHON_DOCKER_REGISTRY}" \
    --build-arg PYTHON_DOCKER_NAMESPACE="${PYTHON_DOCKER_NAMESPACE}" \
    --build-arg PYTHON_DOCKER_IMAGE="${PYTHON_DOCKER_IMAGE}" \
    --build-arg PYTHON_DOCKER_TAG="${PYTHON_DOCKER_TAG}" \
    --build-arg PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL}" \
    --build-arg PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST}" \
    --build-arg MAVEN_REPOSITORIES="${MAVEN_REPOSITORIES:-}" \
    --build-arg SKIP_SPARK_WARMUP="$SKIP_SPARK_WARMUP" \
    -f "$DOCKER_DIR/dq-engine/Dockerfile.engine" \
    "${docker_build_tags[@]}" \
    "$DOCKER_DIR"; then
    echo ""
    echo "✓ Build successful!"
    echo ""
else
    echo ""
    echo "✗ Build failed!"
    exit 1
fi

if [ "$NO_PUSH" = false ]; then
    echo "========================================"
    echo "Pushing to registry"
    echo "========================================"
    echo "Image: $IMAGE_NAME"
    echo ""

    if ! docker info | grep -q "Username"; then
        echo "WARNING: You may not be logged in to the registry."
        echo "If push fails, please run: docker login <registry>"
        echo ""
    fi

    echo "Pushing image..."
    push_ok=true
    docker push "$IMAGE_NAME" || push_ok=false
    docker push "$LATEST_NAME" || push_ok=false
    [ -n "$VERSION_NAME" ] && { docker push "$VERSION_NAME" || push_ok=false; }
    if [ "$push_ok" = true ]; then
        echo ""
        echo "✓ Successfully pushed to registry!"
        echo "  Image: $IMAGE_NAME"
        echo "  Latest: $LATEST_NAME"
        [ -n "$VERSION_NAME" ] && echo "  Version: $VERSION_NAME"
        echo ""
    else
        echo ""
        echo "✗ Push failed!"
        echo ""
        echo "If authentication failed, please login:"
        echo "  docker login <registry>"
        echo ""
        echo "Then run this script again (build will be cached):"
        echo "  ./scripts/build_and_push.sh"
        exit 1
    fi
else
    echo "Skipping push (--no-push specified)"
fi

echo "========================================"
echo "Done!"
echo "========================================"
echo ""
echo "Image details:"
docker images "$IMAGE_NAME" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
echo ""

exit 0
