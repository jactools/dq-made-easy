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
    "  -h, --help               Show this help"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

FORCE=false
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
  local python_runner="$ROOT_DIR/scripts/python_arm64.sh"
  if [[ -x "$python_runner" ]]; then
    "$python_runner" -c "
import base64, os
print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('='))
" 2>/dev/null || openssl rand -base64 32 | tr -d '\n='
  else
    openssl rand -base64 32 | tr -d '\n='
  fi
}

# ---------------------------------------------------------------------------
# Generate secrets
# ---------------------------------------------------------------------------

mkdir -p "$SECRETS_DIR"

# Start the secrets file with a header
{
  echo "# Auto-generated by generate_secrets.sh"
  echo "# Environment: $ENV_SUFFIX"
  echo "# Generated at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "# Do not commit — regenerated on each startup."
  echo ""
  echo "# ============================================================"
  echo "# Database & Storage Credentials"
  echo "# ============================================================"
  echo "DQ_DB_PASSWORD=\"$(generate_password)\""
  echo "KONG_DB_PASSWORD=\"$(generate_password)\""
  echo "OM_DB_PASSWORD=\"$(generate_password)\""
  echo "OM_DB_ROOT_PASSWORD=\"$(generate_password)\""
  echo "OPENMETADATA_SEARCH_PASSWORD=\"$(generate_password)\""
  echo "ZAMMAD_POSTGRES_PASSWORD=\"$(generate_password)\""
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
  # Keycloak admin password: must be the same for KEYCLOAK_ADMIN_PASS and KEYCLOAK_SYSTEM_ADMIN_PASSWORD
  # KEYCLOAK_ADMIN_PASS is used by the healthcheck, KEYCLOAK_SYSTEM_ADMIN_PASSWORD by the entrypoint
  _KEYCLOAK_ADMIN_PASS="$(generate_password)"
  echo "KEYCLOAK_ADMIN_PASS=\"${_KEYCLOAK_ADMIN_PASS}\""
  echo "KEYCLOAK_SYSTEM_ADMIN_PASSWORD=\"${_KEYCLOAK_ADMIN_PASS}\""
  echo "KEYCLOAK_USER_PASSWORD=\"$(generate_password)\""
  echo "OPENMETADATA_OIDC_SEED_PASSWORD=\"$(generate_password)\""
} > "$SECRETS_FILE"

# Restrict permissions on the secrets file
chmod 600 "$SECRETS_FILE"

info "$my_name" "✓ Generated secrets written to $SECRETS_FILE"
info "$my_name" "✓ Permissions set to 600 (owner read/write only)"

# Export the secrets file path for downstream scripts
echo ""
echo "SECRETS_ENV_FILE=$SECRETS_FILE"
