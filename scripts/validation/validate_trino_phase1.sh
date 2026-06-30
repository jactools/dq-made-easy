#!/usr/bin/env bash
set -euo pipefail

# Purpose: Run the Trino Phase 1 validation suite.
# What it does:
# - Runs the full Trino unit/integration coverage gate.
# - Runs live Trino container smoke/integration validation.
# - Runs a Trino query-rule validation against existing AIStor-backed parquet data.
# - Runs the repeatable Trino Phase 1 performance benchmark.
# - Writes a repeatable validation log under test-results/evidence.
#
# validate: groups=engine,performance
# Version: 1.0
# Last modified: 2026-06-30

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="$ROOT_DIR/venv/bin/python"
MY_NAME="validate_trino_phase1.sh"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

print_usage() {
  cat <<'EOF'
Usage: scripts/validation/validate_trino_phase1.sh [OPTIONS]

Runs Trino Phase 1 validation: focused coverage gate, live Trino container tests,
a real AIStor parquet query-rule check, and the Phase 1 benchmark. The Trino and
AIStor containers must already be up; this script never starts or stops them.

Canonical env options:
  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Use an explicit env file

Validation options:
  --dry-run               Run without live Trino or AIStor parquet tests
  --skip-live              Skip live Trino and AIStor parquet tests
  --skip-benchmark         Skip the Phase 1 benchmark
  --pytest-args ARGS       Additional pytest args appended after the coverage targets
  -h, --help               Show this help
EOF
}

DRY_RUN=false
SKIP_LIVE=false
SKIP_BENCHMARK=false
PYTEST_ARGS=()

run_logged() {
  "$@" 2>&1 | tee -a "$LOG_FILE"
  return "${PIPESTATUS[0]}"
}

fail_when_logged_tests_skipped() {
  local validation_name="$1"
  if grep -Eq '(^SKIPPED|[[:space:]][0-9]+ skipped|[0-9]+ skipped)' "$LOG_FILE"; then
    error "$MY_NAME" "$validation_name skipped tests; required live dependencies must be running and configured. See $LOG_FILE"
    exit 1
  fi
}

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 2
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      SKIP_LIVE=true
      shift
      ;;
    --skip-live)
      SKIP_LIVE=true
      shift
      ;;
    --skip-benchmark)
      SKIP_BENCHMARK=true
      shift
      ;;
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

if [[ "$SKIP_LIVE" != "true" ]] && ! command -v docker >/dev/null 2>&1; then
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

export DQ_S3_ENDPOINT="${DQ_S3_ENDPOINT:-${AWS_ENDPOINT_URL:-http://aistor:9000}}"
export DQ_S3_ACCESS_KEY="${DQ_S3_ACCESS_KEY:-${AWS_ACCESS_KEY_ID:-aistoradmin}}"
export DQ_S3_SECRET_KEY="${DQ_S3_SECRET_KEY:-${AWS_SECRET_ACCESS_KEY:-aistoradmin}}"
export DQ_S3_REGION="${DQ_S3_REGION:-${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}}"
export DQ_S3_PATH_STYLE_ACCESS="${DQ_S3_PATH_STYLE_ACCESS:-true}"
export DQ_S3_SSL_ENABLED="${DQ_S3_SSL_ENABLED:-false}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-$DQ_S3_ACCESS_KEY}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-$DQ_S3_SECRET_KEY}"
export AWS_REGION="${AWS_REGION:-$DQ_S3_REGION}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-$DQ_S3_REGION}"
export TRINO_AISTOR_VALIDATION_INPUT_URI="${TRINO_AISTOR_VALIDATION_INPUT_URI:-s3a://retail-banking/standardized/analytics/Currency/v1/LOAD_DTS=20260220T071500000Z}"
export TRINO_AISTOR_VALIDATION_EXPECTED_COUNT="${TRINO_AISTOR_VALIDATION_EXPECTED_COUNT:-180}"

APP_VERSION="${APP_VERSION:-0.11.5}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_DIR="$ROOT_DIR/test-results/evidence/$APP_VERSION/api/${TIMESTAMP}-dq-engine-trino-phase1-validation"
LOG_FILE="$EVIDENCE_DIR/validation.log"
BENCHMARK_OUTPUT="$EVIDENCE_DIR/benchmark.json"
mkdir -p "$EVIDENCE_DIR"

{
  echo "validation: dq-engine-trino-phase1-validation"
  echo "timestamp_utc: $TIMESTAMP"
  echo "root_env_file: $ROOT_ENV_FILE"
  echo "dry_run: $DRY_RUN"
  echo "skip_live: $SKIP_LIVE"
  echo "skip_benchmark: $SKIP_BENCHMARK"
  echo "trino_aistor_validation_input_uri: $TRINO_AISTOR_VALIDATION_INPUT_URI"
  echo "trino_aistor_validation_expected_count: $TRINO_AISTOR_VALIDATION_EXPECTED_COUNT"
  echo "container_lifecycle_managed_by_script: false"
  echo ""
} | tee "$LOG_FILE"

info "$MY_NAME" "Running Trino coverage gate"
(
  cd "$ROOT_DIR/dq-engine"
  run_logged "$PYTHON_BIN" -m pytest \
    tests/test_trino_adapter.py \
    tests/test_trino_executor.py \
    tests/test_trino_execution_pipeline.py \
    tests/test_runtime_lowerer_registry.py \
    --cov=trino_adapter \
    --cov=trino_config \
    --cov=trino_executor \
    --cov=trino_execution_pipeline \
    --cov-report=term-missing \
    --cov-fail-under=90 \
    -q \
    ${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"}
)

if [[ "$SKIP_LIVE" != "true" ]]; then
  info "$MY_NAME" "Running live Trino container validation"
  run_logged "$ROOT_DIR/scripts/validation/validate_trino_live_container.sh" --env-file "$ROOT_ENV_FILE"
  fail_when_logged_tests_skipped "Live Trino container validation"

  info "$MY_NAME" "Running real AIStor parquet validation through Trino"
  (
    cd "$ROOT_DIR/dq-engine"
    run_logged "$PYTHON_BIN" -m pytest tests/test_trino_real_aistor_parquet_validation.py -q -rs
  )
  fail_when_logged_tests_skipped "Real AIStor parquet validation through Trino"
else
  info "$MY_NAME" "Skipping live Trino and AIStor parquet validation"
fi

if [[ "$SKIP_BENCHMARK" != "true" ]]; then
  info "$MY_NAME" "Running Trino Phase 1 benchmark"
  run_logged "$PYTHON_BIN" "$ROOT_DIR/scripts/validation/benchmark_trino_phase1.py" --output "$BENCHMARK_OUTPUT"
else
  info "$MY_NAME" "Skipping Trino Phase 1 benchmark"
fi

info "$MY_NAME" "Validation evidence written to $EVIDENCE_DIR"