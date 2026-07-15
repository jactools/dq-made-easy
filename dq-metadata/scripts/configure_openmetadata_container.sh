#!/usr/bin/env bash
set -euo pipefail

# configure_openmetadata_container.sh
# In-container version of OpenMetadata post-start configuration and seeding.
#
# Runs inside the openmetadata-configure Docker container on the internal
# Docker network.  Does NOT require the git repository or docker-compose on
# the host.
#
# Usage:
#   configure_openmetadata_container.sh [--seed-all] [--skip-configure]
#
# All configuration is supplied via environment variables (see docker-compose).
# SEED_ALL=true is equivalent to --seed-all.

# ROOT_DIR follows the same convention as the host scripts:
# this script lives two directory levels inside ROOT_DIR so that
# sync_dq_db_with_openmetadata.sh (which computes ROOT_DIR identically)
# resolves all sibling paths correctly.
#   /opt/dq-metadata/scripts/configure_openmetadata_container.sh
#     → ROOT_DIR = /opt
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPTS_DIR="$ROOT_DIR/dq-metadata/scripts"

RUN_CONFIGURE=true
RUN_SEED_ALL="${SEED_ALL:-false}"

# Internal Docker-network addresses (never the host-facing localhost/keycloak.local).
# Compose resolves these service names on the shared Docker network.
OM_DB_HOST="${OM_DB_HOST:-openmetadata-db}"
OM_SERVER_HOST="${OM_SERVER_HOST:-openmetadata-server}"
OM_SERVER_PORT="${OM_SERVER_PORT:-8585}"
OM_BASE_PATH="${OPENMETADATA_BASE_PATH:-/}"

openmetadata_base_path_prefix() {
  if [ "$OM_BASE_PATH" = "/" ]; then
    printf ''
    return 0
  fi

  printf '%s' "$OM_BASE_PATH"
}

resolve_openmetadata_login_email() {
  # Prefer mounted seed credentials file (fresh from keycloak-seed-artifacts)
  # over env var (which may be stale from a previous startup run).
  local seed_creds_file="/etc/openmetadata/seed-credentials.env"
  local seed_username=""
  if [ -f "$seed_creds_file" ]; then
    seed_username="$(grep '^SMOKE_LOGIN_EMAIL=' "$seed_creds_file" 2>/dev/null | cut -d= -f2- || true)"
  fi
  # Fallback to env var if file not available
  if [ -z "$seed_username" ]; then
    seed_username="${OPENMETADATA_OIDC_SEED_USERNAME:-}"
  fi

  if [ -n "$seed_username" ]; then
    printf '%s\n' "$seed_username"
    return 0
  fi

  echo "ERROR: OPENMETADATA_OIDC_SEED_USERNAME is required and not found in seed credentials" >&2
  return 1
}

resolve_openmetadata_seed_password() {
  # Prefer mounted seed credentials file (fresh from keycloak-seed-artifacts)
  # over env var (which may be stale from a previous startup run).
  local seed_creds_file="/etc/openmetadata/seed-credentials.env"
  local seed_password=""
  if [ -f "$seed_creds_file" ]; then
    seed_password="$(grep '^SMOKE_LOGIN_PASSWORD=' "$seed_creds_file" 2>/dev/null | cut -d= -f2- || true)"
  fi
  # Fallback to env var if file not available
  if [ -z "$seed_password" ]; then
    seed_password="${OPENMETADATA_OIDC_SEED_PASSWORD:-}"
  fi

  if [ -n "$seed_password" ]; then
    printf '%s' "$seed_password"
    return 0
  fi

  echo "ERROR: OPENMETADATA_OIDC_SEED_PASSWORD is required and not found in seed credentials" >&2
  return 1
}

resolve_openmetadata_oidc_issuer() {
  local issuer="${SSO_INTERNAL_ISSUER_URL:-${SSO_INTERNAL_ISSUER:-${KEYCLOAK_INTERNAL_URL:-}}}"
  if [ -z "$issuer" ]; then
    issuer="${OM_AUTHENTICATION_AUTHORITY:-${OM_AUTHENTICATION_DISCOVERY_URI:-}}"
  fi

  if [ -z "$issuer" ]; then
    echo "ERROR: Unable to resolve the OpenMetadata OIDC issuer; set SSO_INTERNAL_ISSUER_URL or OM_AUTHENTICATION_AUTHORITY" >&2
    return 1
  fi

  issuer="${issuer%/}"
  case "$issuer" in
    */.well-known/openid-configuration)
      issuer="${issuer%/.well-known/openid-configuration}"
      ;;
    */protocol/openid-connect/token)
      issuer="${issuer%/protocol/openid-connect/token}"
      ;;
    */protocol/openid-connect/certs)
      issuer="${issuer%/protocol/openid-connect/certs}"
      ;;
  esac

  if [ "$issuer" = "http://keycloak:8080" ] || [ "$issuer" = "https://keycloak.jac.dot:9444" ]; then
    issuer="${issuer}/realms/jaccloud"
  fi

  printf '%s\n' "$issuer"
}

resolve_openmetadata_password_b64() {
  local seed_password
  seed_password="$(resolve_openmetadata_seed_password)" || return 1
  printf '%s' "$seed_password" | base64 | tr -d '\n'
}

normalize_pg_sslmode() {
  case "${1:-DISABLED}" in
    DISABLED|disabled|disable)
      printf '%s\n' disable
      ;;
    ALLOW|allow)
      printf '%s\n' allow
      ;;
    PREFER|prefer)
      printf '%s\n' prefer
      ;;
    REQUIRE|require)
      printf '%s\n' require
      ;;
    VERIFY-CA|verify-ca|VERIFY_CA|verify_ca)
      printf '%s\n' verify-ca
      ;;
    VERIFY-FULL|verify-full|VERIFY_FULL|verify_full)
      printf '%s\n' verify-full
      ;;
    *)
      echo "Unsupported PostgreSQL SSL mode: ${1:-}" >&2
      return 1
      ;;
  esac
}

build_sql_string_list() {
  local raw_list="$1"
  local trimmed_list="${raw_list#\[}"
  trimmed_list="${trimmed_list%\]}"
  local old_ifs="$IFS"
  local item
  local result=""

  IFS=','
  for item in $trimmed_list; do
    item="$(printf '%s' "$item" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
    if [ -z "$item" ]; then
      continue
    fi
    if [ -n "$result" ]; then
      result="${result},"
    fi
    result="${result}'${item}'"
  done
  IFS="$old_ifs"

  printf '%s' "$result"
}

# ---------------------------------------------------------------------------
configure_openmetadata_auth_settings() {
  local om_db_user="${OM_DB_USER:-openmetadata_user}"
  local om_db_password="${OM_DB_PASSWORD:-openmetadata_pass}"
  local om_db_name="${OM_DB_NAME:-openmetadata_db}"
  local om_db_ssl_mode="${OM_DB_SSL_MODE:-DISABLED}"
  local keys_sql

  local om_provider="${OM_AUTHENTICATION_PROVIDER:-custom-oidc}"
  local om_provider_name="${OM_OIDC_PROVIDER_NAME:-Keycloak}"
  local om_authority
  local om_client_id="${OM_AUTHENTICATION_CLIENT_ID:-openmetadata}"
  local om_callback_url="${OM_AUTHENTICATION_CALLBACK_URL:-https://openmetadata.jac.dot:8585/callback}"
  local om_discovery_uri="${OM_AUTHENTICATION_DISCOVERY_URI:-}"
  local om_public_keys="${OM_AUTHENTICATION_PUBLIC_KEYS:-}"
  local om_enable_auto_redirect="${OM_ENABLE_AUTO_REDIRECT:-false}"
  local om_server_url="${OM_AUTHENTICATION_SERVER_URL:-${om_callback_url%/callback}}"

  om_authority="$(resolve_openmetadata_oidc_issuer)" || return 1
  if [ -z "$om_discovery_uri" ]; then
    om_discovery_uri="${om_authority}/.well-known/openid-configuration"
  fi
  if [ -z "$om_public_keys" ]; then
    om_public_keys="[${om_authority}/protocol/openid-connect/certs,https://openmetadata-server:8585$(openmetadata_base_path_prefix)/api/v1/system/config/jwks]"
  fi

  om_db_ssl_mode="$(normalize_pg_sslmode "$om_db_ssl_mode")"
  keys_sql="$(build_sql_string_list "$om_public_keys")"

  echo "Configuring OpenMetadata authentication settings in database..."
  # Connect directly to the PostgreSQL service on the Docker network.
  PGPASSWORD="$om_db_password" PGSSLMODE="$om_db_ssl_mode" \
    psql -h "$OM_DB_HOST" -U "$om_db_user" -d "$om_db_name" -v ON_ERROR_STOP=1 <<SQL
UPDATE openmetadata_settings
SET json = COALESCE(json, '{}'::jsonb) || jsonb_build_object(
  'provider', '${om_provider}',
  'providerName', '${om_provider_name}',
  'authority', '${om_authority}',
  'clientId', '${om_client_id}',
  'callbackUrl', '${om_callback_url}',
  'publicKeyUrls', jsonb_build_array(${keys_sql}),
  'enableAutoRedirect', '${om_enable_auto_redirect}'::boolean,
  'responseType', 'code',
  'oidcConfiguration', COALESCE(json->'oidcConfiguration', '{}'::jsonb) || jsonb_build_object(
    'id', '${om_client_id}',
    'type', 'keycloak',
    'discoveryUri', '${om_discovery_uri}',
    'callbackUrl', '${om_callback_url}',
    'serverUrl', '${om_server_url}',
    'responseType', 'code',
    'disablePkce', false
  )
)
WHERE configType = 'authenticationConfiguration';

UPDATE user_entity
SET json = jsonb_set(
  json,
  '{email}',
  to_jsonb(replace(json->>'email', '@dqprototype.example', '@jaccloud.nl')),
  true
)
WHERE isBot IS NOT TRUE
  AND deleted IS NOT TRUE
  AND json->>'email' LIKE '%@dqprototype.example';

UPDATE user_entity
SET json = jsonb_set(
  json,
  '{email}',
  to_jsonb(replace(json->>'email', '@dqprototype.com', '@jaccloud.nl')),
  true
)
WHERE isBot IS NOT TRUE
  AND deleted IS NOT TRUE
  AND json->>'email' LIKE '%@dqprototype.com';
SQL

  echo "OpenMetadata authentication settings updated. Restarting dq-made-easy-openmetadata-server to apply changes..."

  # Restart the server container via the Docker socket.  The filter uses the
  # compose service label so it works regardless of the project name prefix.
  local server_container
  server_container="$(docker ps \
    --filter 'label=com.docker.compose.service=openmetadata-server' \
    --format '{{.ID}}' | head -1)"
  if [ -n "$server_container" ]; then
    docker restart "$server_container" >/dev/null
  else
    echo "Warning: could not find openmetadata-server container to restart; the DB changes are persisted but a manual restart may be needed."
  fi

  local om_api_url="https://${OM_SERVER_HOST}:${OM_SERVER_PORT}$(openmetadata_base_path_prefix)/api/v1/system/version"
  for i in $(seq 1 40); do
    if curl -kfsS "$om_api_url" >/dev/null 2>&1; then
      echo "OpenMetadata API is ready with refreshed authentication settings."
      return 0
    fi
    sleep 3
  done

  echo "OpenMetadata API did not become ready after authentication settings update."
  return 1
}

# ---------------------------------------------------------------------------
prepare_openmetadata_access_token() {
  local om_provider="${OM_AUTHENTICATION_PROVIDER:-custom-oidc}"
  local om_client_id="${OM_AUTHENTICATION_CLIENT_ID:-openmetadata}"
  local seed_username
  local seed_password
  local python_runner="$ROOT_DIR/scripts/python_arm64.sh"
  local token_endpoint
  local om_probe_code
  local kc_realm_url

  if [ "$om_provider" != "custom-oidc" ]; then
    return 0
  fi

  # If OM_TOKEN was pre-set (e.g. by the host script via compose env), use it directly.
  if [ -n "${OM_TOKEN:-}" ]; then
    echo "Using preconfigured OM_TOKEN for OpenMetadata automation."
    return 0
  fi

  kc_realm_url="$(resolve_openmetadata_oidc_issuer)" || return 1
  token_endpoint="${kc_realm_url}/protocol/openid-connect/token"

  local realm_probe_code
  local ca_bundle="/etc/openmetadata/certs/internal-ca-bundle.pem"
  if [ ! -f "$ca_bundle" ]; then
    ca_bundle="/etc/openmetadata/certs/mkcert-rootCA.pem"
  fi
  echo "Waiting for Keycloak realm at ${kc_realm_url}..."
  for i in $(seq 1 20); do
    realm_probe_code="$(curl -s --cacert "$ca_bundle" -o /dev/null -w '%{http_code}' \
      "${kc_realm_url}/.well-known/openid-configuration" || true)"
    if [ "$realm_probe_code" = "200" ]; then
      break
    fi
    sleep 3
  done

  if [ "$realm_probe_code" != "200" ]; then
    echo "ERROR: Keycloak realm not reachable at ${kc_realm_url} (HTTP $realm_probe_code); refusing OpenMetadata local-login fallback." >&2
    return 1
  fi

  # Try client credentials grant first (openmetadata-admin service account).
  local om_admin_client_id="${OM_ADMIN_CLIENT_ID:-openmetadata-admin}"
  local om_admin_client_secret="${OM_ADMIN_CLIENT_SECRET:-}"
  if [ -n "$om_admin_client_secret" ]; then
    if OM_TOKEN="$(curl -fsS --cacert "$ca_bundle" -X POST "$token_endpoint" \
      -H 'Content-Type: application/x-www-form-urlencoded' \
      --data-urlencode 'grant_type=client_credentials' \
      --data-urlencode "client_id=$om_admin_client_id" \
      --data-urlencode "client_secret=$om_admin_client_secret" \
      | "$python_runner" --python-bin python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token", ""))' 2>/dev/null)"; then
      if [ -n "$OM_TOKEN" ]; then
        om_probe_code="$(curl -ks -o /dev/null -w '%{http_code}' \
          "https://${OM_SERVER_HOST}:${OM_SERVER_PORT}$(openmetadata_base_path_prefix)/api/v1/system/version" \
          -H "Authorization: Bearer $OM_TOKEN" || true)"
        if [ "$om_probe_code" = "200" ]; then
          echo "Prepared OpenMetadata access token via client credentials grant for $om_admin_client_id."
          return 0
        fi
      fi
    fi
  fi

  # Fallback: password grant with seeded user credentials.
  seed_username="$(resolve_openmetadata_login_email)" || return 1
  seed_password="$(resolve_openmetadata_seed_password)" || return 1

  if ! OM_TOKEN="$(curl -fsS --cacert "$ca_bundle" -X POST "$token_endpoint" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'grant_type=password' \
    --data-urlencode "client_id=$om_client_id" \
    --data-urlencode "username=$seed_username" \
    --data-urlencode "password=$seed_password" \
    | "$python_runner" --python-bin python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token", ""))' 2>/dev/null)"; then
    echo "ERROR: failed to obtain OpenMetadata OIDC access token for $seed_username; refusing OpenMetadata local-login fallback." >&2
    return 1
  fi

  if [ -z "$OM_TOKEN" ]; then
    echo "ERROR: failed to obtain OpenMetadata OIDC access token for $seed_username; refusing OpenMetadata local-login fallback." >&2
    return 1
  fi

  om_probe_code="$(curl -ks -o /dev/null -w '%{http_code}' \
    "https://${OM_SERVER_HOST}:${OM_SERVER_PORT}$(openmetadata_base_path_prefix)/api/v1/system/version" \
    -H "Authorization: Bearer $OM_TOKEN" || true)"
  if [ "$om_probe_code" != "200" ]; then
    echo "ERROR: obtained OIDC token for $seed_username but OpenMetadata API probe returned HTTP $om_probe_code; refusing OpenMetadata local-login fallback." >&2
    unset OM_TOKEN
    return 1
  fi

  export OM_TOKEN
  echo "Prepared OpenMetadata access token via Keycloak OIDC for $seed_username."
}

# ---------------------------------------------------------------------------
print_mapping_preflight_summary() {
  local state_json="$ROOT_DIR/dq-db/mock-data/openmetadata-ready/openmetadata_runner_state.json"
  local python_runner="$ROOT_DIR/scripts/python_arm64.sh"
  if [ ! -f "$state_json" ]; then
    return 0
  fi

  "$python_runner" --python-bin python3 - "$state_json" <<'PY'
import json
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
try:
  state = json.loads(state_path.read_text(encoding="utf-8"))
except Exception:
  raise SystemExit(0)

pre = (state or {}).get("mapping_preflight") or {}
if not pre:
  raise SystemExit(0)

def fmt(value, default="n/a"):
  return default if value is None else value

print("\nOpenMetadata Mapping Preflight Summary")
print(f"- Coverage: {fmt(pre.get('coverage_percent'))}% (min {fmt(pre.get('min_mapping_coverage'))})")
print(
  f"- Pairs present: {fmt(pre.get('present_schema_table'))}/"
  f"{fmt(pre.get('mapping_distinct_schema_table'))}"
)
print(f"- Catalog schemas: {', '.join(pre.get('catalog_schemas') or ['n/a'])}")

top_missing = pre.get("top_missing_schemas") or []
if top_missing:
  preview = ", ".join(
    f"{item.get('schema')} ({item.get('missing_tables')})" for item in top_missing[:5]
  )
  print(f"- Top missing schemas: {preview}")
PY
}

# ---------------------------------------------------------------------------
run_openmetadata_seed_all() {
  local om_user_seed_script="$SCRIPTS_DIR/seed_openmetadata_users_from_csv.py"
  local sync_script="$SCRIPTS_DIR/sync_dq_db_with_openmetadata.sh"
  local python_runner="$ROOT_DIR/scripts/python_arm64.sh"
  local om_login_email
  local om_password_b64

  om_login_email="$(resolve_openmetadata_login_email)" || return 1
  om_password_b64="$(resolve_openmetadata_password_b64)" || return 1

  export OM_EMAIL="$om_login_email"
  export OM_PASSWORD_B64="$om_password_b64"

  if [ -f "$om_user_seed_script" ]; then
    echo "Seeding OpenMetadata users from users.csv..."
    "$python_runner" --python-bin python3 "$om_user_seed_script" \
      --input "$ROOT_DIR/dq-db/mock-data/users.csv" \
      --endpoint "https://${OM_SERVER_HOST}:${OM_SERVER_PORT}/api" \
      --token "${OM_TOKEN:-}" \
      --email "$OM_EMAIL" \
      --password-b64 "$OM_PASSWORD_B64" \
      --continue-on-error || {
        echo "OpenMetadata user seeding failed."
        return 1
      }
  else
    echo "OpenMetadata user seed script not found: $om_user_seed_script"
    return 1
  fi

  if [ -x "$sync_script" ]; then
    echo "Running OpenMetadata dq-db sync as part of --seed-all..."
    if ! OM_BASE_URL="https://${OM_SERVER_HOST}:${OM_SERVER_PORT}" \
         OM_API_BASE="https://${OM_SERVER_HOST}:${OM_SERVER_PORT}/api" \
         RUN_LDD_MAPPING="${RUN_LDD_MAPPING:-true}" \
         "$sync_script"; then
      echo "OpenMetadata dq-db sync failed."
      print_mapping_preflight_summary
      return 1
    fi
  else
    echo "OpenMetadata sync script not found or not executable: $sync_script"
    return 1
  fi
}

# ---------------------------------------------------------------------------
show_usage() {
  echo "Usage: $0 [--seed-all] [--skip-configure]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed-all) RUN_SEED_ALL=true; shift ;;
    --skip-configure) RUN_CONFIGURE=false; shift ;;
    -h|--help) show_usage; exit 0 ;;
    *) echo "Unknown arg: $1"; show_usage; exit 1 ;;
  esac
done

if [ "$RUN_CONFIGURE" = true ]; then
  configure_openmetadata_auth_settings
fi

prepare_openmetadata_access_token

if [ "$RUN_SEED_ALL" = true ]; then
  run_openmetadata_seed_all
fi

exit 0
