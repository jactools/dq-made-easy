#!/usr/bin/env bash
set -euo pipefail

# Purpose: Shared version helpers for package release scripts.
#
# What it does:
# - Reads the current project version from a package pyproject.toml.
# - Bumps the package patch version in place after a successful publish.
#
# Version: 1.0.0
# Last modified: 2026-06-30

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
