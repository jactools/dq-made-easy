#!/usr/bin/env bash
###
# Name: build_and_push.sh
# Description: Build and push dq-base image to Docker Hub
# Usage: ./build_and_push.sh [--no-cache] [--no-push]
###

set -euo pipefail

# Navigate to the repository root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR=${SCRIPT_DIR}/..

source "$ROOT_DIR/../scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR/.."

# Preserve TAG variables that may have been exported from parent
SAVED_DQ_BASE_TAG="${DQ_BASE_TAG:-}"

# Source environment variables
if ! source_selected_root_env_file; then
    exit 1
fi

# Restore exported TAG if it was previously set
if [ -n "$SAVED_DQ_BASE_TAG" ]; then
    DQ_BASE_TAG="$SAVED_DQ_BASE_TAG"
fi

# Default values
NO_CACHE=""
NO_PUSH=false

# Parse arguments
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

Build and push the dq-base Docker image to Docker Hub.

Options:
    --no-cache    Build without using Docker cache
    --no-push     Build only, do not push to Docker Hub
    -h, --help    Show this help message

Environment variables (from the selected root env file):
    DQ_BASE_REGISTRY    Docker registry (current: ${DQ_BASE_REGISTRY:-not set})
    DQ_BASE_NAMESPACE   Docker namespace (current: ${DQ_BASE_NAMESPACE:-not set})
    DQ_BASE_IMAGE       Image name and tag (current: ${DQ_BASE_IMAGE:-not set})

Full image name: ${DQ_BASE_REGISTRY}${DQ_BASE_NAMESPACE}${DQ_BASE_IMAGE}

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

# Validate environment variables
if [ -z "${DQ_BASE_REGISTRY:-}" ] || [ -z "${DQ_BASE_NAMESPACE:-}" ] || [ -z "${DQ_BASE_IMAGE:-}" ]; then
    echo "ERROR: Missing required environment variables"
    echo "  DQ_BASE_REGISTRY: ${DQ_BASE_REGISTRY:-not set}"
    echo "  DQ_BASE_NAMESPACE: ${DQ_BASE_NAMESPACE:-not set}"
    echo "  DQ_BASE_IMAGE: ${DQ_BASE_IMAGE:-not set}"
    exit 1
fi

# Construct full image name
IMAGE_NAME="${DQ_BASE_REGISTRY}${DQ_BASE_NAMESPACE}${DQ_BASE_IMAGE}"
FULL_IMAGE_NAME="${IMAGE_NAME}:${DQ_BASE_TAG}"
LATEST_IMAGE_NAME="${IMAGE_NAME}:latest"

echo "========================================"
echo "Building dq-base Docker image"
echo "========================================"
echo "Image: $FULL_IMAGE_NAME"
echo "Latest: $LATEST_IMAGE_NAME"
echo "Build directory: $SCRIPT_DIR"
echo "Cache: $([ -z "$NO_CACHE" ] && echo "enabled" || echo "disabled")"
echo "Push to registry: $([ "$NO_PUSH" = false ] && echo "yes" || echo "no")"
echo "========================================"
echo ""

# Build the image
echo "Starting build..."

try_build() {
    local node_registry="$1"
    local node_namespace="$2"
    local node_image="$3"
    local node_tag="$4"

    docker build $NO_CACHE \
        --build-arg NODE_REGISTRY="$node_registry" \
        --build-arg NODE_NAMESPACE="$node_namespace" \
        --build-arg NODE_IMAGE="$node_image" \
        --build-arg NODE_TAG="$node_tag" \
    --build-arg APK_REPOSITORIES="${APK_REPOSITORIES:-}" \
        -f "$DOCKER_DIR/Dockerfile.base" \
        -t "$FULL_IMAGE_NAME" \
        -t "$LATEST_IMAGE_NAME" \
        "$DOCKER_DIR"
}

if try_build "${NODE_REGISTRY:-}" "${NODE_NAMESPACE:-}" "${NODE_IMAGE:-}" "${NODE_TAG:-}"; then
    echo ""
    echo "✓ Build successful!"
    echo ""
else
    base_ref="${NODE_REGISTRY:-}${NODE_NAMESPACE:-}${NODE_IMAGE:-node}:${NODE_TAG:-}"
    echo "" >&2
    echo "✗ Build failed using base image: $base_ref" >&2

    auth_probe_output="$(docker manifest inspect "$base_ref" 2>&1 || true)"
    if echo "$auth_probe_output" | grep -qiE 'no basic auth credentials|unauthorized|authentication required'; then
        echo "" >&2
        echo "Docker is not authenticated to the base image registry." >&2
        echo "Fix (work/Nexus):" >&2
        echo "  printf '%s' \"\$NEXUSCLOUD_PASSWORD\" | docker login ${NODE_REGISTRY%/} -u \"\$NEXUSCLOUD_USERNAME\" --password-stdin" >&2
    fi

    echo "" >&2
    echo "No docker.io fallback is performed by this script." >&2
    exit 1
fi

# Push to Docker Hub if requested
if [ "$NO_PUSH" = false ]; then
    echo "========================================"
    echo "Pushing to Docker Hub"
    echo "========================================"
    echo "Image: $IMAGE_NAME"
    echo ""
    
    # Check if logged in to Docker Hub
    if ! docker info | grep -q "Username"; then
        echo "WARNING: You may not be logged in to Docker Hub."
        echo "If push fails, please run: docker login docker.io"
        echo ""
    fi
    
    echo "Pushing image..."
    if docker push "$FULL_IMAGE_NAME" && docker push "$LATEST_IMAGE_NAME"; then
        echo ""
        echo "✓ Successfully pushed to Docker Hub!"
        echo "  Image: $FULL_IMAGE_NAME"
        echo "  Latest: $LATEST_IMAGE_NAME"
        echo ""
    else
        echo ""
        echo "✗ Push failed!"
        echo ""
        echo "If authentication failed, please login:"
        echo "  docker login docker.io"
        echo ""
        echo "Then run this script again (build will be cached):"
        echo "  ./build_and_push.sh"
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
