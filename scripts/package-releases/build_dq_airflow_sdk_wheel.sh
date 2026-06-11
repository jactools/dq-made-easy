#!/usr/bin/env bash
set -euo pipefail

# Purpose: Build the dq-made-easy Airflow SDK wheel artifact.
# What it does:
# - Uses the repo virtual environment to build the wheel.
# - Writes the wheel into tmp/dq-airflow-sdk-dist.
# Version: 1.1
# Last modified: 2026-06-11

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
python_bin="$repo_root/venv/bin/python"
dist_root="$repo_root/tmp/dq-airflow-sdk-dist"
package_root="$repo_root/dq-airflow-sdk"

if [[ ! -x "$python_bin" ]]; then
  echo "Missing repo virtual environment at $python_bin" >&2
  exit 1
fi

if ! "$python_bin" -m build --version >/dev/null 2>&1; then
  echo "Missing Python build frontend in repo venv. Run: $python_bin -m pip install build" >&2
  exit 1
fi

if [[ ! -f "$package_root/pyproject.toml" ]]; then
  echo "Missing Airflow SDK package metadata at $package_root/pyproject.toml" >&2
  exit 1
fi

rm -rf "$dist_root"
mkdir -p "$dist_root"

if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  arch -arm64e /bin/bash "$repo_root/scripts/python_arm64.sh" --python-bin "$python_bin" -m build --no-isolation --wheel --outdir "$dist_root" "$package_root"
else
  "$python_bin" -m build --no-isolation --wheel --outdir "$dist_root" "$package_root"
fi

wheel_path="$(find "$dist_root" -maxdepth 1 -name 'dq_made_easy_airflow_sdk-*.whl' -print | head -n 1)"
if [[ -z "$wheel_path" ]]; then
  echo "dq-made-easy-airflow-sdk wheel was not produced in $dist_root" >&2
  exit 1
fi

printf '%s\n' "$wheel_path"
