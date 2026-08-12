#!/usr/bin/env bash
###
# Name: build_and_push.sh
# Description: Build and push image to configured registry
# Usage: ./build_and_push.sh [--no-cache] [--no-push]
###

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DOCKER_DIR="$REPO_ROOT"

source "$REPO_ROOT/scripts/supporting/root_env_file.sh"
init_root_env_file "$REPO_ROOT"

# Preserve TAG variables that may have been exported from parent
SAVED_DQ_API_TAG="${DQ_API_TAG:-}"
SAVED_DQ_BASE_TAG="${DQ_BASE_TAG:-}"

if ! source_selected_root_env_file; then
    exit 1
fi

source "$REPO_ROOT/scripts/supporting/setup_env.sh"

# Restore exported TAGs if they were previously set
if [ -n "$SAVED_DQ_API_TAG" ]; then
    DQ_API_TAG="$SAVED_DQ_API_TAG"
fi
if [ -n "$SAVED_DQ_BASE_TAG" ]; then
    DQ_BASE_TAG="$SAVED_DQ_BASE_TAG"
fi

NO_CACHE=""
NO_PUSH=false

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
        -h|--help)
            cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build and push the dq-made-easy-api Docker image.

Options:
    --no-cache    Build without using Docker cache
    --no-push     Build only, do not push to registry
    -h, --help    Show this help message

Environment variables (from the selected root env file):
    DQ_API_REGISTRY      Docker registry (current: ${DQ_API_REGISTRY:-not set})
    DQ_API_NAMESPACE     Docker namespace (current: ${DQ_API_NAMESPACE:-not set})
    DQ_API_IMAGE         Image name (current: ${DQ_API_IMAGE:-not set})
    DQ_API_TAG           Image tag (current: ${DQ_API_TAG:-not set})

Full image name: ${DQ_API_REGISTRY:-}${DQ_API_NAMESPACE:-}${DQ_API_IMAGE:-}:${DQ_API_TAG:-}

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

if [ -z "${DQ_API_REGISTRY:-}" ] || [ -z "${DQ_API_NAMESPACE:-}" ] || [ -z "${DQ_API_IMAGE:-}" ] || [ -z "${DQ_API_TAG:-}" ]; then
    echo "ERROR: Missing required environment variables"
    echo "  DQ_API_REGISTRY: ${DQ_API_REGISTRY:-not set}"
    echo "  DQ_API_NAMESPACE: ${DQ_API_NAMESPACE:-not set}"
    echo "  DQ_API_IMAGE: ${DQ_API_IMAGE:-not set}"
    echo "  DQ_API_TAG: ${DQ_API_TAG:-not set}"
    exit 1
fi

if [ -z "${DQ_BASE_REGISTRY:-}" ] || [ -z "${DQ_BASE_NAMESPACE:-}" ] || [ -z "${DQ_BASE_IMAGE:-}" ] || [ -z "${DQ_BASE_TAG:-}" ]; then
    echo "ERROR: Missing base image environment variables required for dq-made-easy-api build"
    echo "  DQ_BASE_REGISTRY: ${DQ_BASE_REGISTRY:-not set}"
    echo "  DQ_BASE_NAMESPACE: ${DQ_BASE_NAMESPACE:-not set}"
    echo "  DQ_BASE_IMAGE: ${DQ_BASE_IMAGE:-not set}"
    echo "  DQ_BASE_TAG: ${DQ_BASE_TAG:-not set}"
    exit 1
fi

for variable in PIP_INDEX_URL PIP_EXTRA_INDEX_URL PIP_TRUSTED_HOST PYPI_SERVER_DNS; do
    if [ -z "${!variable:-}" ]; then
        echo "ERROR: $variable is required for the dq-api image build"
        exit 1
    fi
done

IMAGE_NAME="${DQ_API_REGISTRY}${DQ_API_NAMESPACE}${DQ_API_IMAGE}:${DQ_API_TAG}"
LATEST_NAME="${DQ_API_REGISTRY}${DQ_API_NAMESPACE}${DQ_API_IMAGE}:latest"

# Also tag with base version (e.g. 0.11-608c9b1 -> 0.11)
BASE_TAG="${DQ_API_TAG%%-*}"
if [ "$BASE_TAG" != "$DQ_API_TAG" ]; then
    VERSION_NAME="${DQ_API_REGISTRY}${DQ_API_NAMESPACE}${DQ_API_IMAGE}:${BASE_TAG}"
else
    VERSION_NAME=""
fi

echo "========================================"
echo "Building dq-made-easy-api Docker image"
echo "========================================"
echo "Image: $IMAGE_NAME"
echo "Latest: $LATEST_NAME"
[ -n "$VERSION_NAME" ] && echo "Version: $VERSION_NAME"
echo "Build directory: $DOCKER_DIR"
echo "Cache: $([ -z "$NO_CACHE" ] && echo "enabled" || echo "disabled")"
echo "Push to registry: $([ "$NO_PUSH" = false ] && echo "yes" || echo "no")"
echo "========================================"
echo ""

echo "Starting build..."
docker_build_tags=(-t "$IMAGE_NAME" -t "$LATEST_NAME")
[ -n "$VERSION_NAME" ] && docker_build_tags+=(-t "$VERSION_NAME")

if docker build --add-host "packages.host.dev.jac.dot=192.168.1.17" --add-host "docker-registery.host.dev.jac.dot=192.168.1.17" $NO_CACHE \
    --add-host "${PYPI_SERVER_HOST_DNS:-packages.host.dev.jac.dot}=192.168.1.17" \
    --secret id=pip_index_url,env=PIP_INDEX_URL \
    --build-arg PYTHON_DOCKER_REGISTRY="${PYTHON_DOCKER_REGISTRY}" \
    --build-arg PYTHON_DOCKER_NAMESPACE="${PYTHON_DOCKER_NAMESPACE}" \
    --build-arg PYTHON_DOCKER_IMAGE="${PYTHON_DOCKER_IMAGE}" \
    --build-arg PYTHON_DOCKER_TAG="${PYTHON_DOCKER_TAG}" \
    --build-arg DQ_BASE_REGISTRY="${DQ_BASE_REGISTRY}" \
    --build-arg DQ_BASE_NAMESPACE="${DQ_BASE_NAMESPACE}" \
    --build-arg DQ_BASE_IMAGE="${DQ_BASE_IMAGE}" \
    --build-arg DQ_BASE_TAG="${DQ_BASE_TAG}" \
    --build-arg PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL}" \
    --build-arg PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST}" \
    -f "$DOCKER_DIR/dq-api/Dockerfile.fastapi" \
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
