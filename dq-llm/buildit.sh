#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="spacy-llm-api"
CACHE_VOLUME="dq-llm-hf-cache"

docker build --platform linux/arm64 -t "$IMAGE_NAME" -f Dockerfile.llm .
docker volume create "$CACHE_VOLUME" >/dev/null

docker run --rm --platform linux/arm64 \
	-e HF_HOME=/cache/huggingface \
	-v "$CACHE_VOLUME:/cache/huggingface" \
	"$IMAGE_NAME" \
	python warm_cache.py
