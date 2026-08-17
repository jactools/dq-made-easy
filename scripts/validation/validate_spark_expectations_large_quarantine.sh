#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate the Spark Expectations happy path and large quarantine/error-table path.
# validate: groups=engine
# validate: include=false
# Version: 1.0.0
# Last modified: 2026-06-28

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MY_NAME="validate_spark_expectations_large_quarantine.sh"

# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/supporting/logging.sh"

if ! command -v docker >/dev/null 2>&1; then
  error "${MY_NAME}" "docker is required"
  exit 2
fi

info "${MY_NAME}" "Running Spark Expectations happy-path and large quarantine validation"
bash "${ROOT_DIR}/scripts/run_spark_expectations_container_tests.sh" \
  "dq-engine/tests/test_spark_expectations_adapter.py" \
  "-k" \
  "test_execute_spark_expectations_rule_from_adapter_executes_rows or test_execute_spark_expectations_rule_supports_count_based_aggregate_checks or test_execute_spark_expectations_rule_writes_large_quarantine_artifact"

success "${MY_NAME}" "Spark Expectations happy-path and large quarantine validation passed"