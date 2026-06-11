#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate canonical env files before startup, pull, seed, or stop flows use them.
# What it does:
# - Resolves either a canonical env selector or an explicit env file path.
# - Enforces fail-fast env contract checks for dev/test/prod stages.
# - Supports a reduced stop-mode check so teardown still works with invalid non-stop settings.
# validate: groups=repo
# validate: include=false
# Version: 1.0
# Last modified: 2026-05-13

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
init_root_env_file "$ROOT_DIR"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_env_file.sh"

QUIET=false
OPERATION="full"
EXPECTED_ENVIRONMENT=""

print_usage() {
  printf '%s\n' \
    "Usage: ./scripts/validate_env_file.sh [--env dev|test|prod|--env-file PATH] [OPTIONS]" \
    "" \
    "Canonical env options:" \
    "  --env dev|test|prod      Validate the corresponding .env.<stage>.local file" \
    "  --env-file PATH          Validate an explicit env file" \
    "" \
    "Other options:" \
    "  --operation OP          Validation scope: full or stop (default: full)" \
    "  --quiet                 Suppress success output" \
    "  -h, --help"
}

info() {
  if [[ "$QUIET" != true ]]; then
    printf 'INFO: %s\n' "$1"
  fi
}

pass() {
  if [[ "$QUIET" != true ]]; then
    success "$my_name" "$1"
  fi
}

fail() {
  error "$my_name" "$1"
  exit 1
}

expected_environment_from_selector() {
  case "$1" in
    dev) printf '%s' 'dev' ;;
    test) printf '%s' 'test' ;;
    prod) printf '%s' 'production' ;;
    *) return 1 ;;
  esac
}

infer_expected_environment_from_path() {
  local env_file="$1"
  local base_name

  base_name="$(basename "$env_file")"
  case "$base_name" in
    .env|.env.dev.local)
      printf '%s' 'dev'
      ;;
    .env.test.local)
      printf '%s' 'test'
      ;;
    .env.prod.local|.env.deployment.local|prod.env)
      printf '%s' 'production'
      ;;
    *)
      return 1
      ;;
  esac
}

require_nonempty() {
  local name="$1"
  local value="${!name:-}"

  if [[ -z "$value" ]]; then
    fail "$name is required in $ROOT_ENV_FILE"
  fi
}

validate_supported_environment() {
  case "$1" in
    dev|test|production) return 0 ;;
    *) fail "ENVIRONMENT must be one of: dev, test, production (got: ${1:-<empty>})" ;;
  esac
}

validate_internal_db_url() {
  case "$1" in
    *://db:*|*://db/*|*@db:*|*@db/*) return 0 ;;
    *) fail "DQ_DB_INTERNAL_URL must use the compose service host 'db' (got: $1)" ;;
  esac
}

validate_local_db_url() {
  case "$1" in
    *://db:*|*://db/*|*@db:*|*@db/*)
      fail "DQ_DB_LOCAL_URL must be host-facing and must not use the compose service host 'db' (got: $1)"
      ;;
    *)
      return 0
      ;;
  esac
}

validate_prod_tag() {
  local name="$1"
  local value="${!name:-}"

  if [[ -z "$value" ]]; then
    fail "$name is required for production env validation"
  fi
  if [[ "$value" == "latest" ]]; then
    fail "$name must be pinned for production and may not use 'latest'"
  fi
}

validate_loopback_bind() {
  local name="$1"
  local value="${!name:-}"

  if [[ -z "$value" ]]; then
    fail "$name is required for production env validation"
  fi
  if [[ "$value" != "127.0.0.1" ]]; then
    fail "$name must be 127.0.0.1 for production env validation (got: $value)"
  fi
}

validate_absolute_path() {
  local name="$1"
  local value="${!name:-}"

  if [[ -z "$value" ]]; then
    fail "$name is required for production env validation"
  fi
  case "$value" in
    /*) return 0 ;;
    *) fail "$name must be an absolute path for production env validation (got: $value)" ;;
  esac
}

validate_test_port_diff() {
  local name="$1"
  local dev_default="$2"
  local value="${!name:-}"

  if [[ -z "$value" ]]; then
    fail "$name is required for test env validation"
  fi
  if [[ "$value" == "$dev_default" ]]; then
    fail "$name must differ from the canonical dev port $dev_default for test env validation"
  fi
}

validate_filename() {
  local name="$1"
  local value="${!name:-}"

  if [[ -z "$value" ]]; then
    fail "$name is required in $ROOT_ENV_FILE"
  fi

  case "$value" in
    */*|.*|..)
      fail "$name must be a file name without path separators (got: $value)"
      ;;
  esac
}

run_full_validation() {
  local actual_environment="$1"

  require_nonempty ENVIRONMENT
  require_nonempty DQ_DB_INTERNAL_URL
  require_nonempty DQ_DB_LOCAL_URL
  require_nonempty KONG_PUBLIC_URL
  require_nonempty DQ_LLM_REGISTRY
  require_nonempty DQ_LLM_NAMESPACE
  require_nonempty DQ_LLM_IMAGE
  require_nonempty DQ_LLM_TAG
  require_nonempty DQ_LLM_HOST_BIND
  require_nonempty DQ_LLM_HOST_PORT
  require_nonempty DQ_LLM_MODEL_ID
  require_nonempty DQ_LLM_DEVICE_MAP
  require_nonempty DQ_LLM_MAX_NEW_TOKENS

  validate_internal_db_url "$DQ_DB_INTERNAL_URL"
  validate_local_db_url "$DQ_DB_LOCAL_URL"

  case "$actual_environment" in
    test)
      require_nonempty COMPOSE_PROJECT_NAME
      validate_test_port_diff DB_HOST_PORT 5432
      validate_test_port_diff REDIS_HOST_PORT 6379
      validate_test_port_diff API_HOST_PORT 4010
      validate_test_port_diff FRONTEND_HTTPS_HOST_PORT 5173
      validate_test_port_diff VITE_PORT 5174
      validate_test_port_diff KEYCLOAK_HTTP_HOST_PORT 8080
      validate_test_port_diff KEYCLOAK_HTTPS_HOST_PORT 9444
      validate_test_port_diff KONG_PROXY_HOST_PORT 9443
      validate_test_port_diff KONG_ADMIN_HOST_PORT 8001
      validate_test_port_diff KONG_MANAGER_HOST_PORT 8002
      ;;
    production)
      require_nonempty COMPOSE_PROJECT_NAME
      require_nonempty EDGE_MODE
      if [[ "$EDGE_MODE" != "public" ]]; then
        fail "EDGE_MODE must be public for production env validation (got: $EDGE_MODE)"
      fi

      validate_prod_tag DQ_BASE_TAG
      validate_prod_tag DQ_API_TAG
      validate_prod_tag DQ_ENGINE_TAG
      validate_prod_tag DQ_PROFILING_TAG
      validate_prod_tag DQ_FRONTEND_TAG
      validate_prod_tag DQ_KONG_TAG
      validate_prod_tag DQ_DB_TAG
      validate_prod_tag DQ_KEYCLOAK_TAG
      validate_prod_tag DQ_LLM_TAG

      validate_loopback_bind DB_HOST_BIND
      validate_loopback_bind REDIS_HOST_BIND
      validate_loopback_bind API_HOST_BIND
      validate_loopback_bind FRONTEND_HOST_BIND
      validate_loopback_bind KEYCLOAK_HTTP_HOST_BIND
      validate_loopback_bind KEYCLOAK_HTTPS_HOST_BIND
      validate_loopback_bind KONG_PROXY_HOST_BIND
      validate_loopback_bind KONG_ADMIN_HOST_BIND
      validate_loopback_bind KONG_MANAGER_HOST_BIND
      validate_loopback_bind OPENMETADATA_HOST_BIND
      validate_loopback_bind GRAFANA_HOST_BIND
      validate_loopback_bind OPENMETADATA_DB_HOST_BIND
      validate_loopback_bind OPENMETADATA_SEARCH_HOST_BIND
      validate_loopback_bind OPENMETADATA_INGESTION_HOST_BIND
      validate_loopback_bind LOKI_HOST_BIND
      validate_loopback_bind PROMETHEUS_HOST_BIND
      validate_loopback_bind TEMPO_HOST_BIND
      validate_loopback_bind CONTAINER_METRICS_HOST_BIND
      validate_loopback_bind PUSHGATEWAY_HOST_BIND
      validate_loopback_bind OTEL_GRPC_HOST_BIND
      validate_loopback_bind OTEL_HTTP_HOST_BIND
      validate_loopback_bind OTEL_JAEGER_HOST_BIND
      validate_loopback_bind OTEL_ZIPKIN_HOST_BIND
      validate_loopback_bind AISTOR_API_HOST_BIND
      validate_loopback_bind AISTOR_CONSOLE_HOST_BIND
      validate_loopback_bind ZAMMAD_HOST_BIND

      require_nonempty EDGE_SSL_CERTS_DIR
      validate_filename EDGE_SSL_CERT_FILE_NAME
      validate_filename EDGE_SSL_KEY_FILE_NAME
      ;;
  esac
}

run_stop_validation() {
  local actual_environment="$1"

  require_nonempty ENVIRONMENT
  validate_supported_environment "$actual_environment"

  case "$actual_environment" in
    test|production)
      require_nonempty COMPOSE_PROJECT_NAME
      ;;
  esac
}

if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  print_usage
  exit 1
fi

set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quiet)
      QUIET=true
      shift
      ;;
    --operation)
      if [[ $# -lt 2 ]]; then
        fail "--operation requires one of: full, stop"
      fi
      OPERATION="$2"
      shift 2
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

case "$OPERATION" in
  full|stop) ;;
  *) fail "Unsupported --operation value: $OPERATION" ;;
esac

if [[ ! -f "$ROOT_ENV_FILE" ]]; then
  fail "Env file not found: $ROOT_ENV_FILE"
fi

EXPECTED_ENVIRONMENT="$(infer_expected_environment_from_path "$ROOT_ENV_FILE" || true)"

set -a
# shellcheck disable=SC1090
source "$ROOT_ENV_FILE"
set +a

ACTUAL_ENVIRONMENT="${ENVIRONMENT:-}"
validate_supported_environment "$ACTUAL_ENVIRONMENT"

if [[ -n "$EXPECTED_ENVIRONMENT" && "$ACTUAL_ENVIRONMENT" != "$EXPECTED_ENVIRONMENT" ]]; then
  fail "ENVIRONMENT=$ACTUAL_ENVIRONMENT does not match the selected env file stage ($EXPECTED_ENVIRONMENT)"
fi

case "$OPERATION" in
  stop)
    run_stop_validation "$ACTUAL_ENVIRONMENT"
    pass "env file is valid for stop flow: $ROOT_ENV_FILE"
    ;;
  full)
    run_full_validation "$ACTUAL_ENVIRONMENT"
    pass "env file is valid: $ROOT_ENV_FILE"
    ;;
esac