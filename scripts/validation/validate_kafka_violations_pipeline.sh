#!/usr/bin/env bash
set -euo pipefail

# Purpose: Integration test that runs a real DQ plan producing violations,
# validates the full pipeline: engine → Kafka → consumer → DB + S3.
#
# What it does:
# - Loads the selected repo env file so the helper uses the canonical local contract.
# - Delegates to a Python helper that:
#   1. Triggers a DQ run plan (or ad-hoc GX suite) that generates violations
#   2. Waits for the run to complete
#   3. Verifies violations are persisted in PostgreSQL
#   4. Verifies violation records are stored in S3
#   5. Validates Kafka topic flow (optional if Kafka is not available)
# - Generates a test-proof JSON artifact under test-results/test-proof/
#
# validate: groups=engine,kafka,s3,integration
# Version: 1.0.0
# Last modified: 2026-07-04

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
HELPER="${SCRIPT_DIR}/validate_kafka_violations_pipeline.py"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"

print_usage() {
  cat <<'EOF'
Usage: scripts/validate_kafka_violations_pipeline.sh [options]

Options:
  --env dev|test|prod     Select the root env file (default: dev)
  --run-plan-id ID        Optional pre-existing run plan to invoke
  --skip-kafka            Skip Kafka verification (test DB + S3 only)
  --timeout SECONDS       Max wait time for run completion (default: 600)
  -h, --help              Show this help
EOF
}

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

# Parse optional args
SKIP_KAFKA="false"
EXTRA_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --skip-kafka) SKIP_KAFKA="true" ;;
    -h|--help) print_usage; exit 0 ;;
    *) EXTRA_ARGS+=("$arg") ;;
  esac
done

validate_selected_root_env_file "$ROOT_DIR" full

if ! source_selected_root_env_file; then
  exit 1
fi

if ! dq_source_seeded_user_credentials --quiet; then
  exit 1
fi

KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"

if [[ -f "$KONG_CA_CERT" && -z "${CURL_CA_BUNDLE:-}" ]]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

if [[ -f "$KONG_CA_CERT" && -z "${REQUESTS_CA_BUNDLE:-}" ]]; then
  export REQUESTS_CA_BUNDLE="$KONG_CA_CERT"
fi

export SKIP_KAFKA="${SKIP_KAFKA}"

if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  echo "Unknown args: ${EXTRA_ARGS[*]}" >&2
  exit 2
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing required Python interpreter: $PYTHON_BIN" >&2
  exit 2
fi

exec "$PYTHON_BIN" "$HELPER" "$@"
