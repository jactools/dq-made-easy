#!/usr/bin/env bash
###
# Name: build_and_push.sh
# Description: Build and push dq-profiling image to Docker Hub
# Usage: ./build_and_push.sh [--no-cache] [--no-push]
###

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$ROOT_DIR"

source "$ROOT_DIR/../scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR/.."

# Preserve TAG variables that may have been exported from parent
SAVED_DQ_PROFILING_TAG="${DQ_PROFILING_TAG:-}"
SAVED_DQ_BASE_TAG="${DQ_BASE_TAG:-}"

if ! source_selected_root_env_file; then
    exit 1
fi

# Restore exported TAGs if they were previously set
if [ -n "$SAVED_DQ_PROFILING_TAG" ]; then
    DQ_PROFILING_TAG="$SAVED_DQ_PROFILING_TAG"
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

Build and push the dq-profiling Docker image.

Options:
    --no-cache    Build without using Docker cache
    --no-push     Build only, do not push to Docker Hub
    -h, --help    Show this help message

Environment variables (from the selected root env file):
    DQ_PROFILING_REGISTRY      Docker registry (current: ${DQ_PROFILING_REGISTRY:-not set})
    DQ_PROFILING_NAMESPACE     Docker namespace (current: ${DQ_PROFILING_NAMESPACE:-not set})
    DQ_PROFILING_IMAGE         Image name (current: ${DQ_PROFILING_IMAGE:-not set})
    DQ_PROFILING_TAG           Image tag (current: ${DQ_PROFILING_TAG:-not set})

Full image name: ${DQ_PROFILING_REGISTRY:-}${DQ_PROFILING_NAMESPACE:-}${DQ_PROFILING_IMAGE:-}:${DQ_PROFILING_TAG:-}

Before pushing to Docker Hub, make sure you're logged in:
    docker login docker.io

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

if [ -z "${DQ_PROFILING_REGISTRY:-}" ] || [ -z "${DQ_PROFILING_NAMESPACE:-}" ] || [ -z "${DQ_PROFILING_IMAGE:-}" ] || [ -z "${DQ_PROFILING_TAG:-}" ]; then
    echo "ERROR: Missing required environment variables"
    echo "  DQ_PROFILING_REGISTRY: ${DQ_PROFILING_REGISTRY:-not set}"
    echo "  DQ_PROFILING_NAMESPACE: ${DQ_PROFILING_NAMESPACE:-not set}"
    echo "  DQ_PROFILING_IMAGE: ${DQ_PROFILING_IMAGE:-not set}"
    echo "  DQ_PROFILING_TAG: ${DQ_PROFILING_TAG:-not set}"
    exit 1
fi

if [ -z "${DQ_BASE_REGISTRY:-}" ] || [ -z "${DQ_BASE_NAMESPACE:-}" ] || [ -z "${DQ_BASE_IMAGE:-}" ] || [ -z "${DQ_BASE_TAG:-}" ]; then
    echo "ERROR: Missing base image environment variables required for dq-profiling build"
    echo "  DQ_BASE_REGISTRY: ${DQ_BASE_REGISTRY:-not set}"
    echo "  DQ_BASE_NAMESPACE: ${DQ_BASE_NAMESPACE:-not set}"
    echo "  DQ_BASE_IMAGE: ${DQ_BASE_IMAGE:-not set}"
    echo "  DQ_BASE_TAG: ${DQ_BASE_TAG:-not set}"
    exit 1
fi

IMAGE_NAME="${DQ_PROFILING_REGISTRY}${DQ_PROFILING_NAMESPACE}${DQ_PROFILING_IMAGE}:${DQ_PROFILING_TAG}"
LATEST_NAME="${DQ_PROFILING_REGISTRY}${DQ_PROFILING_NAMESPACE}${DQ_PROFILING_IMAGE}:latest"

echo "========================================"
echo "Building dq-profiling Docker image"
echo "========================================"
echo "Image: $IMAGE_NAME"
echo "Latest: $LATEST_NAME"
echo "Build directory: $DOCKER_DIR"
echo "Cache: $([ -z "$NO_CACHE" ] && echo "enabled" || echo "disabled")"
echo "Push to registry: $([ "$NO_PUSH" = false ] && echo "yes" || echo "no")"
echo "========================================"
echo ""

echo "Starting build..."

# Ensure BuildKit is enabled (required for --secret and RUN --mount=type=secret).
export DOCKER_BUILDKIT=1

DOCKER_BUILD_SECRETS=()
if [ -f "$DOCKER_DIR/.npmrc" ]; then
    DOCKER_BUILD_SECRETS+=("--secret" "id=npmrc,src=$DOCKER_DIR/.npmrc")
fi

if docker build $NO_CACHE \
    "${DOCKER_BUILD_SECRETS[@]}" \
    --build-arg DQ_BASE_REGISTRY="${DQ_BASE_REGISTRY}" \
    --build-arg DQ_BASE_NAMESPACE="${DQ_BASE_NAMESPACE}" \
    --build-arg DQ_BASE_IMAGE="${DQ_BASE_IMAGE}" \
    --build-arg DQ_BASE_TAG="${DQ_BASE_TAG}" \
    --build-arg PIP_INDEX_URL="${PIP_INDEX_URL:-}" \
    -f "$DOCKER_DIR/Dockerfile.profiling" \
    -t "$IMAGE_NAME" \
    -t "$LATEST_NAME" \
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
    echo "Pushing to Docker Hub"
    echo "========================================"
    echo "Image: $IMAGE_NAME"
    echo ""

    if ! docker info | grep -q "Username"; then
        echo "WARNING: You may not be logged in to Docker Hub."
        echo "If push fails, please run: docker login docker.io"
        echo ""
    fi

    echo "Pushing image..."
    if docker push "$IMAGE_NAME" && docker push "$LATEST_NAME"; then
        echo ""
        echo "✓ Successfully pushed to Docker Hub!"
        echo "  Image: $IMAGE_NAME"
        echo "  Latest: $LATEST_NAME"
        echo ""
    else
        echo ""
        echo "✗ Push failed!"
        echo ""
        echo "If authentication failed, please login:"
        echo "  docker login docker.io"
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
