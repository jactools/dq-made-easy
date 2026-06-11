#!/usr/bin/env bash
set -euo pipefail


# Purpose: Execute Python under arm64 on Apple Silicon (when possible).
#
# What it does:
# - Acts as the required launcher for repository Python commands on Apple Silicon.
# - Resolves the Python executable (default python3 or --python-bin).
# - On macOS arm64-capable machines, runs via `arch -arm64`.
# - Otherwise runs the resolved Python normally.
#
# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="python_arm64.sh"

python_bin="python3"
if [[ "${1:-}" == "--python-bin" ]]; then
  python_bin="${2:-}"
  shift 2
fi

if [[ "$python_bin" == */* ]]; then
  if [[ ! -x "$python_bin" ]]; then
    error "$my_name" "Python executable not found or not executable: $python_bin"
    exit 2
  fi
  resolved_python="$python_bin"
else
  resolved_python="$(command -v "$python_bin" || true)"
  if [[ -z "$resolved_python" ]]; then
    error "$my_name" "Python command not found in PATH: $python_bin"
    exit 2
  fi
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  apple_arm_capable="$(sysctl -in hw.optional.arm64 2>/dev/null || echo 0)"
  if [[ "$apple_arm_capable" == "1" ]]; then
    if ! command -v arch >/dev/null 2>&1; then
      error "$my_name" "'arch' command is required to force arm64 Python execution"
      exit 2
    fi
    if ! arch -arm64 "$resolved_python" -c 'import platform; print(platform.machine())' >/dev/null 2>&1; then
      error "$my_name" "Unable to execute Python under arm64: $resolved_python"
      exit 1
    fi
    exec arch -arm64 "$resolved_python" "$@"
  fi
fi

exec "$resolved_python" "$@"