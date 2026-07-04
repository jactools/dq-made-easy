#!/usr/bin/env bash
set -euo pipefail


# Purpose: Run standalone API smoke checks and verification tests.
#
# What it does:
# - Provides functions to validate seeds and run FastAPI verification tests.
# - Can be invoked directly with flags to run selected checks.
# - Defaults to the standard seeded smoke checks when invoked without flags.
# - Uses the repo venv and installs missing dev deps when required.
#
# Version: 1.1
# Last modified: 2026-07-01

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
PYTHON_RUNNER="${PYTHON_RUNNER:-$ROOT_DIR/scripts/python_arm64.sh}"
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

my_name="smoke_test_api.sh"

resolve_fastapi_test_database_url() {
  printf '%s' "${DQ_DB_LOCAL_URL:?DQ_DB_LOCAL_URL is required}"
}

run_fastapi_seeded_list_verification_tests() {
  local fastapi_dir="$ROOT_DIR/dq-api/fastapi"
  local py_cmd="$ROOT_DIR/venv/bin/python"
  local database_url

  database_url="$(resolve_fastapi_test_database_url)"

  if [ ! -x "$py_cmd" ]; then
    error "$my_name" "FastAPI test verification failed: Python environment not found at $py_cmd"
    return 1
  fi

  info "$my_name" "Checking FastAPI verification test dependencies..."
  if ! (
    cd "$ROOT_DIR"
    "$PYTHON_RUNNER" --python-bin "$py_cmd" -c "import reportlab" >/dev/null 2>&1
  ); then
    info "$my_name" "Installing missing FastAPI test dependencies from requirements-dev.txt..."
    (
      cd "$ROOT_DIR"
      "$PYTHON_RUNNER" --python-bin "$py_cmd" -m pip install --quiet -r dq-api/fastapi/requirements-dev.txt
    ) || {
      error "$my_name" "FastAPI test verification failed: unable to install requirements-dev.txt"
      return 1
    }
  fi

  info "$my_name" "Running FastAPI seeded-list unit verification test..."
  (
    cd "$fastapi_dir"
    env REQUIRE_DATABASE=false DQ_DB_LOCAL_URL="$database_url" DQ_DB_HOST="${DQ_DB_HOST:-dq-db.jac.dot}" \
      "$PYTHON_RUNNER" --python-bin "$py_cmd" -m pytest \
      tests/api/test_list_endpoints_non_empty.py \
      --cov-fail-under=0 -q -o addopts='' --disable-warnings
  ) || {
    error "$my_name" "FastAPI seeded-list unit verification failed."
    return 1
  }

  info "$my_name" "Running FastAPI seeded-list integration verification test..."
  (
    cd "$fastapi_dir"
    env DQ_DB_LOCAL_URL="$database_url" DQ_DB_HOST="${DQ_DB_HOST:-dq-db.jac.dot}" \
      "$PYTHON_RUNNER" --python-bin "$py_cmd" -m pytest -m integration \
      tests/infrastructure/integration/test_endpoint_list_non_empty.py \
      --cov-fail-under=0 -q -o addopts='' --disable-warnings
  ) || {
    error "$my_name" "FastAPI seeded-list integration verification failed."
    return 1
  }

  success "$my_name" "FastAPI seeded-list unit + integration verification tests passed"
  return 0
}

run_seed_header_validation() {
  local py_cmd="$ROOT_DIR/venv/bin/python"

  if [ ! -x "$py_cmd" ]; then
    error "$my_name" "Seed header validation failed: Python environment not found at $py_cmd"
    return 1
  fi

  info "$my_name" "Validating generated seed headers against init schema definitions..."
  "$PYTHON_RUNNER" --python-bin "$py_cmd" "$ROOT_DIR/dq-db/scripts/validate_seed_headers.py" || {
    error "$my_name" "Seed header validation failed."
    return 1
  }

  return 0
}

print_usage() {
  cat <<'EOF'
Usage: smoke_test_api.sh [--env dev|test|prod] [--env-file PATH] [--seed-headers] [--fastapi-tests]

Options:
  --env dev|test|prod  Use .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH      Use an explicit env file
  --seed-headers    Run seed header validation
  --fastapi-tests   Run FastAPI seeded-list unit+integration tests
  -h, --help        Show this help
EOF
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  # invoked directly; parse args
  init_root_env_file "$ROOT_DIR"
  if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
    print_usage
    exit 1
  fi

  set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

  validate_selected_root_env_file "$ROOT_DIR" full

  if ! source_selected_root_env_file; then
    exit 1
  fi

  if [[ $# -eq 0 ]]; then
    run_seed_header_validation || exit 1
    run_fastapi_seeded_list_verification_tests || exit 1
    exit 0
  fi

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --seed-headers)
        run_seed_header_validation || exit 1
        shift
        ;;
      --fastapi-tests)
        run_fastapi_seeded_list_verification_tests || exit 1
        shift
        ;;
      -h|--help)
        print_usage
        exit 0
        ;;
      *)
        echo "Unknown arg: $1"
        print_usage
        exit 1
        ;;
    esac
  done
fi
