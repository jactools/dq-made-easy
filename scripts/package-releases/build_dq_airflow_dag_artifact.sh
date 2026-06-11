#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
source_dir="$repo_root/docker/airflow/dags"
dist_root="$repo_root/tmp/dq-airflow-dags-dist"
stable_zip="$dist_root/dq-airflow-dags.zip"

if ! command -v zip >/dev/null 2>&1; then
  echo "Missing zip CLI required to build the Airflow DAG artifact" >&2
  exit 1
fi

rm -rf "$dist_root"
mkdir -p "$dist_root"

(
  cd "$source_dir"
  zip -q "$stable_zip" dq_validation_run_plan.py
)

if [[ ! -f "$stable_zip" ]]; then
  echo "Airflow DAG artifact was not produced at $stable_zip" >&2
  exit 1
fi

printf '%s\n' "$stable_zip"
