#!/usr/bin/env bash
set -euo pipefail

# Purpose: Run the Spark Expectations real-data validation against AIStor-backed parquet data.
#
# validate: groups=engine
# Version: 1.0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 2
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
export SPARK_EXPECTATIONS_VALIDATION_INPUT_URI="${SPARK_EXPECTATIONS_VALIDATION_INPUT_URI:-s3a://retail-banking/standardized/analytics/Currency/v1/LOAD_DTS=20260220T071500000Z}"

echo "Validating the newly added Spark Expectations expression families against AIStor parquet..."
bash "$ROOT_DIR/scripts/run_spark_expectations_container_tests.sh" \
  "dq-engine/tests/test_spark_expectations_real_aistor_validation.py" \
  "-k" \
  "contains or not_in or min_length or regex or avg or stddev or unique or missing_count or duplicate_count or row_count or distinct_count"

echo "Validating the full Spark Expectations construct matrix against AIStor parquet..."
bash "$ROOT_DIR/scripts/run_spark_expectations_container_tests.sh" \
  "dq-engine/tests/test_spark_expectations_real_aistor_validation.py"

echo "Validating the large quarantine/error-table path for Spark Expectations..."
bash "$ROOT_DIR/scripts/validate_spark_expectations_large_quarantine.sh"
