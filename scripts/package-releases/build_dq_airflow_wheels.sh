#!/usr/bin/env bash
set -euo pipefail

# Purpose: Build the Airflow wheel artifacts used by the repo Airflow image.
#
# What it does:
# - Builds the dq-made-easy-airflow-sdk wheel.
# - Builds the dq-made-easy-airflow-operator wheel.
# - Prints both resulting wheel paths.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

sdk_wheel_path="$(${ROOT_DIR}/scripts/package-releases/build_dq_airflow_sdk_wheel.sh)"
operator_wheel_path="$(${ROOT_DIR}/scripts/package-releases/build_dq_airflow_operator_wheel.sh)"

printf '%s\n' "$sdk_wheel_path"
printf '%s\n' "$operator_wheel_path"
