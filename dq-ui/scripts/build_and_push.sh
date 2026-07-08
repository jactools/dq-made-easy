#!/usr/bin/env bash
###
# Name: build_and_push.sh
# Description: Build and push dq-frontend image to Docker Hub
# Usage: ./build_and_push.sh [--no-cache] [--no-push]
###

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$SERVICE_DIR"
DOCKER_DIR="$SERVICE_DIR"

source "$SERVICE_DIR/../scripts/supporting/root_env_file.sh"
init_root_env_file "$SERVICE_DIR/.."

# Preserve the exported canonical frontend tag if a parent script already set it.
SAVED_DQ_FRONTEND_TAG="${DQ_FRONTEND_TAG:-}"

if ! source_selected_root_env_file; then
    exit 1
fi

source "$SERVICE_DIR/../scripts/supporting/setup_env.sh"

# Restore the canonical tag if it was previously set by a parent script.
if [ -n "$SAVED_DQ_FRONTEND_TAG" ]; then
    DQ_FRONTEND_TAG="$SAVED_DQ_FRONTEND_TAG"
fi

echo "Preparing frontend assets locally before Docker packaging..."
bash "$SERVICE_DIR/../scripts/local_build_frontend.sh" --no-docker-build

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

Build and push the dq-frontend Docker image.

Options:
    --no-cache    Build without using Docker cache
    --no-push     Build only, do not push to Docker Hub
    -h, --help    Show this help message

Environment variables (from the selected root env file):
    DQ_FRONTEND_REGISTRY      Docker registry (current: ${DQ_FRONTEND_REGISTRY:-not set})
    DQ_FRONTEND_NAMESPACE     Docker namespace (current: ${DQ_FRONTEND_NAMESPACE:-not set})
    DQ_FRONTEND_IMAGE         Image name (current: ${DQ_FRONTEND_IMAGE:-not set})
    DQ_FRONTEND_TAG           Image tag (current: ${DQ_FRONTEND_TAG:-not set})

Full image name: ${DQ_FRONTEND_REGISTRY:-}${DQ_FRONTEND_NAMESPACE:-}${DQ_FRONTEND_IMAGE:-}:${DQ_FRONTEND_TAG:-}

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

if [ -z "${DQ_FRONTEND_REGISTRY:-}" ] || [ -z "${DQ_FRONTEND_NAMESPACE:-}" ] || [ -z "${DQ_FRONTEND_IMAGE:-}" ] || [ -z "${DQ_FRONTEND_TAG:-}" ]; then
    echo "ERROR: Missing required environment variables"
    echo "  DQ_FRONTEND_REGISTRY: ${DQ_FRONTEND_REGISTRY:-not set}"
    echo "  DQ_FRONTEND_NAMESPACE: ${DQ_FRONTEND_NAMESPACE:-not set}"
    echo "  DQ_FRONTEND_IMAGE: ${DQ_FRONTEND_IMAGE:-not set}"
    echo "  DQ_FRONTEND_TAG: ${DQ_FRONTEND_TAG:-not set}"
    exit 1
fi

if [ -z "${NGINX_REGISTRY:-}" ] || [ -z "${NGINX_IMAGE:-}" ] || [ -z "${NGINX_TAG:-}" ]; then
    echo "ERROR: Missing NGINX base image environment variables required for frontend build"
    echo "  NGINX_REGISTRY: ${NGINX_REGISTRY:-not set}"
    echo "  NGINX_NAMESPACE: ${NGINX_NAMESPACE:-optional}"
    echo "  NGINX_IMAGE: ${NGINX_IMAGE:-not set}"
    echo "  NGINX_TAG: ${NGINX_TAG:-not set}"
    exit 1
fi

IMAGE_NAME="${DQ_FRONTEND_REGISTRY}${DQ_FRONTEND_NAMESPACE}${DQ_FRONTEND_IMAGE}:${DQ_FRONTEND_TAG}"
LATEST_NAME="${DQ_FRONTEND_REGISTRY}${DQ_FRONTEND_NAMESPACE}${DQ_FRONTEND_IMAGE}:latest"

echo "========================================"
echo "Building dq-frontend Docker image"
echo "========================================"
echo "Image: $IMAGE_NAME"
echo "Latest: $LATEST_NAME"
echo "Build directory: $DOCKER_DIR"
echo "Cache: $([ -z "$NO_CACHE" ] && echo "enabled" || echo "disabled")"
echo "Push to registry: $([ "$NO_PUSH" = false ] && echo "yes" || echo "no")"
echo "========================================"
echo ""
echo "NOTE: This Dockerfile expects a prebuilt dist/ directory."
echo ""

echo "Starting build..."

try_build() {
    local nginx_registry="$1"
    local nginx_namespace="$2"
    local nginx_image="$3"
    local nginx_tag="$4"

    DOCKER_BUILDKIT=1 docker build $NO_CACHE \
        --build-arg NGINX_REGISTRY="$nginx_registry" \
        --build-arg NGINX_NAMESPACE="$nginx_namespace" \
        --build-arg NGINX_IMAGE="$nginx_image" \
        --build-arg NGINX_TAG="$nginx_tag" \
        -f "$DOCKER_DIR/Dockerfile.frontend" \
        -t "$IMAGE_NAME" \
        -t "$LATEST_NAME" \
        "$DOCKER_DIR"
}

if try_build "${NGINX_REGISTRY:-}" "${NGINX_NAMESPACE:-}" "${NGINX_IMAGE:-}" "${NGINX_TAG:-}"; then
    echo ""
    echo "✓ Build successful!"
    echo ""
else
    base_ref="${NGINX_REGISTRY:-}${NGINX_NAMESPACE:-}${NGINX_IMAGE:-nginx}:${NGINX_TAG:-}"
    echo "" >&2
    echo "✗ Build failed using nginx base image: $base_ref" >&2

    auth_probe_output="$(docker manifest inspect "$base_ref" 2>&1 || true)"
    if echo "$auth_probe_output" | grep -qiE 'no basic auth credentials|unauthorized|authentication required'; then
        echo "" >&2
        echo "Docker is not authenticated to the base image registry." >&2
        echo "Fix (work/Nexus):" >&2
        echo "  printf '%s' \"\$NEXUSCLOUD_PASSWORD\" | docker login ${NGINX_REGISTRY%/} -u \"\$NEXUSCLOUD_USERNAME\" --password-stdin" >&2
    fi

    echo "" >&2
    echo "No docker.io fallback is performed by this script." >&2
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
