#!/usr/bin/env bash
# Purpose: Generate runtime secrets for the stack and write them to tmp/secrets.{env}.env.
#
# What it does:
# - Accepts --env dev|test|prod or --env-file PATH to determine environment.
# - Generates random passwords, encryption keys, and tokens.
# - Writes output to tmp/secrets.{env}.env (shell-sourceable).
# - Idempotent: preserves existing secrets unless --force is used.
# - Secrets are NOT committed or baked into Docker images.
#
# Version: 1.0
# Last modified: 2026-07-13

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="generate_secrets.sh"

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

print_usage() {
  printf '%s\n' \
    "Usage: $my_name [OPTIONS]" \
    "" \
    "Options:" \
    "  --env dev|test|prod      Use .env.dev.local, .env.test.local, or .env.prod.local" \
    "  --env-file PATH          Use an explicit env file to derive environment name" \
    "  --force                  Regenerate all secrets even if tmp/secrets.{env}.env exists" \
    "  --reuse-admin            Reuse admin passwords from existing secrets (implies --force)" \
    "  -h, --help               Show this help"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

FORCE=false
REUSE_ADMIN=false
ROOT_ENV_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      if [[ -n "${2:-}" ]]; then
        case "$2" in
          dev|test|prod)
            ROOT_ENV_FILE="$ROOT_DIR/.env.${2}.local"
            shift 2
            ;;
          *)
            error "$my_name" "Invalid env selector: $2 (must be dev, test, or prod)"
            exit 1
            ;;
        esac
      else
        error "$my_name" "--env requires a value (dev, test, or prod)"
        exit 1
      fi
      ;;
    --env-file)
      if [[ -n "${2:-}" ]]; then
        ROOT_ENV_FILE="$2"
        shift 2
      else
        error "$my_name" "--env-file requires a path"
        exit 1
      fi
      ;;
    --force) FORCE=true; shift ;;
    --reuse-admin) REUSE_ADMIN=true; FORCE=true; shift ;;
    -h|--help) print_usage; exit 0 ;;
    *)
      error "$my_name" "Unknown option: $1"
      print_usage
      exit 1
      ;;
  esac
done

# Default to dev if not specified
if [[ -z "$ROOT_ENV_FILE" ]]; then
  ROOT_ENV_FILE="$ROOT_DIR/.env.dev.local"
fi

# Resolve relative paths
if [[ "$ROOT_ENV_FILE" != /* ]]; then
  ROOT_ENV_FILE="$ROOT_DIR/$ROOT_ENV_FILE"
fi

# ---------------------------------------------------------------------------
# Derive environment suffix from ROOT_ENV_FILE
# ---------------------------------------------------------------------------

derive_env_suffix() {
  local env_file="$1"
  local basename
  basename="$(basename "$env_file")"

  # Strip .local suffix
  if [[ "$basename" == *.local ]]; then
    basename="${basename%.local}"
  fi

  # Strip .env prefix
  if [[ "$basename" == .env.* ]]; then
    basename="${basename#.env.}"
  fi

  # Normalize known values
  case "$basename" in
    dev|development) printf 'dev' ;;
    test|testing) printf 'test' ;;
    prod|production) printf 'prod' ;;
    *) printf 'local' ;;
  esac
}

ENV_SUFFIX="$(derive_env_suffix "$ROOT_ENV_FILE")"
SECRETS_FILE="$ROOT_DIR/tmp/secrets.${ENV_SUFFIX}.env"
SECRETS_DIR="$(dirname "$SECRETS_FILE")"

info "$my_name" "Environment suffix: $ENV_SUFFIX"
info "$my_name" "Output file: $SECRETS_FILE"

# Admin password variable names (persisted in stateful volumes, must match DB)
_ADMIN_PASSWORD_VARS=(
  DQ_DB_PASSWORD
  KONG_DB_PASSWORD
  OM_DB_PASSWORD
  OM_DB_ROOT_PASSWORD
  OPENMETADATA_SEARCH_PASSWORD
  ZAMMAD_POSTGRES_PASSWORD
  KEYCLOAK_SYSTEM_ADMIN_PASSWORD
  KEYCLOAK_ADMIN_PASS
)

# Load admin passwords from existing secrets file (--reuse-admin mode)
_admin_passwords_json=""
if [[ "$REUSE_ADMIN" = true ]] && [[ -f "$SECRETS_FILE" ]]; then
  info "$my_name" "--reuse-admin: loading admin passwords from existing $SECRETS_FILE"
  while IFS= read -r line; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "$line" ]] && continue
    _var_name="${line%%=*}"
    _var_value="${line#*=}"
    _var_value="${_var_value#\"}"
    _var_value="${_var_value%\"}"
    for _admin_var in "${_ADMIN_PASSWORD_VARS[@]}"; do
      if [ "$_var_name" = "$_admin_var" ]; then
        _admin_passwords_json="${_admin_passwords_json}${_admin_var}=${_var_value}
"
        break
      fi
    done
  done < "$SECRETS_FILE"
fi

_get_admin_password() {
  local var_name="$1"
  local line
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    local name="${line%%=*}"
    local value="${line#*=}"
    if [ "$name" = "$var_name" ]; then
      printf '%s' "$value"
      return 0
    fi
  done <<<"$_admin_passwords_json"
  return 1
}

# Check if secrets file already exists
if [[ -f "$SECRETS_FILE" ]] && [[ "$FORCE" != true ]]; then
  info "$my_name" "Secrets file already exists: $SECRETS_FILE"
  info "$my_name" "Use --force to regenerate all secrets"

  # Source existing secrets file to verify it's valid
  set -a
  # shellcheck disable=SC1090
  source "$SECRETS_FILE"
  set +a

  info "$my_name" "✓ Existing secrets loaded successfully"
  exit 0
fi

# ---------------------------------------------------------------------------
# Helper: generate random password
# ---------------------------------------------------------------------------

generate_password() {
  openssl rand -base64 24 | tr -dc 'a-zA-Z0-9_-' | head -c 32
}

# ---------------------------------------------------------------------------
# Helper: generate encryption key (Fernet-compatible)
# ---------------------------------------------------------------------------

generate_encryption_key() {
  # Use python_arm64.sh if available, otherwise fall back to openssl
  # Fernet keys must be exactly 32 url-safe base64-encoded bytes (44 chars with padding)
  local python_runner="$ROOT_DIR/scripts/python_arm64.sh"
  local python_bin=""

  # Try to find a python with cryptography module
  if [[ -x "$ROOT_DIR/venv/bin/python" ]]; then
    python_bin="$ROOT_DIR/venv/bin/python"
  elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    python_bin="$ROOT_DIR/.venv/bin/python"
  fi

  if [[ -x "$python_runner" && -n "$python_bin" ]]; then
    "$python_runner" --python-bin "$python_bin" -c "
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
" 2>/dev/null
  elif command -v openssl >/dev/null 2>&1; then
    # Fallback: generate 32 random bytes and base64url encode them
    # The padding '=' is required for Fernet to work
    openssl rand -base64 32 | tr '+/' '-_'
  fi
}

# ---------------------------------------------------------------------------
# Generate secrets
# ---------------------------------------------------------------------------

mkdir -p "$SECRETS_DIR"

# Helper: emit an admin password (reuse if available, else generate new)
_emit_admin_password() {
  local var_name="$1"
  local reused_value
  if reused_value="$(_get_admin_password "$var_name")"; then
    echo "${var_name}=\"${reused_value}\""
  else
    echo "${var_name}=\"$(generate_password)\""
  fi
}

# Start the secrets file with a header
{
  echo "# Auto-generated by generate_secrets.sh"
  echo "# Environment: $ENV_SUFFIX"
  echo "# Generated at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  if [[ "$REUSE_ADMIN" = true ]]; then
    echo "# Mode: --reuse-admin (admin passwords reused from prior secrets)"
  fi
  echo "# Do not commit — regenerated on each startup."
  echo ""
  echo "# ============================================================"
  echo "# Database & Storage Credentials"
  echo "# ============================================================"
  _emit_admin_password DQ_DB_PASSWORD
  _emit_admin_password KONG_DB_PASSWORD
  _emit_admin_password OM_DB_PASSWORD
  _emit_admin_password OM_DB_ROOT_PASSWORD
  _emit_admin_password OPENMETADATA_SEARCH_PASSWORD
  _emit_admin_password ZAMMAD_POSTGRES_PASSWORD
  echo "AISTOR_ROOT_PASSWORD=\"$(generate_password)\""
  echo "DQ_S3_SECRET_KEY=\"$(generate_password)\""
  echo "GX_EXCEPTION_STORAGE_SECRET_KEY=\"$(generate_password)\""
  echo "KONG_ADMIN_PASSWORD=\"$(generate_password)\""
  echo ""
  echo "# ============================================================"
  echo "# Application Secrets"
  echo "# ============================================================"
  echo "APP_CONFIG_ENCRYPTION_KEY=\"$(generate_encryption_key)\""
  echo "AIRFLOW_FAB_CLIENT_SECRET=\"$(generate_password)\""
  echo "DQ_ENGINE_OIDC_CLIENT_SECRET=\"$(generate_password)\""
  echo "GRAFANA_OIDC_SECRET=\"$(generate_password)\""
  echo "OM_AIRFLOW_SECRET_KEY=\"$(generate_password)\""
  echo "CATALOG_OIDC_PASSWORD=\"$(generate_password)\""
  echo "GRAFANA_ADMIN_PASSWORD=\"$(generate_password)\""
  echo ""
  echo "# ============================================================"
  echo "# Keystore/Truststore Passwords"
  echo "# ============================================================"
  echo "KAFKA_TLS_KEYSTORE_PASSWORD=\"$(generate_password)\""
  echo "KEYCLOAK_HTTPS_KEYSTORE_PASSWORD=\"$(generate_password)\""
  _emit_admin_password KEYCLOAK_ADMIN_PASS
  _emit_admin_password KEYCLOAK_SYSTEM_ADMIN_PASSWORD
  echo "KEYCLOAK_USER_PASSWORD=\"$(generate_password)\""
  echo "OPENMETADATA_OIDC_SEED_PASSWORD=\"$(generate_password)\""
  echo ""
  echo "# ============================================================"
  echo "# Seeded User Credentials (initial values, rotated during seed)"
  echo "# ============================================================"
  echo "KEYCLOAK_JACCLOUD_PASSWORD=\"$(generate_password)\""
  echo "SMOKE_LOGIN_PASSWORD=\"$(generate_password)\""
  echo "OPERATOR_LOGIN_PASSWORD=\"$(generate_password)\""
  echo "AUDITOR_LOGIN_PASSWORD=\"$(generate_password)\""
  echo "REGULATOR_LOGIN_PASSWORD=\"$(generate_password)\""
} > "$SECRETS_FILE"

# Restrict permissions on the secrets file
chmod 600 "$SECRETS_FILE"

info "$my_name" "✓ Generated secrets written to $SECRETS_FILE"
info "$my_name" "✓ Permissions set to 600 (owner read/write only)"

# Export the secrets file path for downstream scripts
echo ""
echo "SECRETS_ENV_FILE=$SECRETS_FILE"
