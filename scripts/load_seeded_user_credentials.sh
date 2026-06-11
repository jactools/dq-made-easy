#!/usr/bin/env bash
set -euo pipefail

# Purpose: Load generated seeded-user credentials for the selected stack environment.
# What it does:
# - Resolves the canonical root env file using the shared --env/--env-file selector.
# - Sources the selected root env file so downstream scripts inherit stack URLs and client ids.
# - Sources the matching tmp/keycloak_seed_user_credentials.<stage>.env file.
# Version: 1.0
# Last modified: 2026-05-01

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
my_name="load_seeded_user_credentials.sh"

dq_usage() {
  cat <<'EOF'
Usage:
  source scripts/load_seeded_user_credentials.sh [--env dev|test|prod|--env-file PATH] [--quiet]

Examples:
  source scripts/load_seeded_user_credentials.sh --env test
  source scripts/load_seeded_user_credentials.sh --env-file .env.prod.local --quiet
EOF
}

dq_normalize_stage() {
  local value="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    dev|development)
      printf '%s' 'dev'
      ;;
    test|testing)
      printf '%s' 'test'
      ;;
    prod|production)
      printf '%s' 'prod'
      ;;
    *)
      case "$ROOT_ENV_FILE" in
        "$ROOT_DIR/.env.dev.local")
          printf '%s' 'dev'
          ;;
        "$ROOT_DIR/.env.test.local")
          printf '%s' 'test'
          ;;
        "$ROOT_DIR/.env.prod.local")
          printf '%s' 'prod'
          ;;
        *)
          printf '%s' ''
          ;;
      esac
      ;;
  esac
}

dq_decode_seeded_credential_value() {
  local value="$1"

  case "$value" in
    "'"*"'")
      value="${value#\'}"
      value="${value%\'}"
      ;;
    '"'*'"')
      value="${value#\"}"
      value="${value%\"}"
      value="${value//\\\"/\"}"
      value="${value//\\\\/\\}"
      ;;
  esac

  printf '%s' "$value"
}

dq_load_seeded_credentials_env_file() {
  local credentials_env_file="$1"
  local line key value decoded_value

  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in
      ''|'#'*)
        continue
        ;;
    esac

    case "$line" in
      *=*) ;;
      *)
        error "$my_name" "invalid seeded credential line in $credentials_env_file"
        return 1
        ;;
    esac

    key="${line%%=*}"
    value="${line#*=}"
    case "$key" in
      KEYCLOAK_JACCLOUD_USERNAME|KEYCLOAK_JACCLOUD_PASSWORD|SMOKE_LOGIN_EMAIL|SMOKE_LOGIN_PASSWORD|OPERATOR_LOGIN_EMAIL|OPERATOR_LOGIN_PASSWORD|AUDITOR_LOGIN_EMAIL|AUDITOR_LOGIN_PASSWORD|REGULATOR_LOGIN_EMAIL|REGULATOR_LOGIN_PASSWORD) ;;
      *)
        error "$my_name" "unsupported seeded credential key in $credentials_env_file: $key"
        return 1
        ;;
    esac

    decoded_value="$(dq_decode_seeded_credential_value "$value")"
    export "$key=$decoded_value"
  done < "$credentials_env_file"
}

dq_load_seeded_user_credentials_main() {
  local quiet="false"
  local credentials_env_file=""
  local stage=""

  init_root_env_file "$ROOT_DIR"

  if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
    return 1
  fi
  set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --quiet)
        quiet="true"
        shift
        ;;
      -h|--help)
        dq_usage
        return 0
        ;;
      *)
        error "$my_name" "unsupported argument: $1"
        dq_usage >&2
        return 2
        ;;
    esac
  done

  if ! source_selected_root_env_file; then
    return 1
  fi

  stage="$(dq_normalize_stage "${ENVIRONMENT:-}")"
  if [[ -n "$stage" ]]; then
    credentials_env_file="$ROOT_DIR/tmp/keycloak_seed_user_credentials.${stage}.env"
  fi

  if [[ ! -f "$credentials_env_file" ]]; then
    error "$my_name" "seeded credential file not found: $credentials_env_file"
    error "$my_name" "Run the seed-artifacts flow for the selected environment first."
    return 1
  fi

  if ! dq_load_seeded_credentials_env_file "$credentials_env_file"; then
    return 1
  fi

  export OPENMETADATA_OIDC_SEED_USERNAME="${SMOKE_LOGIN_EMAIL:-${KEYCLOAK_JACCLOUD_USERNAME:-}}"
  export OPENMETADATA_OIDC_SEED_PASSWORD="${SMOKE_LOGIN_PASSWORD:-${KEYCLOAK_JACCLOUD_PASSWORD:-}}"
  export DQ_AIRFLOW_USERNAME="${OPERATOR_LOGIN_EMAIL:-${DQ_AIRFLOW_USERNAME:-}}"
  export DQ_AIRFLOW_PASSWORD="${OPERATOR_LOGIN_PASSWORD:-${DQ_AIRFLOW_PASSWORD:-}}"
  export DQ_SEEDED_CREDENTIALS_ENV_FILE="$credentials_env_file"

  if [[ "$quiet" != "true" ]]; then
    info "$my_name" "Loaded seeded user credentials from $credentials_env_file"
    info "$my_name" "Environment selection: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE") -> $ROOT_ENV_FILE"
  fi
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  dq_load_seeded_user_credentials_main "$@"
else
  error "$my_name" "this script must be sourced so it can export credentials into the current shell"
  error "$my_name" "Example: source scripts/load_seeded_user_credentials.sh --env test"
  exit 2
fi