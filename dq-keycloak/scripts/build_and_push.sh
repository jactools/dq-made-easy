#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$ROOT_DIR"

source "$ROOT_DIR/../scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR/.."

SAVED_TAG="${DQ_KEYCLOAK_TAG:-}"

if ! source_selected_root_env_file; then
  exit 1
fi

if [ -n "$SAVED_TAG" ]; then
  DQ_KEYCLOAK_TAG="$SAVED_TAG"
fi

DQ_KEYCLOAK_REGISTRY="${DQ_KEYCLOAK_REGISTRY:-docker.io/}"
DQ_KEYCLOAK_NAMESPACE="${DQ_KEYCLOAK_NAMESPACE:-jacbeekers/}"
DQ_KEYCLOAK_IMAGE="${DQ_KEYCLOAK_IMAGE:-dq-made-easy-keycloak}"
DQ_KEYCLOAK_TAG="${DQ_KEYCLOAK_TAG:-latest}"

NO_CACHE=""
NO_PUSH=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-cache) NO_CACHE="--no-cache"; shift ;;
    --no-push) NO_PUSH=true; shift ;;
    -h|--help)
      echo "Usage: $(basename "$0") [--no-cache] [--no-push]"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

IMAGE_NAME="${DQ_KEYCLOAK_REGISTRY}${DQ_KEYCLOAK_NAMESPACE}${DQ_KEYCLOAK_IMAGE}:${DQ_KEYCLOAK_TAG}"
LATEST_NAME="${DQ_KEYCLOAK_REGISTRY}${DQ_KEYCLOAK_NAMESPACE}${DQ_KEYCLOAK_IMAGE}:latest"

echo "Building $IMAGE_NAME"
docker build $NO_CACHE -f "$DOCKER_DIR/Dockerfile.keycloak" -t "$IMAGE_NAME" -t "$LATEST_NAME" "$DOCKER_DIR"

if [ "$NO_PUSH" = false ]; then
  docker push "$IMAGE_NAME"
  docker push "$LATEST_NAME"
fi

echo "Done: $IMAGE_NAME"
