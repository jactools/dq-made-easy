#!/usr/bin/env bash
set -euo pipefail

# Purpose: Build, publish, and version-bump the standalone dq-made-easy-airflow-sdk package.
#
# What it does:
# - Builds wheel and sdist artifacts for dq-made-easy-airflow-sdk.
# - Publishes the artifacts to a named Twine repository.
# - Bumps dq-airflow-sdk/pyproject.toml to the next patch version after a successful publish.
#
# Version: 1.0.0
# Last modified: 2026-05-31

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
PYTHON_RUNNER="${ROOT_DIR}/scripts/python_arm64.sh"
PACKAGE_DIR="${ROOT_DIR}/dq-airflow-sdk"
PYPROJECT_FILE="${PACKAGE_DIR}/pyproject.toml"
DIST_DIR="${ROOT_DIR}/tmp/dq-airflow-sdk-release"
REPOSITORY="pypi"
DRY_RUN="false"

usage() {
  cat <<'EOF'
Usage: scripts/package-releases/release_dq_airflow_sdk.sh [--repository NAME] [--dry-run]

Options:
  --repository NAME  Twine repository name to publish to (default: pypi)
  --dry-run          Build and check artifacts without uploading or bumping
  -h, --help         Show this help
EOF
}

require_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    printf 'release_dq_airflow_sdk.sh: missing required command: %s\n' "$name" >&2
    exit 2
  fi
}

read_version() {
  "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" - "$PYPROJECT_FILE" <<'PY'
from __future__ import annotations

import pathlib
import sys

path = pathlib.Path(sys.argv[1])
version = None
for line in path.read_text(encoding='utf-8').splitlines():
    stripped = line.strip()
    if stripped.startswith('version = '):
        version = stripped.split('=', 1)[1].strip().strip('"')
        break

if not version:
    raise SystemExit('Unable to read version from pyproject.toml')

print(version)
PY
}

bump_patch_version() {
  local current_version="$1"
  "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" - "$PYPROJECT_FILE" "$current_version" <<'PY'
from __future__ import annotations

import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
current_version = sys.argv[2].strip()
match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', current_version)
if not match:
    raise SystemExit(f'Expected a simple X.Y.Z version, got {current_version!r}')

major, minor, patch = (int(part) for part in match.groups())
next_version = f'{major}.{minor}.{patch + 1}'
text = path.read_text(encoding='utf-8')
updated = re.sub(r'^version = ".*"$', f'version = "{next_version}"', text, count=1, flags=re.MULTILINE)
if updated == text:
    raise SystemExit('Failed to update version in pyproject.toml')
path.write_text(updated, encoding='utf-8')
print(next_version)
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repository)
      if [[ $# -lt 2 ]]; then
        printf 'release_dq_airflow_sdk.sh: --repository requires a value\n' >&2
        usage
        exit 2
      fi
      REPOSITORY="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'release_dq_airflow_sdk.sh: unknown argument: %s\n' "$1" >&2
      usage
      exit 2
      ;;
  esac
done

require_cmd "$PYTHON_RUNNER"
require_cmd "$PYTHON_BIN"

if ! "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m build --version >/dev/null 2>&1; then
  printf 'release_dq_airflow_sdk.sh: build is required in the repo venv\n' >&2
  exit 2
fi

if ! "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m twine --version >/dev/null 2>&1; then
  printf 'release_dq_airflow_sdk.sh: twine is required in the repo venv\n' >&2
  exit 2
fi

cd "$PACKAGE_DIR"
CURRENT_VERSION="$(read_version)"

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

printf 'Building dq-made-easy-airflow-sdk %s\n' "$CURRENT_VERSION"
"$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m build --sdist --wheel --outdir "$DIST_DIR"
"$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m twine check "$DIST_DIR"/*

if [[ "$DRY_RUN" == "true" ]]; then
  printf 'Dry run complete for dq-made-easy-airflow-sdk %s\n' "$CURRENT_VERSION"
  exit 0
fi

printf 'Publishing dq-made-easy-airflow-sdk %s to %s\n' "$CURRENT_VERSION" "$REPOSITORY"
"$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m twine upload --non-interactive --repository "$REPOSITORY" "$DIST_DIR"/*

NEXT_VERSION="$(bump_patch_version "$CURRENT_VERSION")"
printf 'Bumped dq-airflow-sdk/pyproject.toml from %s to %s\n' "$CURRENT_VERSION" "$NEXT_VERSION"
