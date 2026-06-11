#!/usr/bin/env bash

# Apple Silicon safeguard for native-extension wheels in the shared venv.
# Detects x86_64-only .so files and force-reinstalls packages under arm64 when found.

set -euo pipefail

count_non_arm64_native_extensions() {
  local site_packages="$1"
  local count=0

  while IFS= read -r -d '' so_file; do
    local archs=""

    if command -v lipo >/dev/null 2>&1; then
      archs="$(lipo -archs "$so_file" 2>/dev/null || true)"
    fi

    if [[ -n "$archs" ]]; then
      if [[ "$archs" != *"arm64"* ]] && [[ "$archs" != *"arm64e"* ]]; then
        count=$((count + 1))
      fi
      continue
    fi

    # Fallback if lipo is unavailable for some reason.
    local file_output
    file_output="$(file "$so_file" 2>/dev/null || true)"
    if [[ "$file_output" == *"x86_64"* ]] && [[ "$file_output" != *"arm64"* ]]; then
      count=$((count + 1))
    fi
  done < <(find "$site_packages" -name "*.so" -print0)

  echo "$count"
}

ensure_arm64_python_env() {
  local python_bin="${1:-python3}"
  local script_dir
  local repo_root
  local python_runner

  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  repo_root="$(cd "${script_dir}/../../.." && pwd)"
  python_runner="${repo_root}/scripts/python_arm64.sh"

  if [[ "$(uname -s)" != "Darwin" ]]; then
    return 0
  fi

  if ! command -v arch >/dev/null 2>&1; then
    return 0
  fi

  # Use a capability probe instead of uname -m so this still works from Rosetta shells.
  if ! "$python_runner" --python-bin "$python_bin" -c "import sys" >/dev/null 2>&1; then
    return 0
  fi

  local site_packages
  site_packages=$("$python_runner" --python-bin "$python_bin" -c "import sysconfig; print(sysconfig.get_paths().get('platlib',''))")
  if [[ -z "$site_packages" ]] || [[ ! -d "$site_packages" ]]; then
    return 0
  fi

  local mixed_count
  mixed_count="$(count_non_arm64_native_extensions "$site_packages")"

  if [[ "$mixed_count" == "0" ]]; then
    return 0
  fi

  if [[ "${AUTO_FIX_ARM64_VENV:-1}" != "1" ]]; then
    echo "Detected $mixed_count x86_64-only native extensions in $site_packages" >&2
    echo "Set AUTO_FIX_ARM64_VENV=1 to auto-heal, or reinstall the venv under arm64." >&2
    return 1
  fi

  local freeze_file
  freeze_file="$(mktemp -t dq-arm64-reinstall.XXXXXX)"

  echo "Detected $mixed_count x86_64-only native extensions; repairing venv under arm64..." >&2
  "$python_runner" --python-bin "$python_bin" -m pip freeze > "$freeze_file"
  "$python_runner" --python-bin "$python_bin" -m pip install --force-reinstall --no-cache-dir -r "$freeze_file"
  rm -f "$freeze_file"

  mixed_count="$(count_non_arm64_native_extensions "$site_packages")"
  if [[ "$mixed_count" != "0" ]]; then
    echo "Repair did not fully resolve architecture mismatch ($mixed_count files remain)." >&2
    return 1
  fi

  echo "arm64 native extension repair completed." >&2
}
