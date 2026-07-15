#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate that a specific DQ run plan can be invoked through the CLI module.
#
# What it does:
# - Loads the selected repo env file so the script uses the canonical local validation contract.
# - Invokes the real dq-run-plan CLI module through the repo Python interpreter.
# - Verifies the replay response is consistent and emits the CLI JSON output.
#
# validate: groups=api,cli,regression
# Version: 1.0.1
# Last modified: 2026-05-17

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
PYTHON_RUNNER="${ROOT_DIR}/scripts/python_arm64.sh"
CLI_MODULE_DIR="${ROOT_DIR}/dq-cli"
MY_NAME="validate_dq_run_plan_invoke.sh"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

print_usage() {
  cat <<'EOF'
Usage: scripts/validate_dq_run_plan_invoke.sh [--run-plan-id ID]

Options:
  --env dev|test|prod
                     Select the root env file using the common repo env selector
  --run-plan-id ID   Run-plan id to replay
  DQ_VALIDATION_RUN_PLAN_ID
                     Default run-plan id used when --run-plan-id is omitted
  -h, --help         Show this help
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

RUN_PLAN_ID="${DQ_VALIDATION_RUN_PLAN_ID:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-plan-id)
      if [[ $# -lt 2 ]]; then
        error "$MY_NAME" "--run-plan-id requires a value"
        print_usage
        exit 2
      fi
      RUN_PLAN_ID="$2"
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

if [[ ! -x "$PYTHON_RUNNER" ]]; then
  error "$MY_NAME" "Missing required Python launcher: $PYTHON_RUNNER"
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  error "$MY_NAME" "Missing required command: jq"
  exit 127
fi

API_BASE_URL="${DQ_API_LOCAL_URL:-}"
if [[ -z "$API_BASE_URL" ]]; then
  error "$MY_NAME" "DQ_API_LOCAL_URL is required"
  exit 2
fi

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
CLI_ARGS=(
  --base-url "$API_BASE_URL"
  --issuer-url "$SSO_PUBLIC_ISSUER_URL"
  --client-id "$VITE_KEYCLOAK_CLIENT_ID"
  --username "$KEYCLOAK_JACCLOUD_USERNAME"
  --password "$KEYCLOAK_JACCLOUD_PASSWORD"
  --json
  invoke
  --run-plan-id "$RUN_PLAN_ID"
)

if [[ -f "$KONG_CA_CERT" ]]; then
  CLI_ARGS=(
    --base-url "$API_BASE_URL"
    --issuer-url "$SSO_PUBLIC_ISSUER_URL"
    --client-id "$VITE_KEYCLOAK_CLIENT_ID"
    --username "$KEYCLOAK_JACCLOUD_USERNAME"
    --password "$KEYCLOAK_JACCLOUD_PASSWORD"
    --ca-cert "$KONG_CA_CERT"
    --json
    invoke
    --run-plan-id "$RUN_PLAN_ID"
  )
fi

set +e
CLI_OUTPUT="$(PYTHONPATH="$CLI_MODULE_DIR${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m dq_cli.run_plan "${CLI_ARGS[@]}")"
CLI_RC=$?
set -e
if [[ "$CLI_RC" -ne 0 ]]; then
  exit "$CLI_RC"
fi

RETURNED_RUN_PLAN_ID="$(printf '%s' "$CLI_OUTPUT" | jq -r '.run_plan_id // empty')"
QUEUE_MESSAGE_ID="$(printf '%s' "$CLI_OUTPUT" | jq -r '.queue_message_id // empty')"
RUN_ID="$(printf '%s' "$CLI_OUTPUT" | jq -r '.run_id // empty')"

if [[ -z "$RETURNED_RUN_PLAN_ID" ]]; then
  error "$MY_NAME" "CLI output did not include run_plan_id"
  printf '%s\n' "$CLI_OUTPUT" >&2
  exit 1
fi

if [[ "$RETURNED_RUN_PLAN_ID" != "$RUN_PLAN_ID" ]]; then
  error "$MY_NAME" "CLI output returned run_plan_id=${RETURNED_RUN_PLAN_ID}, expected ${RUN_PLAN_ID}"
  printf '%s\n' "$CLI_OUTPUT" >&2
  exit 1
fi

if [[ -z "$QUEUE_MESSAGE_ID" || -z "$RUN_ID" ]]; then
  error "$MY_NAME" "CLI output is missing queue_message_id or run_id"
  printf '%s\n' "$CLI_OUTPUT" >&2
  exit 1
fi

info "$MY_NAME" "Replayed DQ run plan ${RUN_PLAN_ID}"
printf '%s\n' "$CLI_OUTPUT"

success "$MY_NAME" "DQ run-plan invoke validation passed"