#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FASTAPI_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
DQ_API_DIR="$(cd "$FASTAPI_DIR/.." && pwd)"
PYTHON_RUNNER="$DQ_API_DIR/../scripts/python_arm64.sh"
PYTHON_BIN="${PYTHON_BIN:-$FASTAPI_DIR/../../venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

source "$DQ_API_DIR/scripts/testing/ensure_arm64_python_env.sh"
ensure_arm64_python_env "$PYTHON_BIN"

run_py() {
  "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" "$@"
}

UNIT_TEST_PATHS=(
  tests/api
  tests/application
  tests/core
  tests/domain
  tests/infrastructure
  tests/middleware
)

CONTRACT_TEST_PATHS=(
  tests/api/test_ui_endpoint_contract.py
  tests/api/test_ui_endpoint_contract_all.py
)

cd "$FASTAPI_DIR"

echo "==> Enforcing fixture usage for non-ORM tests..."
run_py scripts/testing/check_fixture_usage.py

UNIT_FILES=$(find "${UNIT_TEST_PATHS[@]}" -name '*.py' -print)

REPORT_DIR="$FASTAPI_DIR/test-results"
LINT_LOG="$REPORT_DIR/unit-pylint.log"
PYTEST_LOG="$REPORT_DIR/unit-pytest.log"
JUNIT_XML="$REPORT_DIR/unit-junit.xml"
SUMMARY_MD="$REPORT_DIR/unit-review-summary.md"

mkdir -p "$REPORT_DIR"

set +e
run_py -m pylint app $UNIT_FILES --disable=all --enable=E,F --disable=E1102,E1136 --score=n 2>&1 | tee "$LINT_LOG"
LINT_EXIT=${PIPESTATUS[0]}

PYTEST_EXIT=0
if [[ $LINT_EXIT -eq 0 ]]; then
  run_py -m pytest -q -o addopts='' "${CONTRACT_TEST_PATHS[@]}" 2>&1 | tee "$PYTEST_LOG"
  PYTEST_EXIT=${PIPESTATUS[0]}

  if [[ $PYTEST_EXIT -eq 0 ]]; then
    run_py -m pytest -q -o addopts='' --cov --cov-config=../.coveragerc --cov-report=term --cov-fail-under=0 --junitxml="$JUNIT_XML" "${UNIT_TEST_PATHS[@]}" 2>&1 | tee "$PYTEST_LOG"
    PYTEST_EXIT=${PIPESTATUS[0]}
  fi
else
  printf 'Skipped pytest because pylint failed.\n' | tee "$PYTEST_LOG"
fi
set -e

{
  printf -- '# Unit Review Summary\n\n'
  printf -- '- Generated at: %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
  printf -- '- Lint exit code: %s\n' "$LINT_EXIT"
  printf -- '- Pytest exit code: %s\n' "$PYTEST_EXIT"
  printf -- '- Lint log: %s\n' "$LINT_LOG"
  printf -- '- Pytest log: %s\n' "$PYTEST_LOG"
  if [[ -f "$JUNIT_XML" ]]; then
    printf -- '- JUnit XML: %s\n' "$JUNIT_XML"
  else
    printf -- '- JUnit XML: not generated\n'
  fi
} > "$SUMMARY_MD"

if [[ $LINT_EXIT -ne 0 ]]; then
  exit "$LINT_EXIT"
fi

if [[ $PYTEST_EXIT -ne 0 ]]; then
  exit "$PYTEST_EXIT"
fi
