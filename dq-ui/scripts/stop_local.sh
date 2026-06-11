#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"


if [ -f .pids/vite.pid ]; then
  PID=$(cat .pids/vite.pid)
  echo "Stopping Vite (pid=$PID)"
  kill "$PID" || true
  rm -f .pids/vite.pid
else
  echo "No Vite pid found"
fi

# Do not stop Docker containers here.
# The repository stack includes a dockerized frontend that binds port 5173; it
# may be intentionally running (e.g., when using containerized UI instead of Vite).
# If you need Vite on a different port, set VITE_PORT in the environment.

# Best-effort cleanup of stale Vite listeners (processes only).
if command -v lsof >/dev/null 2>&1; then
  STALE_PIDS=$(for p in {5173..5205}; do
    lsof -iTCP:"$p" -sTCP:LISTEN -t 2>/dev/null || true
  done | sort -u)
  for pid in $STALE_PIDS; do
    cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
    if echo "$cmd" | grep -qi "vite"; then
      echo "Stopping stale Vite listener (pid=$pid)"
      kill "$pid" 2>/dev/null || true
    fi
  done
fi

echo "Stopped local services."
