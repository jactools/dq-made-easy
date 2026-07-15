#!/usr/bin/env bash

# Purpose: Keep the local machine awake while a script is running.
# What it does:
# - Uses macOS caffeinate when available to prevent display sleep.
# - Runs the wake guard in the background until the parent shell exits.

STAY_AWAKE_PID=""

usage() {
	cat <<EOF
Usage: $(basename "$0") --duration 10m [--key left|right|up|down]

Keep the screen awake for a fixed period.

Duration formats:
  90s   90 seconds
  15m   15 minutes
  2h    2 hours

Key options:
	left|right|up|down   Press an arrow key every 60 seconds while the timer runs

Examples:
	$(basename "$0") --duration 30m --key left
	$(basename "$0") --duration 2h --key right
EOF
}

duration_to_seconds() {
	local duration_spec="$1"
	local value=""
	local unit=""

	if [[ "$duration_spec" =~ ^([0-9]+)([smh]?)$ ]]; then
		value="${BASH_REMATCH[1]}"
		unit="${BASH_REMATCH[2]}"
	else
		return 1
	fi

	case "$unit" in
		""|s)
			printf '%s' "$value"
			;;
		m)
			printf '%s' "$((value * 60))"
			;;
		h)
			printf '%s' "$((value * 3600))"
			;;
		*)
			return 1
			;;
	 esac
}

press_arrow_key() {
	local key_name="$1"
	local key_code=""

	case "$key_name" in
		left)
			key_code=123
			;;
		right)
			key_code=124
			;;
		down)
			key_code=125
			;;
		up)
			key_code=126
			;;
		*)
			printf 'error: unsupported key %s\n' "$key_name" >&2
			return 1
			;;
	 esac

	if ! command -v osascript >/dev/null 2>&1; then
		printf 'warning: osascript is not available; continuing without the key press\n' >&2
		return 0
	fi

	if ! osascript -e "tell application \"System Events\" to key code $key_code" >/dev/null 2>&1; then
		printf 'warning: key press could not be sent; continuing with caffeinate only\n' >&2
	fi
}

start_stay_awake() {
	if [ -n "${STAY_AWAKE_PID:-}" ]; then
		return 0
	fi

	if ! command -v caffeinate >/dev/null 2>&1; then
		return 0
	fi

	caffeinate -d -w "$$" >/dev/null 2>&1 &
	STAY_AWAKE_PID="$!"
}

stop_stay_awake() {
	if [ -z "${STAY_AWAKE_PID:-}" ]; then
		return 0
	fi

	kill "$STAY_AWAKE_PID" >/dev/null 2>&1 || true
	wait "$STAY_AWAKE_PID" >/dev/null 2>&1 || true
	STAY_AWAKE_PID=""
}

run_stay_awake_cli() {
	local duration_spec=""
	local duration_seconds=""
	local key_name=""

	while [[ $# -gt 0 ]]; do
		case "$1" in
			-d|--duration)
				if [[ -z "${2:-}" ]]; then
					printf 'error: --duration requires a value\n' >&2
					return 1
				fi
				duration_spec="$2"
				shift 2
				;;
			--duration=*)
				duration_spec="${1#*=}"
				shift
				;;
			-k|--key)
				if [[ -z "${2:-}" ]]; then
					printf 'error: --key requires a value\n' >&2
					return 1
				fi
				key_name="$2"
				shift 2
				;;
			--key=*)
				key_name="${1#*=}"
				shift
				;;
			-h|--help)
				usage
				return 0
				;;
			*)
				printf 'error: unknown argument %s\n' "$1" >&2
				usage >&2
				return 1
				;;
		esac
	done

	if [ -z "$duration_spec" ]; then
		printf 'error: --duration is required when running stay_awake.sh directly\n' >&2
		usage >&2
		return 1
	fi

	if ! duration_seconds="$(duration_to_seconds "$duration_spec")"; then
		printf 'error: invalid duration %s\n' "$duration_spec" >&2
		usage >&2
		return 1
	fi

	if ! command -v caffeinate >/dev/null 2>&1; then
		printf 'error: caffeinate is required on macOS to keep the screen awake\n' >&2
		return 1
	fi

	if [ -n "$key_name" ]; then
		press_arrow_key "$key_name" || true
	fi

	printf 'Keeping the screen awake for %s (%s seconds)\n' "$duration_spec" "$duration_seconds"
	caffeinate -d -t "$duration_seconds" >/dev/null 2>&1 &
	local caffeinate_pid="$!"
	local elapsed_seconds=0
	local sleep_seconds=0

	while (( elapsed_seconds + 60 <= duration_seconds )); do
		sleep 60
		elapsed_seconds=$((elapsed_seconds + 60))
		if [ -n "$key_name" ]; then
			press_arrow_key "$key_name" || true
		fi
	done

	sleep_seconds=$((duration_seconds - elapsed_seconds))
	if (( sleep_seconds > 0 )); then
		sleep "$sleep_seconds"
	fi

	wait "$caffeinate_pid" >/dev/null 2>&1 || true

}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	set -euo pipefail
	run_stay_awake_cli "$@"
fi
