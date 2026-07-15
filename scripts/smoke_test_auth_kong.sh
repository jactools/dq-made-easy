#!/usr/bin/env bash
set -euo pipefail

# Version: 1.1
# Last modified: 2026-07-01

WRAPPER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$WRAPPER_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$WRAPPER_DIR/supporting/root_env_file.sh"

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
	exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

validate_selected_root_env_file "$ROOT_DIR" full

if ! source_selected_root_env_file; then
	exit 1
fi

exec "$WRAPPER_DIR/validation/smoke_test_auth_kong.sh" "$@"