#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate that a DQ run plan can be scheduled, executed to completion,
#          and that the monitor schedule persists across multiple runs.
#
# What it does:
# - Loads the selected repo env file for the canonical local validation contract.
# - Optionally saves a monitor schedule for a target scope (data_asset or source_dataset).
# - Invokes (replays) the target run plan N times (default 3).
# - Polls each run to a terminal state (succeeded/failed/cancelled).
# - After all runs complete, reads back the monitor schedule and asserts it was not lost.
# - Reports a summary table showing per-run status.
#
# validate: groups=api,regression
# Version: 1.0.0
# Last modified: 2026-05-23

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
HELPER="${SCRIPT_DIR}/validate_monitor_schedule_run_plan.py"
MY_NAME="validate_monitor_schedule_run_plan.sh"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

print_usage() {
  cat <<'EOF'
Usage: scripts/validate_monitor_schedule_run_plan.sh [--run-plan-id ID]
       [--run-count N] [--scope-kind KIND] [--scope-id ID] [--workspace-id ID]

Options:
  --run-plan-id   ID    DQ run plan id to replay (or set DQ_VALIDATION_RUN_PLAN_ID)
  --run-count     N     Number of replay runs (default: 3)
  --scope-kind    KIND  Scope kind for monitor schedule: data_asset|source_dataset
                        (default: data_asset)
  --scope-id      ID    Scope id for monitor schedule (optional; derived from run
                        plan when omitted)
  --workspace-id  ID    Workspace id for monitor schedule (optional; derived from
                        run plan when omitted)
  -h, --help            Show this help
EOF
}

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 1
fi

set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      print_usage
      exit 0
      ;;
  esac
done

validate_selected_root_env_file "$ROOT_DIR" full

if ! source_selected_root_env_file; then
  exit 1
fi

dq_source_seeded_user_credentials --env-file "$ROOT_ENV_FILE" --quiet

RUN_PLAN_ID="${DQ_VALIDATION_RUN_PLAN_ID:-}"
RUN_COUNT=""
SCOPE_KIND=""
SCOPE_ID=""
WORKSPACE_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-plan-id)
      if [[ $# -lt 2 ]]; then
        error "$MY_NAME" "--run-plan-id requires a value"
        exit 2
      fi
      RUN_PLAN_ID="$2"
      shift 2
      ;;
    --run-count)
      if [[ $# -lt 2 ]]; then
        error "$MY_NAME" "--run-count requires a value"
        exit 2
      fi
      RUN_COUNT="$2"
      shift 2
      ;;
    --scope-kind)
      if [[ $# -lt 2 ]]; then
        error "$MY_NAME" "--scope-kind requires a value"
        exit 2
      fi
      SCOPE_KIND="$2"
      shift 2
      ;;
    --scope-id)
      if [[ $# -lt 2 ]]; then
        error "$MY_NAME" "--scope-id requires a value"
        exit 2
      fi
      SCOPE_ID="$2"
      shift 2
      ;;
    --workspace-id)
      if [[ $# -lt 2 ]]; then
        error "$MY_NAME" "--workspace-id requires a value"
        exit 2
      fi
      WORKSPACE_ID="$2"
      shift 2
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      error "$MY_NAME" "Unknown argument: $1"
      print_usage
      exit 2
      ;;
  esac
done

if [[ -z "$RUN_PLAN_ID" ]]; then
  error "$MY_NAME" "--run-plan-id is required when DQ_VALIDATION_RUN_PLAN_ID is not set"
  print_usage
  exit 2
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  error "$MY_NAME" "Missing required Python interpreter: $PYTHON_BIN"
  exit 2
fi

if [[ ! -f "$HELPER" ]]; then
  error "$MY_NAME" "Missing required helper: $HELPER"
  exit 2
fi

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [[ -f "$KONG_CA_CERT" && -z "${CURL_CA_BUNDLE:-}" ]]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi
if [[ -f "$KONG_CA_CERT" && -z "${REQUESTS_CA_BUNDLE:-}" ]]; then
  export REQUESTS_CA_BUNDLE="$KONG_CA_CERT"
fi

export DQ_VALIDATION_RUN_PLAN_ID="$RUN_PLAN_ID"
if [[ -n "$RUN_COUNT" ]]; then
  export DQ_VALIDATION_RUN_COUNT="$RUN_COUNT"
fi
if [[ -n "$SCOPE_KIND" ]]; then
  export DQ_VALIDATION_SCOPE_KIND="$SCOPE_KIND"
fi
if [[ -n "$SCOPE_ID" ]]; then
  export DQ_VALIDATION_SCOPE_ID="$SCOPE_ID"
fi
if [[ -n "$WORKSPACE_ID" ]]; then
  export DQ_VALIDATION_WORKSPACE_ID="$WORKSPACE_ID"
fi

exec "$PYTHON_BIN" "$HELPER"
