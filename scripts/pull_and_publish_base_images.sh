#!/usr/bin/env bash
set -euo pipefail

# Purpose: Pull base images from Docker Hub and publish them to our local docker-registry.
# What it does:
# - Sources the selected .env.<env>.local file
# - Pulls base images from Docker Hub
# - Tags them for the local registry with namespace
# - Pushes them to the local registry
# Version: 1.0
# Last modified: 2026-08-08

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR"

usage() {
  cat <<'USAGE'
Usage: scripts/pull_and_publish_base_images.sh <dev|test|prod>

Pulls base images from Docker Hub and publishes them to the local docker-registry.

Examples:
  scripts/pull_and_publish_base_images.sh dev
  scripts/pull_and_publish_base_images.sh test

Notes:
  - Base images are pulled from Docker Hub
  - They are tagged with the local registry URL and namespace
  - They are pushed to the local registry
USAGE
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

target_env="$1"
shift

resolve_env_file() {
  case "$1" in
    dev) echo ".env.dev.local" ;;
    test) echo ".env.test.local" ;;
    prod) echo ".env.prod.local" ;;
    *)
      echo "Unsupported environment: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
}

env_file="$ROOT_DIR/$(resolve_env_file "$target_env")"
if [[ ! -f "$env_file" ]]; then
  echo "Missing environment file: $env_file" >&2
  exit 1
fi

set -a
source "$env_file"
set +a

# Docker registry configuration
DOCKER_REGISTRY_DNS="${DOCKER_REGISTRY_DNS:-docker-registry.dev.jac.dot}"
DOCKER_REGISTRY_PORT="${DOCKER_REGISTRY_PORT:-5000}"
DOCKER_REGISTRY_URL="https://${DOCKER_REGISTRY_DNS}:10443"
NAMESPACE="${DQ_BASE_NAMESPACE:-jacbeekers/}"

# Base images to pull and publish
# Format: "source_image:tag local_name:tag"
BASE_IMAGES=(
  "python:3.13-slim dq-made-easy-python-base:latest"
  "postgres:18 dq-made-easy-postgres:latest"
  "nginx:stable-bookworm dq-made-easy-nginx:latest"
  "node:26-bookworm dq-made-easy-node:latest"
  "ubuntu:latest dq-made-easy-ubuntu:latest"
  "axllent/mailpit:latest dq-made-easy-mailpit:latest"
  "openmetadata/server:1.12.7 openmetadata/server:1.12.7"
  "debian:bookworm-slim otel-javaagent-helper:bookworm-slim"
  "ghcr.io/zammad/zammad:7.0.1-0000 zammad/zammad:7.0.1-0000"
)

# Pull and publish each base image
for image_pair in "${BASE_IMAGES[@]}"; do
  read -r source_image local_image <<< "$image_pair"
  
  echo "=== Pulling $source_image ==="
  docker pull "$source_image" || {
    echo "Failed to pull $source_image" >&2
    exit 1
  }
  
  # Tag for local registry with namespace
  tagged_image="${DOCKER_REGISTRY_DNS}:10443/${NAMESPACE}${local_image}"
  echo "=== Tagging as $tagged_image ==="
  docker tag "$source_image" "$tagged_image"
  
  # Push to local registry
  echo "=== Pushing to local registry ==="
  docker push "$tagged_image" || {
    echo "Failed to push $tagged_image" >&2
    exit 1
  }
  
  echo "=== Successfully published ${NAMESPACE}${local_image} ==="
  echo ""
done

echo "=== All base images published to local registry ==="
echo "Registry URL: $DOCKER_REGISTRY_URL"
echo "Namespace: $NAMESPACE"
