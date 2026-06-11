#!/usr/bin/env bash
set -euo pipefail


# Purpose: Seed the ISO 11179 registry-definition demo slice into OpenMetadata.
#
# What it does:
# - Runs the strict retail-banking registry-definition loader with the repo venv.
# - Uses the committed demo manifest under dq-metadata/demo by default.
# - Fails fast if the OpenMetadata extension fields are unsupported or seeding fails.
#
# Version: 1.0
# Last modified: 2026-04-20

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="seed_openmetadata_registry_definitions.sh"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/venv/bin/python}"
MANIFEST_PATH="${MANIFEST_PATH:-$ROOT_DIR/dq-metadata/demo/openmetadata_registry_definitions.retail_banking.json}"
OUTPUT_PATH="${OUTPUT_PATH:-$ROOT_DIR/tmp/openmetadata-registry-definitions/seed-report.json}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  error "$my_name" "Python executable not found or not executable: $PYTHON_BIN"
  exit 2
fi

exec "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" \
  "$ROOT_DIR/dq-metadata/scripts/seed_openmetadata_registry_definitions.py" \
  --manifest "$MANIFEST_PATH" \
  --output "$OUTPUT_PATH" \
  "$@"