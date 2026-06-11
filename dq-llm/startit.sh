#!/usr/bin/env bash
set -euo pipefail

docker volume create dq-llm-hf-cache >/dev/null

if docker ps -a --format '{{.Names}}' | grep -Fxq 'spacy-llm-service'; then
  docker rm -f spacy-llm-service
fi

docker run --platform linux/arm64 -d \
  --name spacy-llm-service \
  --network dq-network \
  -p 8123:8000 \
  -e HF_HOME=/cache/huggingface \
  -v dq-llm-hf-cache:/cache/huggingface \
  spacy-llm-api
