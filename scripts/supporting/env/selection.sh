# Purpose: Implement canonical env selection helpers for shell scripts.
#
# What it does:
# - Resolves dev/test/prod env-file paths and custom env-file paths.
# - Describes the selected env file in user-facing logs.
# - Parses --env and --env-file options into ROOT_ENV_FILE.
# - Validates and sources the selected env file.
#
# Version: 1.0
# Last modified: 2026-05-08

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$REPO_ROOT/scripts/supporting/logging.sh"

env_selector_values() {
  printf '%s' 'dev|test|prod'
}

describe_root_env_file_selection() {
  local root_dir="$1"
  local env_file="$2"

  case "$env_file" in
    "$root_dir/.env.dev.local")
      printf '%s' 'dev (.env.dev.local)'
      ;;
    "$root_dir/.env.test.local")
      printf '%s' 'test (.env.test.local)'
      ;;
    "$root_dir/.env.prod.local")
      printf '%s' 'prod (.env.prod.local)'
      ;;
    *)
      printf 'custom (%s)' "$env_file"
      ;;
  esac
}

resolve_env_file_path() {
  local root_dir="$1"
  local requested_path="$2"

  if [[ "$requested_path" != /* ]]; then
    requested_path="$root_dir/$requested_path"
  fi

  printf '%s' "$requested_path"
}

named_root_env_file_path() {
  local root_dir="$1"
  local selector="$2"

  case "$selector" in
    dev|test|prod)
      printf '%s/.env.%s.local' "$root_dir" "$selector"
      ;;
    *)
      return 1
      ;;
  esac
}

source_runtime_env_dependencies() {
  local selected_root_env_file="${1:-${ROOT_ENV_FILE:-}}"
  local phase="${2:-pre-root}"
  local root_dir=""
  local basename=""
  local env_name=""
  local dependency_file=""
  local dependency_files=()

  if [[ -z "$selected_root_env_file" ]]; then
    return 0
  fi

  if [[ "$selected_root_env_file" != /* ]]; then
    selected_root_env_file="$ROOT_DIR/$selected_root_env_file"
  fi

  root_dir="$(dirname "$selected_root_env_file")"
  basename="$(basename "$selected_root_env_file")"

  if [[ "$basename" == *.local ]]; then
    basename="${basename%.local}"
  fi
  if [[ "$basename" == .env.* ]]; then
    basename="${basename#.env.}"
  fi

  case "$basename" in
    dev|development)
      env_name="dev"
      ;;
    test|testing)
      env_name="test"
      ;;
    prod|production)
      env_name="prod"
      ;;
    *)
      env_name="local"
      ;;
  esac

  case "$phase" in
    pre-root)
      dependency_files=(
        "$root_dir/tmp/secrets.${env_name}.env"
        "$root_dir/tmp/keycloak_seed_user_credentials.${env_name}.env"
      )
      ;;
    post-root)
      dependency_files=(
        "$root_dir/tmp/secrets.${env_name}.env"
        "$root_dir/tmp/keycloak_seed_user_credentials.${env_name}.env"
        "$root_dir/tmp/env_passwords/${env_name}.env"
      )
      ;;
    *)
      dependency_files=()
      ;;
  esac

  for dependency_file in "${dependency_files[@]}"; do
    if [[ -f "$dependency_file" ]]; then
      set -a
      # shellcheck disable=SC1090
      source "$dependency_file"
      set +a
    fi
  done
}

init_root_env_file() {
  local root_dir="$1"
  local default_env_file

  default_env_file="$(named_root_env_file_path "$root_dir" dev)"
  if [ -n "${ROOT_ENV_FILE:-}" ]; then
    ROOT_ENV_FILE="$(resolve_env_file_path "$root_dir" "$ROOT_ENV_FILE")"
  else
    ROOT_ENV_FILE="$default_env_file"
  fi
}

ensure_selected_root_env_file_exists() {
  if [[ ! -f "$ROOT_ENV_FILE" ]]; then
    error "env/selection.sh" "env file not found: $ROOT_ENV_FILE"
    return 1
  fi
}

source_selected_root_env_file() {
  ensure_selected_root_env_file_exists || return 1

  local selected_root_env_file="$ROOT_ENV_FILE"
  source_runtime_env_dependencies "$selected_root_env_file" pre-root
  set -a
  # shellcheck disable=SC1090
  source "$selected_root_env_file"
  set +a
  source_runtime_env_dependencies "$selected_root_env_file" post-root

  ROOT_ENV_FILE="$selected_root_env_file"
  export ROOT_ENV_FILE
}

validate_selected_root_env_file() {
  local root_dir="$1"
  local operation="${2:-full}"

  "$root_dir/scripts/validate_env_file.sh" --env-file "$ROOT_ENV_FILE" --operation "$operation" --quiet
}

consume_root_env_selection_args() {
  local root_dir="$1"
  shift

  ROOT_ENV_SELECTION_REMAINING_ARGS=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --env)
        if [[ $# -lt 2 ]]; then
          error "env/selection.sh" "--env requires one of: $(env_selector_values)"
          return 1
        fi
        if ! ROOT_ENV_FILE="$(named_root_env_file_path "$root_dir" "$2")"; then
          error "env/selection.sh" "unsupported --env value: $2"
          return 1
        fi
        shift 2
        ;;
      --env-file)
        if [[ $# -lt 2 ]]; then
          error "env/selection.sh" "--env-file requires a path"
          return 1
        fi
        ROOT_ENV_FILE="$(resolve_env_file_path "$root_dir" "$2")"
        shift 2
        ;;
      *)
        ROOT_ENV_SELECTION_REMAINING_ARGS+=("$1")
        shift
        ;;
    esac
  done
}
