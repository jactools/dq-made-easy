#!/usr/bin/env bash
set -euo pipefail

# Purpose: Build required repo wheel artifacts for startup/rebuild workflows.
#
# What it does:
# - Under --force-build, builds core repo Python package wheels.
# - With --with-airflow, ensures Airflow SDK/operator wheels exist.
# - Enforces dq_made_easy_* wheel filename prefix policy.
# Version: 1.1
# Last modified: 2026-06-11

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/scripts/supporting/logging.sh"

set_log_level INFO
my_name="build_required_wheels.sh"

PYTHON_RUNNER="${ROOT_DIR}/scripts/python_arm64.sh"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"

FORCE_BUILD="false"
WITH_AIRFLOW="false"

usage() {
  cat <<'EOF'
Usage: scripts/package-releases/build_required_wheels.sh [--force-build] [--with-airflow]

Options:
  --force-build   Build core repo package wheels unconditionally
  --with-airflow  Ensure Airflow SDK/operator wheels are present (build if missing, or rebuild under --force-build)
  -h, --help      Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force-build)
      FORCE_BUILD="true"
      shift
      ;;
    --with-airflow)
      WITH_AIRFLOW="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "$my_name" "Unknown argument: $1"
      usage
      exit 2
      ;;
  esac
done

if [[ "$FORCE_BUILD" != "true" && "$WITH_AIRFLOW" != "true" ]]; then
  exit 0
fi

if [[ ! -x "$PYTHON_RUNNER" ]]; then
  error "$my_name" "Python runner is missing or not executable: $PYTHON_RUNNER"
  exit 2
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  error "$my_name" "Repo venv python is missing or not executable: $PYTHON_BIN"
  exit 2
fi

if ! "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m build --version >/dev/null 2>&1; then
  error "$my_name" "python -m build is required in the repo Python environment"
  exit 2
fi

build_core_package_wheels() {
  local package_dir
  local package_label
  local output_dir
  local wheel_path
  local wheel_name
  local -a package_dirs=(
    "dq-cli"
    "dq-utils"
    "dq-domain-validation"
    "dq-airflow-sdk"
    "dq-airflow-operator"
  )

  for package_dir in "${package_dirs[@]}"; do
    package_label="${package_dir//\//-}"
    output_dir="$ROOT_DIR/tmp/${package_label}-dist"

    info "$my_name" "Building wheel artifacts for $package_dir"

    rm -rf "$output_dir"
    mkdir -p "$output_dir"

    if ! (cd "$ROOT_DIR/$package_dir" && "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m build --no-isolation --sdist --wheel --outdir "$output_dir" >/dev/null); then
      error "$my_name" "Failed to build Python package artifacts for $package_dir"
      exit 1
    fi

    wheel_path="$(find "$output_dir" -maxdepth 1 -name '*.whl' -print | head -n 1)"
    if [[ -z "$wheel_path" ]]; then
      error "$my_name" "No wheel artifact was produced for $package_dir"
      exit 1
    fi

    wheel_name="$(basename "$wheel_path")"
    if [[ "$wheel_name" != dq_made_easy_* ]]; then
      error "$my_name" "Wheel naming policy violation for $package_dir: expected dq_made_easy_* prefix, got $wheel_name"
      exit 1
    fi

    success "$my_name" "Built $wheel_name"
  done
}

ensure_airflow_wheels() {
  local sdk_wheel
  local operator_wheel

  sdk_wheel="$(find "$ROOT_DIR/tmp/dq-airflow-sdk-dist" -maxdepth 1 -name 'dq_made_easy_airflow_sdk-*.whl' -print | head -n 1)"
  operator_wheel="$(find "$ROOT_DIR/tmp/dq-airflow-operator-dist" -maxdepth 1 -name 'dq_made_easy_airflow_operator-*.whl' -print | head -n 1)"

  if [[ "$FORCE_BUILD" != "true" && -f "$sdk_wheel" && -f "$operator_wheel" ]]; then
    info "$my_name" "Using existing Airflow SDK/operator wheel artifacts"
    return 0
  fi

  info "$my_name" "Building Airflow SDK/operator wheel artifacts"
  "$ROOT_DIR/scripts/package-releases/build_dq_airflow_wheels.sh" >/dev/null

  sdk_wheel="$(find "$ROOT_DIR/tmp/dq-airflow-sdk-dist" -maxdepth 1 -name 'dq_made_easy_airflow_sdk-*.whl' -print | head -n 1)"
  operator_wheel="$(find "$ROOT_DIR/tmp/dq-airflow-operator-dist" -maxdepth 1 -name 'dq_made_easy_airflow_operator-*.whl' -print | head -n 1)"
  if [[ ! -f "$sdk_wheel" || ! -f "$operator_wheel" ]]; then
    error "$my_name" "Airflow SDK/operator wheel artifacts are missing after build"
    exit 1
  fi

  success "$my_name" "Airflow SDK/operator wheel artifacts are ready"
}

if [[ "$FORCE_BUILD" == "true" ]]; then
  build_core_package_wheels
fi

if [[ "$WITH_AIRFLOW" == "true" ]]; then
  ensure_airflow_wheels
fi
