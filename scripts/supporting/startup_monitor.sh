#!/usr/bin/env bash
# Purpose: Background monitoring helper for the common startup flow.
#
# What it does:
# - Launches a detached monitor for the startup process.
# - Polls docker compose status and prints grouped progress.
# - Cleans up the monitor automatically on exit.
#
# Version: 1.0
# Last modified: 2026-07-12

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"

startup_monitor_pid=0

startup_monitor_build_service_profiles() {
  python3 -c "
import yaml, os, glob
mapping = {}
for path in [os.path.join('$ROOT_DIR', 'docker-compose.yml')] + glob.glob(os.path.join('$ROOT_DIR', 'docker-compose', '*.yml')):
    try:
        with open(path) as fh:
            for doc in yaml.safe_load_all(fh):
                if not doc:
                    continue
                for svc, cfg in (doc.get('services') or {}).items():
                    profiles = cfg.get('profiles', [])
                    if isinstance(profiles, list):
                        mapping[svc] = profiles
    except Exception:
        pass
for svc, profiles in sorted(mapping.items()):
    print(f'{svc} -> {\" + \".join(profiles)}')
" 2>/dev/null
}

startup_monitor_cleanup() {
  if [ "${startup_monitor_pid:-0}" -ne 0 ]; then
    kill "$startup_monitor_pid" 2>/dev/null || true
    wait "$startup_monitor_pid" 2>/dev/null || true
    startup_monitor_pid=0
  fi
}

startup_monitor_run() {
  local target_pid="$1"
  local last_output=""
  local poll_interval=5
  local start_time
  start_time=$(date +%s)
  local service_profiles
  service_profiles="$(startup_monitor_build_service_profiles)"

  while kill -0 "$target_pid" 2>/dev/null; do
    local current_output
    current_output="$(docker compose -f "$ROOT_DIR/docker-compose.yml" --env-file "$ROOT_ENV_FILE" ps --format 'table {{.Service}}\t{{.Status}}' 2>/dev/null | tail -n +2 | sort)"

    if [ "$current_output" != "$last_output" ]; then
      last_output="$current_output"
      local now
      now=$(date +%s)
      local elapsed=$((now - start_time))
      local mins=$((elapsed / 60))
      local secs=$((elapsed % 60))

      local running=0 healthy=0 starting=0 exited=0 restarting=0 unhealthy=0
      while IFS=$'\t' read -r service status; do
        [ -z "$service" ] && continue
        case "$status" in
          *healthy) healthy=$((healthy + 1)) ;;
          *starting) starting=$((starting + 1)) ;;
          *restarting) restarting=$((restarting + 1)) ;;
          *unhealthy) unhealthy=$((unhealthy + 1)) ;;
          *exited*) exited=$((exited + 1)) ;;
          *) running=$((running + 1)) ;;
        esac
      done <<< "$current_output"

      printf '\n\033[2K\r[%s] [%02d:%02d] Startup progress:\n' "$(date -u '+%H:%M:%S')" "$mins" "$secs"
      printf '  healthy=%-3d  starting=%-3d  running=%-3d  exited=%-3d  restarting=%-3d  unhealthy=%-3d\n' \
        "$healthy" "$starting" "$running" "$exited" "$restarting" "$unhealthy"

      local prev_profile=""
      while IFS=$'\t' read -r service status; do
        [ -z "$service" ] && continue
        local profile
        profile="$(printf '%s\n' "$service_profiles" | grep "^${service} ->" | sed 's/.* -> //')"
        [ -z "$profile" ] && profile="(none)"

        if [ "$profile" != "$prev_profile" ]; then
          printf '\n  [Profile: %s]\n' "$profile"
          prev_profile="$profile"
        fi

        local color=""
        case "$status" in
          *healthy) color="\033[32m" ;;
          *starting) color="\033[33m" ;;
          *restarting) color="\033[31m" ;;
          *unhealthy) color="\033[31m" ;;
          *exited*) color="\033[36m" ;;
        esac
        local reset="\033[0m"

        printf '    %s%s %s %-60s %s%s\n' "$color" "$status" "$reset" "$service" "$color" "$reset"
      done <<< "$current_output"

      printf '\n'
    fi

    sleep "$poll_interval"
  done
}

startup_monitor_start() {
  local target_pid="$1"
  startup_monitor_run "$target_pid" &
  startup_monitor_pid=$!
  trap startup_monitor_cleanup EXIT
}