# Purpose: Implement the shared logging primitives used by shell scripts.
#
# What it does:
# - Defines log levels and a UTC timestamped log format.
# - Provides helper functions (debug/info/warning/error/success).
# - Supports an optional script tag for grouped log lines.
#
# Version: 1.0
# Last modified: 2026-05-08

DEBUG=0
INFO=1
WARNING=2
ERROR=3
SUCCESS=4

: "${LOG_LEVEL:=1}"

log_message() {
    local level="$1"
    shift

    local script_name
    script_name="$(basename "$0")"

    local subscript_name=""
    local message=""

    if [ "$#" -ge 2 ]; then
        if [ "$1" != "$script_name" ]; then
            subscript_name=" [$1]"
        fi
        shift
    fi

    message="$*"

    local timestamp
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    if [ "$level" = ERROR ]; then
        printf '[%s] [%s] [%s]%s %s\n' "$timestamp" "$level" "$script_name" "$subscript_name" "$message" >&2
    else
        printf '[%s] [%s] [%s]%s %s\n' "$timestamp" "$level" "$script_name" "$subscript_name" "$message"
    fi
}

set_log_level() {
    case "$1" in
        0|DEBUG) LOG_LEVEL=0 ;;
        1|INFO) LOG_LEVEL=1 ;;
        2|WARNING) LOG_LEVEL=2 ;;
        3|ERROR) LOG_LEVEL=3 ;;
        4|SUCCESS) LOG_LEVEL=4 ;;
        *) printf 'Invalid log level: %s\n' "$1" >&2; return 1 ;;
    esac

    export LOG_LEVEL
}

debug()   { if [ "$LOG_LEVEL" -le 0 ]; then log_message DEBUG "$@"; fi }
info()    { if [ "$LOG_LEVEL" -le 1 ]; then log_message INFO "$@"; fi }
warning() { if [ "$LOG_LEVEL" -le 2 ]; then log_message WARNING "$@"; fi }
error()   { if [ "$LOG_LEVEL" -le 3 ]; then log_message ERROR "$@"; fi }
success() { if [ "$LOG_LEVEL" -le 4 ]; then log_message SUCCESS "$@"; fi }

# require_cmd: check that an external command is available on PATH.
# Emits a clear error with installation hint and exits 1 if missing.
require_cmd() {
  local cmd="$1"
  local hint="${2:-}"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "require_cmd" "Missing required command: $cmd"
    if [ -n "$hint" ]; then
      info "require_cmd" "Installation hint: $hint"
    fi
    exit 1
  fi
}
