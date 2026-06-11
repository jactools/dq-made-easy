#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
cd "$ROOT_DIR"

source "$REPO_ROOT/scripts/supporting/logging.sh"
my_name="generate_sql_seeds.sh"

PY_SCRIPT="${ROOT_DIR}/scripts/generate_sql_seeds.py"
INPUT_DIR="${1}"
OUTPUT_DIR="${2}"

if [ ! -f "$PY_SCRIPT" ]; then
  error "$my_name" "Missing generator script: $PY_SCRIPT"
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

info "$my_name" "Generating SQL seed files from CSVs in: $INPUT_DIR -> $OUTPUT_DIR"
"$REPO_ROOT/scripts/python_arm64.sh" --python-bin python3 "$PY_SCRIPT" --input-dir "$INPUT_DIR" --output-dir "$OUTPUT_DIR"
info "$my_name" "Done."
