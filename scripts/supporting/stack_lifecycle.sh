#!/usr/bin/env bash
# Purpose: Shared helpers for stack lifecycle scripts (start/stop/restart/destroy/seed).
#
# What it does:
# - Classifies env variables into admin vs service/user password buckets.
# - Detects whether stateful volumes exist for the current project.
# - Provides volume management primitives (list, remove, check existence).
#
# Version: 1.0
# Last modified: 2026-07-14

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/logging.sh"
source "$SCRIPT_DIR/compose/invocation.sh"

# ---------------------------------------------------------------------------
# Admin password variable names
# These passwords are persisted inside stateful volumes (databases, Keycloak).
# They MUST NOT change unless the volume is destroyed first.
# ---------------------------------------------------------------------------
ADMIN_PASSWORD_VARS=(
  DQ_DB_PASSWORD
  KONG_DB_PASSWORD
  OM_DB_PASSWORD
  OM_DB_ROOT_PASSWORD
  OPENMETADATA_SEARCH_PASSWORD
  ZAMMAD_POSTGRES_PASSWORD
  KEYCLOAK_SYSTEM_ADMIN_PASSWORD
  KEYCLOAK_ADMIN_PASS
)

is_admin_password_var() {
  local var_name="$1"
  local admin_var=""
  for admin_var in "${ADMIN_PASSWORD_VARS[@]}"; do
    if [ "$var_name" = "$admin_var" ]; then
      return 0
    fi
  done
  return 1
}

# ---------------------------------------------------------------------------
# Stateful volume names
# These volumes hold data that embeds admin passwords.
# ---------------------------------------------------------------------------
STATEFUL_VOLUME_NAMES=(
  keycloak_data
  pgdata_v18
  kong-db-data-v17
  openmetadata_pgdata_v18
  zammad_postgresql_data
  openmetadata_search_data
  openmetadata_search_v9_data
)

# ---------------------------------------------------------------------------
# Volume helpers
# ---------------------------------------------------------------------------

_get_project_prefix() {
  # Derive the compose project prefix from ROOT_ENV_FILE
  local env_file="${ROOT_ENV_FILE:-}"
  local project_name="${COMPOSE_PROJECT_NAME:-}"

  # If COMPOSE_PROJECT_NAME is set, use it directly
  if [ -n "$project_name" ]; then
    printf '%s' "$project_name"
    return 0
  fi

  # Fall back to deriving from env file name: .env.dev.local -> dq-made-easy-dev
  local basename=""
  if [ -n "$env_file" ]; then
    basename="$(basename "$env_file")"
    basename="${basename%.local}"
    basename="${basename#.env.}"
    if [ -z "$basename" ]; then
      basename="local"
    fi
    printf '%s' "dq-made-easy-${basename}"
    return 0
  fi

  printf '%s' "dq-made-easy-dev"
}

_list_stateful_volumes() {
  local prefix
  prefix="$(_get_project_prefix)"
  local vol_name=""
  for vol_name in "${STATEFUL_VOLUME_NAMES[@]}"; do
    docker volume ls -q --filter "name=${prefix}_${vol_name}$" 2>/dev/null || true
  done
}

# Returns 0 if at least one stateful volume exists
stateful_volumes_exist() {
  local volumes
  volumes="$(_list_stateful_volumes)"
  [ -n "$volumes" ]
}

# Remove all stateful volumes for the current project
remove_stateful_volumes() {
  local prefix
  prefix="$(_get_project_prefix)"
  local vol_name=""
  local removed=0

  for vol_name in "${STATEFUL_VOLUME_NAMES[@]}"; do
    local full_name="${prefix}_${vol_name}"
    if docker volume ls -q --filter "name=${full_name}$" 2>/dev/null | grep -q .; then
      info "stack_lifecycle" "Removing stateful volume: $full_name"
      docker volume rm "$full_name" 2>/dev/null || {
        # Volume may be in use by a running container; try with force
        warning "stack_lifecycle" "Could not remove $full_name (may be in use)"
      }
      removed=$((removed + 1))
    fi
  done

  if [ "$removed" -eq 0 ]; then
    info "stack_lifecycle" "No stateful volumes found to remove"
  else
    info "stack_lifecycle" "Removed $removed stateful volume(s)"
  fi
}

# Remove only the main Postgres (pgdata_v18) volume
remove_compose_postgres_volume() {
  local prefix
  prefix="$(_get_project_prefix)"
  local vol_name="${prefix}_pgdata_v18"

  if ! docker volume ls -q --filter "name=${vol_name}$" 2>/dev/null | grep -q .; then
    info "stack_lifecycle" "Postgres volume $vol_name does not exist (fresh)"
    return 0
  fi

  # Stop the db container so the volume can be removed
  local db_container
  db_container="$(docker ps -q --filter name=dq-made-easy-db 2>/dev/null || true)"
  if [ -n "$db_container" ]; then
    info "stack_lifecycle" "Stopping db container before removing volume"
    docker stop "$db_container" 2>/dev/null || true
    docker rm "$db_container" 2>/dev/null || true
  fi

  info "stack_lifecycle" "Removing Postgres volume: $vol_name"
  if docker volume rm "$vol_name" 2>/dev/null; then
    info "stack_lifecycle" "Removed $vol_name"
    return 0
  fi

  # Volume may still be in use; try with --force
  warning "stack_lifecycle" "Could not remove $vol_name normally, trying with force"
  if docker volume rm -f "$vol_name" 2>/dev/null; then
    info "stack_lifecycle" "Force-removed $vol_name"
    return 0
  fi

  error "stack_lifecycle" "Failed to remove Postgres volume $vol_name (may be in use by another container)"
  return 1
}

# ---------------------------------------------------------------------------
# Generated artifact cleanup
# ---------------------------------------------------------------------------

_derive_env_suffix() {
  local env_file="${1:-$ROOT_ENV_FILE}"
  local basename=""
  if [ -z "$env_file" ]; then
    printf '%s' "dev"
    return
  fi
  basename="$(basename "$env_file")"
  basename="${basename%.local}"
  basename="${basename#.env.}"
  case "$basename" in
    dev|development) printf 'dev' ;;
    test|testing) printf 'test' ;;
    prod|production) printf 'prod' ;;
    *) printf 'local' ;;
  esac
}

remove_generated_artifacts() {
  local env_suffix
  env_suffix="$(_derive_env_suffix "$1")"
  local root_dir="${2:-$ROOT_DIR}"

  info "stack_lifecycle" "Removing generated artifacts for env=$env_suffix"

  # Secrets file
  local secrets_file="$root_dir/tmp/secrets.${env_suffix}.env"
  if [ -f "$secrets_file" ]; then
    rm -f "$secrets_file"
    info "stack_lifecycle" "Removed $secrets_file"
  fi

  # Rotated env file
  local passwords_dir="$root_dir/tmp/env_passwords"
  if [ -f "$passwords_dir/${env_suffix}.env" ]; then
    rm -f "$passwords_dir/${env_suffix}.env"
    info "stack_lifecycle" "Removed $passwords_dir/${env_suffix}.env"
  fi

  # Keycloak seed credentials
  local kc_csv="$root_dir/tmp/keycloak_seed_user_credentials.${env_suffix}.csv"
  local kc_env="$root_dir/tmp/keycloak_seed_user_credentials.${env_suffix}.env"
  [ -f "$kc_csv" ] && rm -f "$kc_csv"
  [ -f "$kc_env" ] && rm -f "$kc_env"

  # TLS certs
  local certs_dir="$root_dir/tmp/certs"
  if [ -d "$certs_dir" ]; then
    rm -rf "$certs_dir"
    info "stack_lifecycle" "Removed $certs_dir"
  fi
}

# ---------------------------------------------------------------------------
# Env preparation: load secrets and rotated passwords into the environment
# ---------------------------------------------------------------------------

load_generated_env() {
  local env_file="${1:-$ROOT_ENV_FILE}"
  local root_dir="${2:-$ROOT_DIR}"
  local env_suffix
  env_suffix="$(_derive_env_suffix "$env_file")"

  # Load secrets
  local secrets_file="$root_dir/tmp/secrets.${env_suffix}.env"
  if [ -f "$secrets_file" ]; then
    info "stack_lifecycle" "Loading secrets from $secrets_file"
    set -a
    # shellcheck disable=SC1090
    source "$secrets_file"
    set +a
  else
    warning "stack_lifecycle" "No secrets file found at $secrets_file"
  fi

  # Load rotated env passwords
  local passwords_file="$root_dir/tmp/env_passwords/${env_suffix}.env"
  if [ -f "$passwords_file" ]; then
    info "stack_lifecycle" "Loading rotated passwords from $passwords_file"
    set -a
    # shellcheck disable=SC1090
    source "$passwords_file"
    set +a
  fi

  # Load keycloak seed credentials
  local kc_env="$root_dir/tmp/keycloak_seed_user_credentials.${env_suffix}.env"
  if [ -f "$kc_env" ]; then
    info "stack_lifecycle" "Loading Keycloak credentials from $kc_env"
    set -a
    # shellcheck disable=SC1090
    source "$kc_env"
    set +a
  fi
}
