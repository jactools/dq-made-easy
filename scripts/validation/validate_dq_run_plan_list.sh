#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate that the DQ run-plan catalog can be listed through the CLI module.
#
# What it does:
# - Loads the selected repo env file so the script uses the canonical local validation contract.
# - Invokes the real dq-run-plan CLI module through the repo Python interpreter.
# - Verifies the catalog response is non-empty and emits a concise summary.
#
# validate: groups=api,cli
# Version: 1.0.0
# Last modified: 2026-05-17

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
PYTHON_RUNNER="${ROOT_DIR}/scripts/python_arm64.sh"
CLI_MODULE_DIR="${ROOT_DIR}/dq-cli"
MY_NAME="validate_dq_run_plan_list.sh"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

print_usage() {
  cat <<'EOF'
Usage: scripts/validate_dq_run_plan_list.sh [--workspace-id ID] [--business-key KEY] [--suite-id ID] [--status STATUS]

Options:
  --workspace-id ID   Filter by workspace id
  --business-key KEY   Filter by business key
  --suite-id ID       Filter by suite id
  --status STATUS     Filter by run-plan status
  -h, --help          Show this help
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

declare -a CLI_ARGS=(
  --base-url "$KONG_PUBLIC_URL"
  --issuer-url "$SSO_PUBLIC_ISSUER_URL"
  --client-id "$VITE_KEYCLOAK_CLIENT_ID"
  --username "$KEYCLOAK_JACCLOUD_USERNAME"
  --password "$KEYCLOAK_JACCLOUD_PASSWORD"
  --json
  list
)

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [[ -f "$KONG_CA_CERT" ]]; then
  CLI_ARGS=(
    --base-url "$KONG_PUBLIC_URL"
    --issuer-url "$SSO_PUBLIC_ISSUER_URL"
    --client-id "$VITE_KEYCLOAK_CLIENT_ID"
    --username "$KEYCLOAK_JACCLOUD_USERNAME"
    --password "$KEYCLOAK_JACCLOUD_PASSWORD"
    --ca-cert "$KONG_CA_CERT"
    --json
    list
  )
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace-id)
      if [[ $# -lt 2 ]]; then
        error "$MY_NAME" "--workspace-id requires a value"
        print_usage
        exit 2
      fi
      CLI_ARGS+=("--workspace-id" "$2")
      shift 2
      ;;
    --business-key)
      if [[ $# -lt 2 ]]; then
        error "$MY_NAME" "--business-key requires a value"
        print_usage
        exit 2
      fi
      CLI_ARGS+=("--business-key" "$2")
      shift 2
      ;;
    --suite-id)
      if [[ $# -lt 2 ]]; then
        error "$MY_NAME" "--suite-id requires a value"
        print_usage
        exit 2
      fi
      CLI_ARGS+=("--suite-id" "$2")
      shift 2
      ;;
    --status)
      if [[ $# -lt 2 ]]; then
        error "$MY_NAME" "--status requires a value"
        print_usage
        exit 2
      fi
      CLI_ARGS+=("--status" "$2")
      shift 2
      ;;
    *)
      error "$MY_NAME" "Unknown argument: $1"
      print_usage
      exit 2
      ;;
  esac
done

set +e
CLI_OUTPUT="$(PYTHONPATH="$CLI_MODULE_DIR${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m dq_cli.run_plan "${CLI_ARGS[@]}")"
CLI_RC=$?
set -e
if [[ "$CLI_RC" -ne 0 ]]; then
  exit "$CLI_RC"
fi

RUN_PLAN_COUNT="$(printf '%s' "$CLI_OUTPUT" | jq -r '.validation_summary.run_plan_count // empty')"
if [[ -z "$RUN_PLAN_COUNT" ]]; then
  error "$MY_NAME" "CLI output did not include validation_summary.run_plan_count"
  printf '%s\n' "$CLI_OUTPUT" >&2
  exit 1
fi

if [[ "$RUN_PLAN_COUNT" -lt 1 ]]; then
  error "$MY_NAME" "CLI returned no run plans"
  printf '%s\n' "$CLI_OUTPUT" >&2
  exit 1
fi

info "$MY_NAME" "Listed ${RUN_PLAN_COUNT} DQ run plan(s)"
printf '%s\n' "$CLI_OUTPUT"

success "$MY_NAME" "DQ run-plan listing validation passed"