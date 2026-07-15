#!/usr/bin/env bash
set -euo pipefail

# Purpose: Build, publish, and version-bump the standalone dq-made-easy-cli package.
#
# What it does:
# - Delegates wheel build/publish to scripts/release_python_package.sh.
# - Bumps dq-cli/pyproject.toml to the next patch version after a successful publish.
#
# Version: 1.2.0
# Last modified: 2026-06-30

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
PYTHON_RUNNER="${ROOT_DIR}/scripts/python_arm64.sh"
CLI_DIR="${ROOT_DIR}/dq-cli"
PYPROJECT_FILE="${CLI_DIR}/pyproject.toml"
RELEASE_WRAPPER="${ROOT_DIR}/scripts/release_python_package.sh"
PACKAGE_KEY="dq-cli"
REPOSITORY=""
DRY_RUN="false"

source "${ROOT_DIR}/scripts/package-releases/package_release_versioning.sh"

usage() {
  cat <<'EOF'
Usage: scripts/package-releases/release_dq_made_easy_cli.sh [--repository NAME] [--dry-run]

Options:
  --repository NAME  Twine repository name to publish to (default: pypi)
  --dry-run          Build and check artifacts without uploading or bumping
  -h, --help         Show this help
EOF
}

require_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    printf 'release_dq_made_easy_cli.sh: missing required command: %s\n' "$name" >&2
    exit 2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repository)
      if [[ $# -lt 2 ]]; then
        printf 'release_dq_made_easy_cli.sh: --repository requires a value\n' >&2
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
      printf 'release_dq_made_easy_cli.sh: unknown argument: %s\n' "$1" >&2
      usage
      exit 2
      ;;
  esac
done

require_cmd "$PYTHON_RUNNER"
require_cmd "$PYTHON_BIN"

cd "$CLI_DIR"
CURRENT_VERSION="$(read_version)"

if [[ "$DRY_RUN" == "true" ]]; then
  PACKAGE_RELEASE_PUBLISH=false PACKAGE_RELEASE_PRINT_WHEEL_PATH=false "$RELEASE_WRAPPER" "$PACKAGE_KEY" --dry-run
  printf 'Dry run complete for dq-made-easy-cli %s\n' "$CURRENT_VERSION"
  exit 0
fi

if [[ -n "$REPOSITORY" ]]; then
  PACKAGE_RELEASE_PUBLISH=true PACKAGE_RELEASE_PRINT_WHEEL_PATH=false "$RELEASE_WRAPPER" "$PACKAGE_KEY" --repository "$REPOSITORY"
else
  PACKAGE_RELEASE_PUBLISH=true PACKAGE_RELEASE_PRINT_WHEEL_PATH=false "$RELEASE_WRAPPER" "$PACKAGE_KEY"
fi

NEXT_VERSION="$(bump_patch_version "$CURRENT_VERSION")"
printf 'Bumped dq-cli/pyproject.toml from %s to %s\n' "$CURRENT_VERSION" "$NEXT_VERSION"

"$ROOT_DIR/scripts/package-releases/sync_fastapi_requirements_dev.sh"
