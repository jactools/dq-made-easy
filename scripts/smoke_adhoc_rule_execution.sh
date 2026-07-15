#!/usr/bin/env bash
set -euo pipefail

# Purpose: Smoke-test ad-hoc rule execution with reusable generated test data.
#
# What it does:
# - Gets a JWT from Keycloak via client_credentials for the seeded engine client.
# - Discovers a seeded data_object_version_id via Kong.
# - Probes for a DOV that has GX suites (without enqueuing runs).
# - Creates/reuses a test-data materialization and waits for completion.
# - Enqueues an ad-hoc GX run using source overrides and waits for completion.
# - Asserts the GX worker reported `storage_uri` == the override output_uri.
#
# Version: 1.1
# Last modified: 2026-06-30

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

exec "$WRAPPER_DIR/validation/smoke_adhoc_rule_execution.sh" "$@"