#!/usr/bin/env bash
# Purpose: Background monitoring helper for the common startup flow.
#
# What it does:
# - Tails the startup log and prints container state changes (first appearance or
#   status transition), suppressing repeated identical lines.
# - Fails fast when a container enters an error state (docker compose "Error ..." or
#   "dependency ... failed to start").
# - Warns when a container is stuck in a non-terminal state for too long.
# - Enforces a global startup timeout and aborts if exceeded.
# - Watches docker compose container state and aborts if a container exits non-zero.
# - Cleans up automatically when the startup process exits.
#
# Version: 2.4
# Last modified: 2026-07-12
# Changelog:
# - 2.4: Added fail-fast on Error states and "dependency failed to start" lines.
# - 2.3: Added global timeout (STARTUP_MONITOR_TIMEOUT_SECONDS) and per-container
#   stuck detection (STARTUP_MONITOR_STUCK_THRESHOLD_SECONDS).

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

  # Associative array: container_name -> last_status
  declare -A container_state
  # Associative array: container_name -> last_change_epoch
  declare -A container_last_change
  # Associative array: container_name -> stuck warning already printed (1=yes)
  declare -A container_stuck_warned

  # Global timeout (env: STARTUP_MONITOR_TIMEOUT_SECONDS, default: 1800 = 30 min)
  local global_timeout="${STARTUP_MONITOR_TIMEOUT_SECONDS:-1800}"
  # Per-container stuck threshold (env: STARTUP_MONITOR_STUCK_THRESHOLD_SECONDS, default: 300 = 5 min)
  local stuck_threshold="${STARTUP_MONITOR_STUCK_THRESHOLD_SECONDS:-300}"

  set +e +o pipefail

  _startup_monitor_print_change() {
    local name="$1"
    local status="$2"
    local prev="${container_state[$name]:-}"
    if [ -z "$prev" ] || [ "$prev" != "$status" ]; then
      container_state["$name"]="$status"
      container_last_change["$name"]=$(date +%s)
      # Reset stuck flag on state change
      container_stuck_warned["$name"]=""
      printf ' Container %-55s %s\n' "$name" "$status"
    fi
  }

  # Terminal states that don't count as stuck
  _is_terminal_state() {
    local status="$1"
    case "$status" in
      Exited|Healthy|Exited*|Completed|Completed*) return 0 ;;
      *) return 1 ;;
    esac
  }

  # Error states that should trigger immediate abort (fail-fast)
  _is_error_state() {
    local status="$1"
    case "$status" in
      Error*|error*) return 0 ;;
      *) return 1 ;;
    esac
  }

  local start_epoch
  start_epoch=$(date +%s)

  while kill -0 "$target_pid" 2>/dev/null; do
    # Global timeout check
    local now_epoch
    now_epoch=$(date +%s)
    local elapsed=$(( now_epoch - start_epoch ))
    if [ "$elapsed" -ge "$global_timeout" ]; then
      echo "" >&2
      echo "startup_monitor: global timeout reached (${elapsed}s / ${global_timeout}s). Aborting startup." >&2
      echo "startup_monitor: containers that may still be pending:" >&2
      for cname in "${!container_state[@]}"; do
        local cstatus="${container_state[$cname]}"
        if ! _is_terminal_state "$cstatus"; then
          echo "  $cname: $cstatus" >&2
        fi
      done
      kill "$target_pid" 2>/dev/null || true
      break
    fi

    if [ -f "$log_file" ]; then
      local current_log_size
      current_log_size=$(stat -f%z "$log_file" 2>/dev/null || stat -c%s "$log_file" 2>/dev/null || echo 0)
      if [ "$current_log_size" -gt "$last_log_size" ] && [ "$current_log_size" -gt 0 ]; then
        local new_lines
        new_lines=$(tail -c +$((last_log_size + 1)) "$log_file" | \
          sed 's/\x1b\[[0-9;]*m//g' || true)
        if [ -n "$new_lines" ]; then
          local error_hit=""
          # Parse "Container <name> <status>" lines and deduplicate by state change
          while IFS= read -r line; do
            if [[ "$line" =~ ^\ *Container\ ([^\ ]+)\ (.+)$ ]]; then
              _startup_monitor_print_change "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
              # Fail-fast: abort on any Error state
              if _is_error_state "${BASH_REMATCH[2]}"; then
                error_hit="${BASH_REMATCH[1]}: ${BASH_REMATCH[2]}"
              fi
            else
              # Non-container lines (timestamps, errors, etc.): pass through
              printf '%s\n' "$line"
              # Fail-fast: abort on docker compose dependency errors
              if [[ "$line" =~ dependency\ failed\ to\ start ]]; then
                error_hit="dependency failure: $line"
              fi
            fi
          done <<< "$new_lines"

          if [ -n "$error_hit" ]; then
            echo "" >&2
            echo "startup_monitor: container error detected — aborting startup" >&2
            echo "startup_monitor: $error_hit" >&2
            kill "$target_pid" 2>/dev/null || true
            break
          fi
        fi
        last_log_size=$current_log_size
      fi
    fi

    # Stuck container check
    for cname in "${!container_last_change[@]}"; do
      local cstatus="${container_state[$cname]}"
      # Skip terminal states
      if _is_terminal_state "$cstatus"; then
        continue
      fi
      # Skip containers that already got a warning
      if [ "${container_stuck_warned[$cname]:-}" = "1" ]; then
        continue
      fi
      local change_epoch="${container_last_change[$cname]:-}"
      if [ -z "$change_epoch" ]; then
        continue
      fi
      local container_elapsed=$(( now_epoch - change_epoch ))
      if [ "$container_elapsed" -ge "$stuck_threshold" ]; then
        container_stuck_warned["$cname"]="1"
        printf '\nstartup_monitor: ⚠ Container "%s" has been stuck in "%s" for %ds (threshold: %ds)\n' \
          "$cname" "$cstatus" "$container_elapsed" "$stuck_threshold"
      fi
    done

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