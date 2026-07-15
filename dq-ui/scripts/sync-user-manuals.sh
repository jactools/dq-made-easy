#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
python_bin="$repo_root/venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
  echo "[sync-user-manuals] Missing Python interpreter: $python_bin" >&2
  exit 1
fi

exec "$python_bin" "$script_dir/sync-user-manuals.py" "$@"