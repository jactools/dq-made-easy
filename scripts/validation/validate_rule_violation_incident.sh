#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate that data-quality threshold breaches in a DQ run are surfaced
#          as a functional_violation incident with an optional Zammad ticket.
#
# What it does:
# - Loads the selected repo env file for the canonical local validation contract.
# - Looks up a completed GX execution run (by --run-id) or replays a given run plan
#   and waits for a terminal state.
# - Checks whether the run's violation_count exceeds --violation-threshold (default 0).
# - If violations are present, posts a functional_violation incident to
#   POST /rulebuilder/v1/incidents with create_itsm_ticket=true so Zammad is notified.
# - Asserts the API response contains a valid incident ID.
# - Exits 0 with an informational note if violation_count <= threshold (no ticket needed).
# - Prints a summary with the incident ID and Zammad ticket reference.
#
# validate: groups=api,regression
# Version: 1.0.1
# Last modified: 2026-05-23

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
HELPER="${SCRIPT_DIR}/validate_rule_violation_incident.py"
MY_NAME="validate_rule_violation_incident.sh"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

print_usage() {
  cat <<'EOF'
Usage: scripts/validate_rule_violation_incident.sh [--run-id ID] [--run-plan-id ID]
       [--violation-threshold N] [--workspace-id ID] [--scope-kind KIND]
       [--scope-id ID] [--no-itsm]

Options:
  --run-id              ID  GX execution run ID to inspect for violations.
  --run-plan-id         ID  DQ run plan to replay when --run-id is omitted. The script
                            replays the plan once and waits for it to complete.
                            (Or set DQ_VALIDATION_RUN_PLAN_ID)
                            Omit both --run-id and --run-plan-id to select interactively.
  --violation-threshold N   Minimum violation count that triggers incident creation.
                            Defaults to 0 (any violation triggers the incident).
  --workspace-id        ID  Workspace ID for the incident (optional; derived from run).
  --scope-kind         KIND Scope kind: data_asset|source_dataset (default: data_asset)
  --scope-id            ID  Scope ID for the incident (optional; derived from run plan).
  --no-itsm                 Skip Zammad ticket creation (create_itsm_ticket=false).
  -h, --help                Show this help
EOF
}

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

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

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [[ -f "$KONG_CA_CERT" && -z "${CURL_CA_BUNDLE:-}" ]]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi
if [[ -f "$KONG_CA_CERT" && -z "${REQUESTS_CA_BUNDLE:-}" ]]; then
  export REQUESTS_CA_BUNDLE="$KONG_CA_CERT"
fi

RUN_ID=""
RUN_PLAN_ID="${DQ_VALIDATION_RUN_PLAN_ID:-}"
VIOLATION_THRESHOLD="0"
WORKSPACE_ID=""
SCOPE_KIND=""
SCOPE_ID=""
CREATE_ITSM_TICKET="true"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id)
      RUN_ID="$2"; shift 2 ;;
    --run-plan-id)
      RUN_PLAN_ID="$2"; shift 2 ;;
    --violation-threshold)
      VIOLATION_THRESHOLD="$2"; shift 2 ;;
    --workspace-id)
      WORKSPACE_ID="$2"; shift 2 ;;
    --scope-kind)
      SCOPE_KIND="$2"; shift 2 ;;
    --scope-id)
      SCOPE_ID="$2"; shift 2 ;;
    --no-itsm)
      CREATE_ITSM_TICKET="false"; shift ;;
    --)
      shift; break ;;
    -*)
      echo "[$MY_NAME] Unknown option: $1" >&2
      print_usage
      exit 1
      ;;
    *)
      break ;;
  esac
done


export DQ_VALIDATION_RUN_ID="$RUN_ID"
export DQ_VALIDATION_RUN_PLAN_ID="$RUN_PLAN_ID"
export DQ_VALIDATION_VIOLATION_THRESHOLD="$VIOLATION_THRESHOLD"
export DQ_VALIDATION_WORKSPACE_ID="$WORKSPACE_ID"
export DQ_VALIDATION_SCOPE_KIND="${SCOPE_KIND:-data_asset}"
export DQ_VALIDATION_SCOPE_ID="$SCOPE_ID"
export DQ_VALIDATION_CREATE_ITSM_TICKET="$CREATE_ITSM_TICKET"

exec "$PYTHON_BIN" "$HELPER"
