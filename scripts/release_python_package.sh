#!/usr/bin/env bash
set -euo pipefail

# Purpose: Build wheel artifacts for a repo Python package and optionally publish them.
#
# What it does:
# - Resolves one of the repo package release targets in scripts/package-releases.
# - Builds the package wheel into a temporary dist directory.
# - Optionally publishes the wheel to PyPI or a corporate Nexus PyPI endpoint.
#
# Version: 1.2.0
# Last modified: 2026-06-30

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${ROOT_DIR}/scripts/supporting/logging.sh"
source "${ROOT_DIR}/scripts/supporting/root_env_file.sh"

my_name="release_python_package.sh"
PYTHON_RUNNER="${ROOT_DIR}/scripts/python_arm64.sh"
PYTHON_BIN="${ROOT_DIR}/venv/bin/python"

PACKAGE_KEY=""
ALL_PACKAGES="false"
PACKAGE_DIR=""
PACKAGE_LABEL=""
DIST_DIR=""
PUBLISH="${PACKAGE_RELEASE_PUBLISH:-false}"
PRINT_WHEEL_PATH="${PACKAGE_RELEASE_PRINT_WHEEL_PATH:-true}"
REPOSITORY_NAME="${PACKAGE_RELEASE_REPOSITORY:-}"
REPOSITORY_URL="${PACKAGE_RELEASE_REPOSITORY_URL:-}"
WHEEL_PATH=""

ALL_PACKAGE_KEYS=(
  dq-cli
  dq-utils
  dq-domain-validation
  dq-airflow-sdk
  dq-airflow-operator
)

usage() {
  cat <<'EOF'
Usage: scripts/release_python_package.sh [PACKAGE] [OPTIONS]

Packages:
  dq-cli | dq-made-easy-cli | release_dq_made_easy_cli.sh
  dq-utils | dq-made-easy-utils | release_dq_utils.sh
  dq-domain-validation | dq-made-easy-domain-validation | release_dq_domain_validation.sh
  dq-airflow-sdk | dq-made-easy-airflow-sdk | release_dq_airflow_sdk.sh
  dq-airflow-operator | dq-made-easy-airflow-operator | release_dq_airflow_operator.sh

Options:
  --all                  Build and optionally publish every repo package
  --publish              Upload the built wheel after validation
  --repository NAME      Twine repository name to publish to
  --repository-url URL   Twine repository URL to publish to
  --dry-run              Build and validate without uploading
  -h, --help             Show this help

Environment:
  PACKAGE_RELEASE_PUBLISH         Truthy value enables publishing
  PACKAGE_RELEASE_PRINT_WHEEL_PATH Truthy value prints the final wheel path
  PACKAGE_RELEASE_REPOSITORY      Default Twine repository name
  PACKAGE_RELEASE_REPOSITORY_URL  Default Twine repository URL
  NEXUSCLOUD_PYPI_URL             Default corporate Nexus PyPI URL

Env selection:
  --env dev|test|prod      Load .env.dev.local, .env.test.local, or .env.prod.local
  --env-file PATH          Load an explicit env file
EOF
}

truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

require_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    error "$my_name" "Missing required command: $name"
    exit 2
  fi
}

resolve_package() {
  local package_key="$1"

  case "$package_key" in
    dq-cli|dq-made-easy-cli|release_dq_made_easy_cli.sh)
      PACKAGE_DIR="${ROOT_DIR}/dq-cli"
      PACKAGE_LABEL="dq-made-easy-cli"
      ;;
    dq-utils|dq-made-easy-utils|release_dq_utils.sh)
      PACKAGE_DIR="${ROOT_DIR}/dq-utils"
      PACKAGE_LABEL="dq-made-easy-utils"
      ;;
    dq-domain-validation|dq-made-easy-domain-validation|release_dq_domain_validation.sh)
      PACKAGE_DIR="${ROOT_DIR}/dq-domain-validation"
      PACKAGE_LABEL="dq-made-easy-domain-validation"
      ;;
    dq-airflow-sdk|dq-made-easy-airflow-sdk|release_dq_airflow_sdk.sh)
      PACKAGE_DIR="${ROOT_DIR}/dq-airflow-sdk"
      PACKAGE_LABEL="dq-made-easy-airflow-sdk"
      ;;
    dq-airflow-operator|dq-made-easy-airflow-operator|release_dq_airflow_operator.sh)
      PACKAGE_DIR="${ROOT_DIR}/dq-airflow-operator"
      PACKAGE_LABEL="dq-made-easy-airflow-operator"
      ;;
    *)
      error "$my_name" "Unknown package selector: $package_key"
      usage
      exit 2
      ;;
  esac

  DIST_DIR="${ROOT_DIR}/tmp/${PACKAGE_DIR##*/}-release"
}

resolve_publish_target() {
  if [[ -n "$REPOSITORY_URL" ]]; then
    return 0
  fi

  if [[ -n "$REPOSITORY_NAME" ]]; then
    return 0
  fi

  if [[ -n "${NEXUSCLOUD_PYPI_URL:-}" ]]; then
    REPOSITORY_URL="${NEXUSCLOUD_PYPI_URL}"
    return 0
  fi

  REPOSITORY_NAME="pypi"
}

build_package() {
  resolve_package "$1"

  if [[ ! -f "$PACKAGE_DIR/pyproject.toml" ]]; then
    error "$my_name" "Missing package metadata at $PACKAGE_DIR/pyproject.toml"
    exit 1
  fi

  rm -rf "$DIST_DIR"
  mkdir -p "$DIST_DIR"

  info "$my_name" "Building $PACKAGE_LABEL wheel"
  if ! (cd "$PACKAGE_DIR" && "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m pip wheel --no-deps --no-build-isolation --wheel-dir "$DIST_DIR" . >/dev/null); then
    error "$my_name" "Failed to build wheel for $PACKAGE_LABEL"
    exit 1
  fi

  WHEEL_PATH="$(find "$DIST_DIR" -maxdepth 1 -name '*.whl' -print | head -n 1)"
  if [[ -z "$WHEEL_PATH" ]]; then
    error "$my_name" "No wheel artifact was produced for $PACKAGE_LABEL"
    exit 1
  fi

  success "$my_name" "Built $(basename "$WHEEL_PATH")"

  if [[ "$PUBLISH" != "true" ]]; then
    if truthy "$PRINT_WHEEL_PATH"; then
      printf '%s\n' "$WHEEL_PATH"
    fi
    return 0
  fi

  if ! "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m twine --version >/dev/null 2>&1; then
    error "$my_name" "Python twine frontend is required in the repo venv for publishing"
    exit 2
  fi

  resolve_publish_target

  info "$my_name" "Checking wheel metadata before publishing"
  if ! "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m twine check "$WHEEL_PATH" >/dev/null; then
    error "$my_name" "twine check failed for $(basename "$WHEEL_PATH")"
    exit 1
  fi

  if [[ -n "$REPOSITORY_URL" ]]; then
    info "$my_name" "Publishing $PACKAGE_LABEL to configured repository URL"
    if [[ -n "${NEXUSCLOUD_USERNAME:-}" && -n "${NEXUSCLOUD_PASSWORD:-}" ]]; then
      if ! TWINE_REPOSITORY_URL="$REPOSITORY_URL" TWINE_USERNAME="$NEXUSCLOUD_USERNAME" TWINE_PASSWORD="$NEXUSCLOUD_PASSWORD" "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m twine upload --non-interactive "$WHEEL_PATH"; then
        error "$my_name" "Failed to publish $PACKAGE_LABEL to configured repository URL"
        exit 1
      fi
    else
      if ! TWINE_REPOSITORY_URL="$REPOSITORY_URL" "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m twine upload --non-interactive "$WHEEL_PATH"; then
        error "$my_name" "Failed to publish $PACKAGE_LABEL to configured repository URL"
        exit 1
      fi
    fi
  else
    info "$my_name" "Publishing $PACKAGE_LABEL to $REPOSITORY_NAME"
    if ! TWINE_REPOSITORY="$REPOSITORY_NAME" "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m twine upload --non-interactive "$WHEEL_PATH"; then
      error "$my_name" "Failed to publish $PACKAGE_LABEL to $REPOSITORY_NAME"
      exit 1
    fi
  fi

  if truthy "$PRINT_WHEEL_PATH"; then
    printf '%s\n' "$WHEEL_PATH"
  fi
}

init_root_env_file "$ROOT_DIR"

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  usage
  exit 1
fi

set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      ALL_PACKAGES="true"
      shift
      ;;
    --publish)
      PUBLISH="true"
      shift
      ;;
    --repository)
      if [[ $# -lt 2 ]]; then
        error "$my_name" "--repository requires a value"
        usage
        exit 2
      fi
      REPOSITORY_NAME="$2"
      PUBLISH="true"
      shift 2
      ;;
    --repository-url)
      if [[ $# -lt 2 ]]; then
        error "$my_name" "--repository-url requires a value"
        usage
        exit 2
      fi
      REPOSITORY_URL="$2"
      PUBLISH="true"
      shift 2
      ;;
    --dry-run)
      PUBLISH="false"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "$PACKAGE_KEY" ]]; then
        PACKAGE_KEY="$1"
        shift
      else
        error "$my_name" "Unknown argument: $1"
        usage
        exit 2
      fi
      ;;
  esac
done

if ! source_selected_root_env_file; then
  exit 1
fi

PUBLISH="${PACKAGE_RELEASE_PUBLISH:-$PUBLISH}"
PRINT_WHEEL_PATH="${PACKAGE_RELEASE_PRINT_WHEEL_PATH:-$PRINT_WHEEL_PATH}"
REPOSITORY_NAME="${PACKAGE_RELEASE_REPOSITORY:-$REPOSITORY_NAME}"
REPOSITORY_URL="${PACKAGE_RELEASE_REPOSITORY_URL:-$REPOSITORY_URL}"

if [[ "$ALL_PACKAGES" == "true" && -n "$PACKAGE_KEY" ]]; then
  error "$my_name" "--all cannot be combined with a package selector"
  usage
  exit 2
fi

if [[ "$ALL_PACKAGES" != "true" && -z "$PACKAGE_KEY" ]]; then
  error "$my_name" "PACKAGE is required unless --all is set"
  usage
  exit 2
fi

if truthy "${PACKAGE_RELEASE_PUBLISH:-}"; then
  PUBLISH="true"
fi

require_cmd "$PYTHON_RUNNER"
require_cmd "$PYTHON_BIN"

if [[ "$ALL_PACKAGES" == "true" ]]; then
  for PACKAGE_KEY in "${ALL_PACKAGE_KEYS[@]}"; do
    build_package "$PACKAGE_KEY"
  done
else
  build_package "$PACKAGE_KEY"
fi
