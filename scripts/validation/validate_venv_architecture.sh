#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate local Python venv architecture compatibility.
#
# What it does:
# - Detects Rosetta usage on Apple Silicon.
# - Scans site-packages for single-arch x86_64 native extensions.
#
# validate: groups=repo

# Version: 1.1
# Last modified: 2026-04-07

# Verify that a Python virtual environment does not contain single-arch x86_64
# native extensions that will fail on Apple Silicon arm64 runtime.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_venv_architecture.sh"
VENV_DIR="${1:-${ROOT_DIR}/venv}"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  error "$my_name" "Python executable not found at ${VENV_DIR}/bin/python"
  exit 2
fi

if ! command -v file >/dev/null 2>&1; then
  error "$my_name" "'file' command is required but not found in PATH"
  exit 2
fi

PYTHON_BIN_DESC="$(file "${VENV_DIR}/bin/python")"
HOST_ARCH="$(uname -m)"
APPLE_ARM_CAPABLE="$(sysctl -in hw.optional.arm64 2>/dev/null || echo 0)"
PROC_TRANSLATED="$(sysctl -in sysctl.proc_translated 2>/dev/null || echo 0)"

if [[ "${APPLE_ARM_CAPABLE}" == "1" ]]; then
  if [[ "${PROC_TRANSLATED}" == "1" ]]; then
    PYTHON_ARCH="x86_64"
  else
    PYTHON_ARCH="arm64"
  fi
else
  PYTHON_ARCH="${HOST_ARCH}"
fi

info "$my_name" "Checking virtualenv: ${VENV_DIR}"
info "$my_name" "Host arch: ${HOST_ARCH}"
info "$my_name" "Apple Silicon capable: ${APPLE_ARM_CAPABLE}"
info "$my_name" "Rosetta translated process: ${PROC_TRANSLATED}"
info "$my_name" "Python runtime arch: ${PYTHON_ARCH}"
info "$my_name" "Python binary: ${PYTHON_BIN_DESC}"

if [[ "${APPLE_ARM_CAPABLE}" == "1" && "${PROC_TRANSLATED}" == "1" ]]; then
  error "$my_name" "Current shell is running under Rosetta translation on Apple Silicon."
  info "$my_name" "Run this validation from a native arm64 terminal session."
  exit 1
fi

if [[ "${APPLE_ARM_CAPABLE}" == "1" && "${PYTHON_ARCH}" == "x86_64" ]]; then
  error "$my_name" "Python runtime is x86_64 on an arm64 host (likely Rosetta shell)."
  info "$my_name" "Open a native arm64 terminal/session and recreate the venv if needed."
  exit 1
fi

PY_VERSION_DIR="$(find "${VENV_DIR}/lib" -maxdepth 1 -mindepth 1 -type d -name 'python*' | LC_ALL=C sort | head -1 | xargs -n1 basename)"
SITE_PACKAGES_DIR="${VENV_DIR}/lib/${PY_VERSION_DIR}/site-packages"

if [[ -z "${PY_VERSION_DIR}" || ! -d "${SITE_PACKAGES_DIR}" ]]; then
  error "$my_name" "site-packages not found at ${SITE_PACKAGES_DIR}"
  exit 2
fi

# Collect all single-arch x86_64 extensions (allow universal binaries containing arm64).
# Note: macOS ships bash 3.2 by default, so avoid bash-4-only `mapfile`.
BAD_EXTENSIONS=()
while IFS= read -r -d '' ext; do
  desc="$(file "$ext")"
  if [[ "$desc" == *"x86_64"* && "$desc" != *"arm64"* ]]; then
    BAD_EXTENSIONS+=("$desc")
  fi
done < <(find "${SITE_PACKAGES_DIR}" -name "*.so" -print0)

if [[ ${#BAD_EXTENSIONS[@]} -eq 0 ]]; then
  success "$my_name" "No single-arch x86_64 native extensions found."
  exit 0
fi

error "$my_name" "Found ${#BAD_EXTENSIONS[@]} single-arch x86_64 native extension(s):"
printf '%s
' "${BAD_EXTENSIONS[@]}"

info "$my_name" "Recommended fix on Apple Silicon:"
info "$my_name" "1) mv venv venv_x86_64_backup_YYYYMMDD"
info "$my_name" "2) scripts/python_arm64.sh --python-bin python3 -m venv venv"
info "$my_name" "3) scripts/python_arm64.sh --python-bin venv/bin/python -m pip install -r dq-api/fastapi/requirements.txt -r dq-api/fastapi/requirements-dev.txt"

exit 1
