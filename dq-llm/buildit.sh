#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="spacy-llm-api"
CACHE_VOLUME="dq-llm-hf-cache"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

: "${REGISTRY:?REGISTRY is required to build the LLM image against the shared Python base}"

if [ -f "$REPO_ROOT/.env.dev.local" ]; then
	set -a
	source "$REPO_ROOT/.env.dev.local"
	set +a
fi

docker build --platform linux/arm64 \
	--build-arg PYTHON_REGISTRY="${REGISTRY:-}" \
	--build-arg PYTHON_NAMESPACE= \
	--build-arg PYTHON_IMAGE=dq-made-easy-python-base \
	--build-arg PYTHON_TAG=latest \
	-t "$IMAGE_NAME" -f Dockerfile.llm .
docker volume create "$CACHE_VOLUME" >/dev/null

docker run --rm --platform linux/arm64 \
	-e HF_HOME=/cache/huggingface \
	-v "$CACHE_VOLUME:/cache/huggingface" \
	"$IMAGE_NAME" \
	python warm_cache.py
