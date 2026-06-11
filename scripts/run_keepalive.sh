#!/usr/bin/env bash
set -uo pipefail

# Purpose: Run a command in a terminal without leaving the session dead on shell errors.
# What it does:
# - Executes the command passed on the command line.
# - Captures and prints the child command exit status.
# - Writes the latest status to tmp/last_terminal_command_status by default.
# - Returns to the existing terminal prompt after the child command finishes.
# - Propagates the child status only when --propagate or DQ_KEEPALIVE_PROPAGATE_STATUS=1 is set.
# Version: 1.1
# Last modified: 2026-05-07
# Changelog:
# - 1.1 (2026-05-07): Captures child status without exiting non-zero by default, so command-launched terminals stay alive.

if [[ $# -eq 0 ]]; then
  printf 'Usage: %s [--propagate] [--status-file PATH] <command> [args...]\n' "$0" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
status_file="${DQ_KEEPALIVE_STATUS_FILE:-${ROOT_DIR}/tmp/last_terminal_command_status}"
propagate_status="${DQ_KEEPALIVE_PROPAGATE_STATUS:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --propagate)
      propagate_status="1"
      shift
      ;;
    --status-file)
      if [[ -z "${2:-}" ]]; then
        printf 'ERROR: --status-file requires a path\n' >&2
        exit 2
      fi
      status_file="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -eq 0 ]]; then
  printf 'Usage: %s [--propagate] [--status-file PATH] <command> [args...]\n' "$0" >&2
  exit 2
fi

command_display="$(printf '%q ' "$@")"

record_status() {
  local exit_code="$1"
  local finished_at

  finished_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  mkdir -p "$(dirname "$status_file")" || {
    printf 'ERROR: unable to create status directory for %s\n' "$status_file" >&2
    return 1
  }

  {
    printf 'exit_code=%s\n' "$exit_code"
    printf 'finished_at=%s\n' "$finished_at"
    printf 'command=%s\n' "$command_display"
  } >"$status_file" || {
    printf 'ERROR: unable to write status file %s\n' "$status_file" >&2
    return 1
  }
}

printf 'RUNNING: %s\n' "$command_display"

set +e
"$@"
command_exit_code=$?
set -e

if ! record_status "$command_exit_code"; then
  if [[ "$propagate_status" == "1" ]]; then
    exit 1
  fi
  printf 'Terminal kept alive; status capture failed.\n' >&2
  exit 0
fi

if [[ "$command_exit_code" -ne 0 ]]; then
  printf 'ERROR: command failed with exit code %s: %s\n' "$command_exit_code" "$command_display" >&2
  printf 'Captured exit status in %s\n' "$status_file" >&2
else
  printf 'OK: command completed successfully. Captured exit status in %s\n' "$status_file"
fi

if [[ "$propagate_status" == "1" ]]; then
  exit "$command_exit_code"
fi

exit 0
