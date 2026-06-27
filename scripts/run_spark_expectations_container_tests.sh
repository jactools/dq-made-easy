#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-dq-engine-spark-test}"
TEST_TARGET="${1:-tests/test_spark_expectations_adapter.py}"

cd "$REPO_ROOT"

export TEST_TARGET

NETWORK_NAME="${NETWORK_NAME:-$(docker inspect -f '{{range $name, $conf := .NetworkSettings.Networks}}{{$name}}{{println}}{{end}}' dq-aistor 2>/dev/null | head -1)}"
NETWORK_ARGS=()
if [[ -n "$NETWORK_NAME" ]]; then
  NETWORK_ARGS+=(--network "$NETWORK_NAME")
fi

docker build -f "$REPO_ROOT/dq-engine/Dockerfile.engine" -t "$IMAGE_NAME" "$REPO_ROOT"
docker run --rm \
  "${NETWORK_ARGS[@]}" \
  -e TEST_TARGET="$TEST_TARGET" \
  -v "$REPO_ROOT":/workspace \
  -w /workspace/dq-engine \
  "$IMAGE_NAME" \
  sh -lc '/opt/venv/bin/pip install pytest httpx >/tmp/pip.log 2>&1 && /opt/venv/bin/python -m pytest "$TEST_TARGET" -q'