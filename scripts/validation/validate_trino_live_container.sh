#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate Trino execution against a live Trino container.
# What it does:
# - Requires the Trino compose profile/container to already be running.
# - Runs the live Trino smoke and integration pytest tests from dq-engine.
# - Fails when the live tests skip because Trino is unavailable.
# - Writes a repeatable evidence log under test-results/evidence.
#
# validate: groups=engine
# Version: 1.0
# Last modified: 2026-06-30

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="$ROOT_DIR/venv/bin/python"
PYTEST_TARGET="tests/test_trino_live_container.py"
MY_NAME="validate_trino_live_container.sh"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

print_usage() {
  cat <<'EOF'
Usage: scripts/validation/validate_trino_live_container.sh [OPTIONS]

Runs the live Trino smoke and integration tests against the Trino compose service.
The Trino container must already be up; this script never starts or stops it.

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file

Validation options:
  --pytest-args ARGS       Additional pytest args appended after the default target
  -h, --help               Show this help
EOF
}

EVIDENCE_DIR=""
LOG_FILE=""
PYTEST_ARGS=()

trino_is_running() {
  docker ps \
    --filter 'name=^/dq-made-easy-trino$' \
    --filter 'status=running' \
    --format '{{.ID}}' \
    | grep -q .
}

cleanup() {
  local exit_code=$?
  exit "$exit_code"
}

run_logged() {
  "$@" 2>&1 | tee -a "$LOG_FILE"
  return "${PIPESTATUS[0]}"
}

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 2
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pytest-args)
      if [[ -z "${2:-}" ]]; then
        error "$MY_NAME" "--pytest-args requires a quoted argument string"
        print_usage
        exit 2
      fi
      # shellcheck disable=SC2206
      PYTEST_ARGS+=($2)
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

if [[ ! -x "$PYTHON_BIN" ]]; then
  error "$MY_NAME" "Missing required Python interpreter: $PYTHON_BIN"
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  error "$MY_NAME" "Missing required command: docker"
  exit 2
fi

validate_selected_root_env_file "$ROOT_DIR" full

if [[ -f "$ROOT_ENV_FILE" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "$ROOT_ENV_FILE"
  set -u
fi

APP_VERSION="${APP_VERSION:-0.11.5}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_DIR="$ROOT_DIR/test-results/evidence/$APP_VERSION/api/${TIMESTAMP}-dq-engine-trino-live-container"
LOG_FILE="$EVIDENCE_DIR/validation.log"
mkdir -p "$EVIDENCE_DIR"

trap cleanup EXIT

{
  echo "validation: dq-engine-trino-live-container"
  echo "timestamp_utc: $TIMESTAMP"
  echo "root_env_file: $ROOT_ENV_FILE"
  echo "pytest_target: $PYTEST_TARGET"
  echo "requires_live_trino_container: true"
  echo "container_lifecycle_managed_by_script: false"
  echo ""
} | tee "$LOG_FILE"

if ! trino_is_running; then
  error "$MY_NAME" "Trino is not running. Start it first with: ./scripts/stack_ctl.sh start --env-file '$ROOT_ENV_FILE' --profile trino"
  exit 1
fi

info "$MY_NAME" "Running live Trino pytest validation"
(
  cd "$ROOT_DIR/dq-engine"
  run_logged "$PYTHON_BIN" -m pytest "$PYTEST_TARGET" -q -rs ${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"}
)

if grep -Eq '(^SKIPPED|[[:space:]][0-9]+ skipped|[0-9]+ skipped)' "$LOG_FILE"; then
  error "$MY_NAME" "Live Trino validation skipped tests; the container must be running and accepting queries. See $LOG_FILE"
  exit 1
fi

info "$MY_NAME" "Validation evidence written to $EVIDENCE_DIR"
