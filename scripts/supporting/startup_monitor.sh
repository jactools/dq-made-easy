#!/usr/bin/env bash
# Purpose: Background monitoring helper for the common startup flow.
#
# What it does:
# - Tails the startup log and prints new output (minus ANSI codes).
# - Watches docker compose container state and aborts if a container exits non-zero.
# - Cleans up automatically when the startup process exits.
#
# Version: 2.1
# Last modified: 2026-07-12

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

startup_monitor_pid=0

startup_monitor_cleanup() {
  if [ "${startup_monitor_pid:-0}" -ne 0 ]; then
    kill "$startup_monitor_pid" 2>/dev/null || true
    wait "$startup_monitor_pid" 2>/dev/null || true
    startup_monitor_pid=0
  fi
}

startup_monitor_detect_failed_containers() {
  local compose_output
  compose_output="$(docker compose -f "$ROOT_DIR/docker-compose.yml" --env-file "$ROOT_ENV_FILE" ps --all --format json 2>/dev/null || true)"

  if [ -z "$compose_output" ]; then
    return 0
  fi

  python3 - "$compose_output" <<'PY'
import json
import sys

raw = sys.argv[1]
if not raw.strip():
    raise SystemExit(0)

try:
    items = json.loads(raw)
except json.JSONDecodeError:
    raise SystemExit(0)

if isinstance(items, dict):
    items = [items]

for item in items:
    service = item.get("Service") or item.get("Name") or "unknown"
    exit_code = item.get("ExitCode")
    health = str(item.get("Health") or "").lower()
    status = str(item.get("Status") or "").lower()

    if exit_code is None:
        continue

    try:
        exit_code_int = int(exit_code)
    except (TypeError, ValueError):
        continue

    if exit_code_int != 0:
        print(f"startup_monitor: container '{service}' failed with exit code {exit_code_int}", file=sys.stderr)
        raise SystemExit(1)

    if health == "unhealthy" or ("unhealthy" in status and "healthy" not in status):
        print(f"startup_monitor: container '{service}' reported unhealthy status", file=sys.stderr)
        raise SystemExit(2)
PY
}

startup_monitor_run() {
  local target_pid="$1"
  local last_log_size=0
  local log_file="$ROOT_DIR/tmp/startup.log"

  set +e +o pipefail

  while kill -0 "$target_pid" 2>/dev/null; do
    if [ -f "$log_file" ]; then
      local current_log_size
      current_log_size=$(stat -f%z "$log_file" 2>/dev/null || stat -c%s "$log_file" 2>/dev/null || echo 0)
      if [ "$current_log_size" -gt "$last_log_size" ] && [ "$current_log_size" -gt 0 ]; then
        local new_lines
        new_lines=$(tail -c +$((last_log_size + 1)) "$log_file" 2>/dev/null | \
          sed 's/\x1b\[[0-9;]*m//g' || true)
        if [ -n "$new_lines" ]; then
          printf '%s\n' "$new_lines"
        fi
        last_log_size=$current_log_size
      fi
    fi

    if ! startup_monitor_detect_failed_containers; then
      echo "startup_monitor: detected a failed container; aborting startup" >&2
      kill "$target_pid" 2>/dev/null || true
      break
    fi

    sleep 1
  done

  set +e
  set -o pipefail
}

startup_monitor_start() {
  local target_pid="$1"
  startup_monitor_run "$target_pid" &
  startup_monitor_pid=$!
  trap startup_monitor_cleanup EXIT
}