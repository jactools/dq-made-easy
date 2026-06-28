#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-dq-engine-spark-test}"
FORCE_REBUILD="${SPARK_TEST_FORCE_REBUILD:-0}"
TEST_TARGET="${1:-tests/test_spark_expectations_adapter.py}"
shift || true
EXTRA_PYTEST_ARGS=("$@")

cd "$REPO_ROOT"

case "$TEST_TARGET" in
  /*)
    CONTAINER_TEST_TARGET="$TEST_TARGET"
    ;;
  *)
    CONTAINER_TEST_TARGET="/workspace/${TEST_TARGET#./}"
    ;;
esac

export CONTAINER_TEST_TARGET
export TEST_TARGET="$CONTAINER_TEST_TARGET"

NETWORK_NAME="${NETWORK_NAME:-$(docker inspect -f '{{range $name, $conf := .NetworkSettings.Networks}}{{$name}}{{println}}{{end}}' dq-made-easy-aistor 2>/dev/null | head -1)}"
NETWORK_ARGS=()
if [[ -n "$NETWORK_NAME" ]]; then
  NETWORK_ARGS+=(--network "$NETWORK_NAME")
fi

ENV_ARGS=()
for env_name in \
  DQ_S3_ENDPOINT \
  DQ_S3_ACCESS_KEY \
  DQ_S3_SECRET_KEY \
  DQ_S3_REGION \
  DQ_S3_PATH_STYLE_ACCESS \
  DQ_S3_SSL_ENABLED \
  AWS_ENDPOINT_URL \
  AWS_ACCESS_KEY_ID \
  AWS_SECRET_ACCESS_KEY \
  AWS_REGION \
  AWS_DEFAULT_REGION \
  SPARK_EXPECTATIONS_VALIDATION_INPUT_URI \
  DQ_SPARK_MASTER
  do
    if [[ -n "${!env_name:-}" ]]; then
      ENV_ARGS+=("-e" "$env_name=${!env_name}")
    fi
done

if [[ "$FORCE_REBUILD" == "1" ]]; then
  docker build -f "$REPO_ROOT/dq-engine/Dockerfile.engine" -t "$IMAGE_NAME" "$REPO_ROOT"
else
  if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    docker build -f "$REPO_ROOT/dq-engine/Dockerfile.engine" -t "$IMAGE_NAME" "$REPO_ROOT"
  fi
fi

docker run --rm \
  "${NETWORK_ARGS[@]}" \
  "${ENV_ARGS[@]}" \
  -e TEST_TARGET="$CONTAINER_TEST_TARGET" \
  -v "$REPO_ROOT":/workspace \
  -w /workspace \
  "$IMAGE_NAME" \
  sh -lc '/opt/venv/bin/pip install pytest httpx >/tmp/pip.log 2>&1 && target=$1 && shift && /opt/venv/bin/python -m pytest "$target" -q "$@"' _ "$CONTAINER_TEST_TARGET" "${EXTRA_PYTEST_ARGS[@]}"