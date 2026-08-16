#!/usr/bin/env bash
set -euo pipefail

# Purpose: Build wheel artifacts for a repo Python package and optionally publish them.
#
# What it does:
# - Resolves one of the repo package release targets in scripts/package-releases.
# - Builds the package wheel into a temporary dist directory.
# - Optionally publishes the wheel to PyPI or a corporate Nexus PyPI endpoint.
#
# Version: 1.2.1
# Last modified: 2026-07-01

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
BUILD_DIR=""
PUBLIC_DIST_DIR=""
PUBLISH="${PACKAGE_RELEASE_PUBLISH:-false}"
PRINT_WHEEL_PATH="${PACKAGE_RELEASE_PRINT_WHEEL_PATH:-true}"
REPOSITORY_NAME="${PACKAGE_RELEASE_REPOSITORY:-}"
REPOSITORY_URL="${PACKAGE_RELEASE_REPOSITORY_URL:-}"
WHEEL_PATH=""
PACKAGE_VERSION_OVERRIDE=""
PACKAGE_USE_BUILD_ISOLATION="false"
PACKAGE_SKIP_TWINE_CHECK="false"

ALL_PACKAGE_KEYS=(
  dq-cli
  dq-utils
  dq-domain-validation
  dq-airflow-sdk
  dq-airflow-operator
  spark-expectations
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
  spark-expectations | release_spark_expectations.sh

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
  --source local|corporate  Use public PyPI or corporate Nexus for dependency resolution
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

  PACKAGE_VERSION_OVERRIDE=""
  PACKAGE_USE_BUILD_ISOLATION="false"
  PACKAGE_SKIP_TWINE_CHECK="false"

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
    spark-expectations|release_spark_expectations.sh)
      PACKAGE_DIR="${ROOT_DIR}/vendor/spark-expectations-2.10.1"
      PACKAGE_LABEL="spark-expectations"
      PACKAGE_VERSION_OVERRIDE="2.10.1"
      PACKAGE_USE_BUILD_ISOLATION="true"
      PACKAGE_SKIP_TWINE_CHECK="true"
      ;;
    *)
      error "$my_name" "Unknown package selector: $package_key"
      usage
      exit 2
      ;;
  esac

  DIST_DIR="${ROOT_DIR}/tmp/${PACKAGE_DIR##*/}-release"
  PUBLIC_DIST_DIR="${ROOT_DIR}/tmp/${PACKAGE_DIR##*/}-dist"
  BUILD_DIR="${ROOT_DIR}/tmp/${PACKAGE_DIR##*/}-build"
}

apply_package_build_overrides() {
  if [[ -z "$PACKAGE_VERSION_OVERRIDE" ]]; then
    return 0
  fi

  if [[ ! -f "$BUILD_DIR/pyproject.toml" ]]; then
    error "$my_name" "Missing package metadata at $BUILD_DIR/pyproject.toml"
    exit 1
  fi

  perl -0pi -e 's/dynamic = \["version"\]/version = "'"$PACKAGE_VERSION_OVERRIDE"'"/' "$BUILD_DIR/pyproject.toml"
  perl -0pi -e 's/\n\[tool\.hatch\.version\]\nsource = "vcs"\nstyle = "semver"\n/\n/' "$BUILD_DIR/pyproject.toml"
}

resolve_publish_target() {
  if [[ -n "$REPOSITORY_URL" ]]; then
    return 0
  fi

  if [[ -n "$REPOSITORY_NAME" ]]; then
    return 0
  fi

  if [[ -n "${TWINE_REPOSITORY_URL:-}" ]]; then
    REPOSITORY_URL="${TWINE_REPOSITORY_URL}"
    return 0
  fi

  if [[ -n "${NEXUSCLOUD_PYPI_URL:-}" ]]; then
    REPOSITORY_URL="${NEXUSCLOUD_PYPI_URL}"
    return 0
  fi

  REPOSITORY_NAME="pypi"
}

upload_wheel_to_repository_url() {
  local wheel_path="$1"
  local target_url="$2"
  local package_label="$3"
  local twine_output_file="${ROOT_DIR}/tmp/twine-upload-output.log"
  local pypi_container_name="${PYPI_CONTAINER_NAME:-platform-pypi-server}"
  local pypi_storage_dir=""
  local local_pypi_host="${PYPI_BUILD_HOST_DNS:-$(resolve_pypi_build_host || true)}"

  rm -f "$twine_output_file"

  if [[ -n "$local_pypi_host" && "$target_url" == *"://${local_pypi_host}"* ]]; then
    pypi_storage_dir="$(docker inspect "$pypi_container_name" --format '{{range .Mounts}}{{if eq .Destination "/data/packages"}}{{println .Source}}{{end}}{{end}}' 2>/dev/null | head -n 1 | tr -d '\r')"
    if [[ -n "$pypi_storage_dir" && -d "$pypi_storage_dir" ]]; then
      cp "$wheel_path" "$pypi_storage_dir/$(basename "$wheel_path")"
      return 0
    fi
  fi

  # Unset internal CA bundle overrides for twine when publishing to public HTTPS endpoints.
  if TWINE_REPOSITORY_URL="$target_url" TWINE_CERT="" REQUESTS_CA_BUNDLE="" SSL_CERT_FILE="" CURL_CA_BUNDLE="" "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m twine upload --non-interactive "$wheel_path" >"$twine_output_file" 2>&1; then
    return 0
  fi

  cat "$twine_output_file" >&2
  return 1
}

build_package() {
  resolve_package "$1"

  if [[ ! -f "$PACKAGE_DIR/pyproject.toml" ]]; then
    error "$my_name" "Missing package metadata at $PACKAGE_DIR/pyproject.toml"
    exit 1
  fi

  rm -rf "$DIST_DIR"
  rm -rf "$PUBLIC_DIST_DIR"
  rm -rf "$BUILD_DIR"
  mkdir -p "$BUILD_DIR"
  mkdir -p "$DIST_DIR"

  cp -R "$PACKAGE_DIR"/. "$BUILD_DIR"/
  apply_package_build_overrides

  info "$my_name" "Building $PACKAGE_LABEL wheel"
  build_wheel_args=(--no-deps --wheel-dir "$DIST_DIR" .)
  if [[ "$PACKAGE_USE_BUILD_ISOLATION" != "true" ]]; then
    build_wheel_args=(--no-deps --no-build-isolation --wheel-dir "$DIST_DIR" .)
  fi
  if ! (cd "$BUILD_DIR" && "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m pip wheel "${build_wheel_args[@]}" >/dev/null); then
    error "$my_name" "Failed to build wheel for $PACKAGE_LABEL"
    exit 1
  fi

  WHEEL_PATH="$(find "$DIST_DIR" -maxdepth 1 -name '*.whl' -print | head -n 1)"
  if [[ -z "$WHEEL_PATH" ]]; then
    error "$my_name" "No wheel artifact was produced for $PACKAGE_LABEL"
    exit 1
  fi

  success "$my_name" "Built $(basename "$WHEEL_PATH")"

  mkdir -p "$PUBLIC_DIST_DIR"
  cp "$WHEEL_PATH" "$PUBLIC_DIST_DIR/"

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

  if [[ "$PACKAGE_SKIP_TWINE_CHECK" != "true" ]]; then
    info "$my_name" "Checking wheel metadata before publishing"
    if ! "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m twine check "$WHEEL_PATH" >/dev/null; then
      error "$my_name" "twine check failed for $(basename "$WHEEL_PATH")"
      exit 1
    fi
  fi

  if [[ -n "$REPOSITORY_URL" ]]; then
    info "$my_name" "Publishing $PACKAGE_LABEL to configured repository URL"
    if [[ -n "${NEXUSCLOUD_USERNAME:-}" && -n "${NEXUSCLOUD_PASSWORD:-}" ]]; then
      if ! TWINE_USERNAME="$NEXUSCLOUD_USERNAME" TWINE_PASSWORD="$NEXUSCLOUD_PASSWORD" upload_wheel_to_repository_url "$WHEEL_PATH" "$REPOSITORY_URL" "$PACKAGE_LABEL"; then
        error "$my_name" "Failed to publish $PACKAGE_LABEL to configured repository URL"
        exit 1
      fi
    else
      if ! upload_wheel_to_repository_url "$WHEEL_PATH" "$REPOSITORY_URL" "$PACKAGE_LABEL"; then
        error "$my_name" "Failed to publish $PACKAGE_LABEL to configured repository URL"
        exit 1
      fi
    fi
  else
    info "$my_name" "Publishing $PACKAGE_LABEL to $REPOSITORY_NAME"
    if ! TWINE_REPOSITORY="$REPOSITORY_NAME" TWINE_CERT="" REQUESTS_CA_BUNDLE="" SSL_CERT_FILE="" CURL_CA_BUNDLE="" "$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" -m twine upload --skip-existing --non-interactive "$WHEEL_PATH"; then
      error "$my_name" "Failed to publish $PACKAGE_LABEL to $REPOSITORY_NAME"
      exit 1
    fi
  fi

  if truthy "$PRINT_WHEEL_PATH"; then
    printf '%s\n' "$WHEEL_PATH"
  fi

  rm -rf "$BUILD_DIR"
}

init_root_env_file "$ROOT_DIR"

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  usage
  exit 1
fi

  set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

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

source "${ROOT_DIR}/scripts/supporting/setup_env.sh"

LOCAL_MKCERT_CA_FILE="${ROOT_DIR}/certs/mkcert-rootCA.pem"
if [[ -f "${LOCAL_MKCERT_CA_FILE}" ]]; then
  export TWINE_CERT="${LOCAL_MKCERT_CA_FILE}"
  export REQUESTS_CA_BUNDLE="${LOCAL_MKCERT_CA_FILE}"
  export SSL_CERT_FILE="${LOCAL_MKCERT_CA_FILE}"
elif [[ -n "${TLS_INTERNAL_CA_BUNDLE:-}" && -f "${TLS_INTERNAL_CA_BUNDLE}" ]]; then
  export TWINE_CERT="${TLS_INTERNAL_CA_BUNDLE}"
  export REQUESTS_CA_BUNDLE="${TLS_INTERNAL_CA_BUNDLE}"
  export SSL_CERT_FILE="${TLS_INTERNAL_CA_BUNDLE}"
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
