#!/usr/bin/env bash
set -euo pipefail


# Purpose: Seed the ODPS retail-banking product-spec demo slice into OpenMetadata.
#
# What it does:
# - Runs the strict retail-banking product-spec loader with the repo venv.
# - Uses the committed demo manifest under dq-metadata/demo by default.
# - Fails fast if the linked ODCS contract has not already been seeded into OpenMetadata.
#
# Version: 1.0
# Last modified: 2026-05-31

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="seed_openmetadata_product_specs.sh"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/venv/bin/python}"
MANIFEST_PATH="${MANIFEST_PATH:-$ROOT_DIR/dq-metadata/demo/openmetadata_product_specs.retail_banking.json}"
OUTPUT_PATH="${OUTPUT_PATH:-$ROOT_DIR/tmp/openmetadata-product-specs/seed-report.json}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  error "$my_name" "Python executable not found or not executable: $PYTHON_BIN"
  exit 2
fi

exec "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" \
  "$ROOT_DIR/dq-metadata/scripts/seed_openmetadata_product_specs.py" \
  --manifest "$MANIFEST_PATH" \
  --output "$OUTPUT_PATH" \
  "$@"