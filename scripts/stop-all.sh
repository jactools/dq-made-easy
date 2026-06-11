#!/usr/bin/env bash
set -euo pipefail


# Purpose: Stop the local frontend and the docker compose stack.
#
# What it does:
# - Stops the local Vite frontend process (if running).
# - Brings down the stack via stop_stack.sh.
#
# Version: 1.2
# Last modified: 2026-04-29
# Changelog:
# - 1.1 (2026-04-27): Propagated env-file selection to stop_stack.sh so teardown uses the same deployment env.
# - 1.2 (2026-04-29): Switched teardown env selection to the canonical dev/test/prod contract.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="stop-all.sh"
info "$my_name" "pwd: $PWD"

source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR"

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
	exit 1
fi

set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"

while [[ "$#" -gt 0 ]]; do
	case "$1" in
		-h|--help)
			printf '%s\n' "Usage: $(basename "$0") [OPTIONS]"
			printf '%s\n' ""
			printf '%s\n' "Canonical env options:"
			printf '%s\n' "  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local"
			printf '%s\n' "  --env-file PATH          Use an explicit env file for CI, /etc, or diagnostics"
			printf '%s\n' ""
			printf '%s\n' "Other options:"
			printf '%s\n' "  --remove-volumes, -v     Remove compose volumes as part of teardown"
			printf '%s\n' "  -h, --help"
			exit 0
			;;
		--remove-volumes|-v)
			break
			;;
		*)
			break
			;;
	esac
done

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
	error "$my_name" "Env file not found: $ROOT_ENV_FILE"
	exit 1
fi

export ROOT_ENV_FILE

info "$my_name" "Environment selection: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE") -> $ROOT_ENV_FILE"

set -a
source "$ROOT_ENV_FILE"
set +a

source "$ROOT_DIR/scripts/supporting/setup_env.sh"

info "$my_name" "Stopping local frontend (if running)..."
dq-ui/scripts/stop_local.sh
./scripts/stop_stack.sh --env-file "$ROOT_ENV_FILE" "$@"
