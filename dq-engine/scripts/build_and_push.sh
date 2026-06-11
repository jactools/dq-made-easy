#!/usr/bin/env bash
###
# Name: build_and_push.sh
# Description: Build and push dq-engine image to Docker Hub
# Usage: ./build_and_push.sh [--no-cache] [--no-push]
###

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$ROOT_DIR/.."

source "$ROOT_DIR/../scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR/.."

# Preserve TAG variables that may have been exported from parent
SAVED_DQ_ENGINE_TAG="${DQ_ENGINE_TAG:-}"

if ! source_selected_root_env_file; then
    exit 1
fi

# Restore exported TAG if it was previously set
if [ -n "$SAVED_DQ_ENGINE_TAG" ]; then
    DQ_ENGINE_TAG="$SAVED_DQ_ENGINE_TAG"
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

Build and push the dq-engine Docker image.

Options:
    --no-cache    Build without using Docker cache
    --no-push     Build only, do not push to Docker Hub
    -h, --help    Show this help message

Environment variables (from the selected root env file):
    DQ_ENGINE_REGISTRY      Docker registry (current: ${DQ_ENGINE_REGISTRY:-not set})
    DQ_ENGINE_NAMESPACE     Docker namespace (current: ${DQ_ENGINE_NAMESPACE:-not set})
    DQ_ENGINE_IMAGE         Image name (current: ${DQ_ENGINE_IMAGE:-not set})
    DQ_ENGINE_TAG           Image tag (current: ${DQ_ENGINE_TAG:-not set})

Full image name: ${DQ_ENGINE_REGISTRY:-}${DQ_ENGINE_NAMESPACE:-}${DQ_ENGINE_IMAGE:-}:${DQ_ENGINE_TAG:-}

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

if [ -z "${DQ_ENGINE_REGISTRY:-}" ] || [ -z "${DQ_ENGINE_NAMESPACE:-}" ] || [ -z "${DQ_ENGINE_IMAGE:-}" ] || [ -z "${DQ_ENGINE_TAG:-}" ]; then
    echo "ERROR: Missing required environment variables"
    echo "  DQ_ENGINE_REGISTRY: ${DQ_ENGINE_REGISTRY:-not set}"
    echo "  DQ_ENGINE_NAMESPACE: ${DQ_ENGINE_NAMESPACE:-not set}"
    echo "  DQ_ENGINE_IMAGE: ${DQ_ENGINE_IMAGE:-not set}"
    echo "  DQ_ENGINE_TAG: ${DQ_ENGINE_TAG:-not set}"
    exit 1
fi

IMAGE_NAME="${DQ_ENGINE_REGISTRY}${DQ_ENGINE_NAMESPACE}${DQ_ENGINE_IMAGE}:${DQ_ENGINE_TAG}"
LATEST_NAME="${DQ_ENGINE_REGISTRY}${DQ_ENGINE_NAMESPACE}${DQ_ENGINE_IMAGE}:latest"

echo "========================================"
echo "Building dq-engine Docker image"
echo "========================================"
echo "Image: $IMAGE_NAME"
echo "Latest: $LATEST_NAME"
echo "Build directory: $DOCKER_DIR"
echo "Cache: $([ -z "$NO_CACHE" ] && echo "enabled" || echo "disabled")"
echo "Push to registry: $([ "$NO_PUSH" = false ] && echo "yes" || echo "no")"
echo "========================================"
echo ""

echo "Starting build..."
if docker build $NO_CACHE \
    --build-arg PIP_INDEX_URL="${PIP_INDEX_URL:-}" \
    --build-arg MAVEN_REPOSITORIES="${MAVEN_REPOSITORIES:-}" \
    -f "$DOCKER_DIR/dq-engine/Dockerfile.engine" \
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
