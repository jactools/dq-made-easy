#!/usr/bin/env bash
set -euo pipefail

/docker-entrypoint.sh kong docker-start &
KONG_PID=$!

# Best effort bootstrap. Do not crash Kong process if bootstrap fails once.
if ! /opt/dq-kong/scripts/bootstrap_kong.sh; then
  echo "[kong-bootstrap] warning: bootstrap failed; Kong will continue running"
fi

wait "$KONG_PID"
