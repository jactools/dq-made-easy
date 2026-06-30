#!/usr/bin/env bash
set -euo pipefail

# Purpose: Synchronize FastAPI dev requirements with the current repo package versions.
#
# What it does:
# - Reads pinned versions from the package pyproject.toml files.
# - Rewrites the managed wheel pin block in dq-api/fastapi/requirements-dev.txt.
#
# Version: 1.0.0
# Last modified: 2026-06-30

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
PYTHON_RUNNER="${ROOT_DIR}/scripts/python_arm64.sh"
REQUIREMENTS_FILE="${ROOT_DIR}/dq-api/fastapi/requirements-dev.txt"

source "${ROOT_DIR}/scripts/supporting/logging.sh"
source "${ROOT_DIR}/scripts/package-releases/package_release_versioning.sh"

my_name="sync_fastapi_requirements_dev.sh"

require_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: $name"
    exit 2
  fi
}

read_package_version() {
  local package_dir="$1"
  PYPROJECT_FILE="${ROOT_DIR}/${package_dir}/pyproject.toml" read_version
}

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
  error "$my_name" "Missing FastAPI requirements file: $REQUIREMENTS_FILE"
  exit 1
fi

require_cmd "$PYTHON_RUNNER"
require_cmd "$PYTHON_BIN"

CLI_VERSION="$(read_package_version dq-cli)"
UTILS_VERSION="$(read_package_version dq-utils)"
DOMAIN_VERSION="$(read_package_version dq-domain-validation)"

info "$my_name" "Synchronizing pinned FastAPI wheel requirements"

"$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" - "$REQUIREMENTS_FILE" "$CLI_VERSION" "$UTILS_VERSION" "$DOMAIN_VERSION" <<'PY'
from __future__ import annotations

from pathlib import Path
import sys

path = Path(sys.argv[1])
cli_version, utils_version, domain_version = sys.argv[2:5]

start_marker = '# BEGIN managed repo wheel pins\n'
end_marker = '# END managed repo wheel pins\n'

replacement = ''.join([
    f'./tmp/dq-cli-dist/dq_made_easy_cli-{cli_version}-py3-none-any.whl\n',
    f'./tmp/dq-utils-dist/dq_made_easy_utils-{utils_version}-py3-none-any.whl\n',
    f'./tmp/dq-domain-validation-dist/dq_made_easy_domain_validation-{domain_version}-py3-none-any.whl\n',
])

text = path.read_text(encoding='utf-8')
if start_marker not in text or end_marker not in text:
    raise SystemExit('Managed wheel pin markers are missing from requirements-dev.txt')

prefix, remainder = text.split(start_marker, 1)
_, suffix = remainder.split(end_marker, 1)
updated = prefix + start_marker + replacement + end_marker + suffix

if updated != text:
    path.write_text(updated, encoding='utf-8')
PY

success "$my_name" "Updated ${REQUIREMENTS_FILE#$ROOT_DIR/}"