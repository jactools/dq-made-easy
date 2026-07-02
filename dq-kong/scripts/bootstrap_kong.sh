#!/usr/bin/env bash
set -euo pipefail

bootstrap_exit_handler() {
  local exit_code=$?
  if [ "$exit_code" -eq 0 ]; then
    echo "[kong-bootstrap] bootstrap finished successfully"
  else
    echo "[kong-bootstrap] bootstrap failed with exit code $exit_code"
  fi
}
trap bootstrap_exit_handler EXIT

require_env() {
  local name="$1"
  local value="${!name:-}"
  if [ -z "$value" ]; then
    echo "[kong-bootstrap] missing required environment variable: $name"
    exit 1
  fi
  printf '%s' "$value"
}

KONG_ADMIN_INTERNAL_URL="${KONG_ADMIN_INTERNAL_URL:-http://127.0.0.1:8001}"
DQ_API_INTERNAL_URL="$(require_env DQ_API_INTERNAL_URL)"
APP_CONFIG_INTERNAL_URL="${DQ_API_INTERNAL_URL%/}/api/system/v1/app-config"
MAX_RETRIES="${MAX_RETRIES:-60}"
RETRY_COUNT=0
KEYCLOAK_INTERNAL_URL="$(require_env KEYCLOAK_INTERNAL_URL)"
KEYCLOAK_ADMIN_REALM="$(require_env KEYCLOAK_ADMIN_REALM)"
KEYCLOAK_SYSTEM_ADMIN_USERNAME="$(require_env KEYCLOAK_SYSTEM_ADMIN_USERNAME)"
KEYCLOAK_SYSTEM_ADMIN_PASSWORD="$(require_env KEYCLOAK_SYSTEM_ADMIN_PASSWORD)"
KEYCLOAK_BOOTSTRAP_ADMIN_USERNAME="${KEYCLOAK_ADMIN_USER:-${KEYCLOAK_ADMIN_USERNAME:-${KEYCLOAK_ADMIN:-}}}"
KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASS:-${KEYCLOAK_ADMIN_PASSWORD:-}}"
KEYCLOAK_REALM="$(require_env KEYCLOAK_REALM)"
DQ_ENGINE_OIDC_CLIENT_ID="$(require_env DQ_ENGINE_OIDC_CLIENT_ID)"
UI_VITE_LOCAL_URL="$(require_env UI_VITE_LOCAL_URL)"
UI_NGINX_LOCAL_URL="$(require_env UI_NGINX_LOCAL_URL)"

ALL_AUTHENTICATED_GROUPS='["authenticated","viewer","analyst","data-steward","admin"]'
STEWARD_GROUPS='["data-steward","admin"]'
ADMIN_ONLY_GROUPS='["admin"]'

REALM_CONSUMERS_SYNCED=false

echo "[kong-bootstrap] waiting for Kong Admin API at ${KONG_ADMIN_INTERNAL_URL}"
while [ "$RETRY_COUNT" -lt "$MAX_RETRIES" ]; do
  if curl -s -f "$KONG_ADMIN_INTERNAL_URL/" >/dev/null 2>&1; then
    break
  fi
  RETRY_COUNT=$((RETRY_COUNT + 1))
  sleep 1
done
if [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
  echo "[kong-bootstrap] Kong Admin API not ready after ${MAX_RETRIES}s"
  exit 1
fi

create_service() {
  local name="$1"
  local url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$KONG_ADMIN_INTERNAL_URL/services/$name")
  if [ "$code" = "200" ]; then
    # Keep existing services aligned with the desired upstream target.
    curl -s -X PATCH "$KONG_ADMIN_INTERNAL_URL/services/$name" \
      -H 'Content-Type: application/json' \
      -d "{\"url\":\"$url\"}" >/dev/null
  else
    curl -s -X POST "$KONG_ADMIN_INTERNAL_URL/services" \
      -H 'Content-Type: application/json' \
      -d "{\"name\":\"$name\",\"url\":\"$url\"}" >/dev/null
  fi
}

create_route() {
  local service="$1"
  local route_name="$2"
  local path="$3"
  local methods_json="${4:-[\"GET\",\"POST\",\"PUT\",\"DELETE\",\"PATCH\",\"OPTIONS\"]}"
  if ! curl -s "$KONG_ADMIN_INTERNAL_URL/services/$service/routes" | grep -q "\"name\":\"$route_name\""; then
    curl -s -X POST "$KONG_ADMIN_INTERNAL_URL/services/$service/routes" \
      -H 'Content-Type: application/json' \
      -d "{\"name\":\"$route_name\",\"paths\":[\"$path\"],\"methods\":$methods_json,\"strip_path\":false}" >/dev/null
  fi
}

upsert_plugin_for_route() {
  local route="$1"
  local plugin="$2"
  local payload="$3"
  local plugin_id

  plugin_id=$(curl -s "$KONG_ADMIN_INTERNAL_URL/routes/$route/plugins" | jq -r --arg p "$plugin" '.data[]? | select(.name==$p) | .id // empty' 2>/dev/null | head -1)
  if [ -n "$plugin_id" ]; then
    curl -s -X DELETE "$KONG_ADMIN_INTERNAL_URL/plugins/$plugin_id" >/dev/null || true
  fi

  curl -s -X POST "$KONG_ADMIN_INTERNAL_URL/routes/$route/plugins" \
    -H 'Content-Type: application/json' \
    -d "$payload" >/dev/null
}

set_route_regex_priority() {
  local route_name="$1"
  local priority="$2"
  local route_id

  route_id=$(curl -s "$KONG_ADMIN_INTERNAL_URL/routes/$route_name" | jq -r '.id // empty' 2>/dev/null || true)
  if [ -z "$route_id" ]; then
    return 0
  fi

  curl -s -X PATCH "$KONG_ADMIN_INTERNAL_URL/routes/$route_id" \
    -H 'Content-Type: application/json' \
    -d "{\"regex_priority\":$priority}" >/dev/null || true
}

enable_plugin_if_missing() {
  local service="$1"
  local plugin="$2"
  local payload="$3"
  if ! curl -s "$KONG_ADMIN_INTERNAL_URL/services/$service/plugins" | grep -q "\"name\":\"$plugin\""; then
    curl -s -X POST "$KONG_ADMIN_INTERNAL_URL/services/$service/plugins" \
      -H 'Content-Type: application/json' \
      -d "$payload" >/dev/null
  fi
}

upsert_plugin_for_service() {
  local service="$1"
  local plugin="$2"
  local payload="$3"
  local plugin_id

  plugin_id=$(curl -s "$KONG_ADMIN_INTERNAL_URL/services/$service/plugins" | jq -r --arg p "$plugin" '.data[]? | select(.name==$p) | .id // empty' | head -1)
  if [ -n "$plugin_id" ]; then
    curl -s -X DELETE "$KONG_ADMIN_INTERNAL_URL/plugins/$plugin_id" >/dev/null || true
  fi

  curl -s -X POST "$KONG_ADMIN_INTERNAL_URL/services/$service/plugins" \
    -H 'Content-Type: application/json' \
    -d "$payload" >/dev/null
}

json_get_string() {
  local json="$1"
  local key="$2"
  printf '%s' "$json" | jq -r --arg k "$key" '.[$k] // empty' 2>/dev/null || true
}

json_get_bool() {
  local json="$1"
  local key="$2"
  local value
  value=$(printf '%s' "$json" | jq -r --arg k "$key" '.[$k] // false' 2>/dev/null || true)
  if [ "$value" = "true" ] || [ "$value" = "false" ]; then
    printf '%s' "$value"
  else
    printf 'false'
  fi
}

build_rsa_public_key_from_jwk() {
  local jwk_json="$1"
  local x5c n e rsa_public_key cert_pem

  x5c=$(printf '%s' "$jwk_json" | jq -r '.x5c[0] // empty' 2>/dev/null || true)
  if [ -n "$x5c" ]; then
    echo -n "✅" >&2
    cert_pem="-----BEGIN CERTIFICATE-----\n$(printf '%s' "$x5c" | fold -w 64)\n-----END CERTIFICATE-----"
    rsa_public_key=$(printf '%b\n' "$cert_pem" | openssl x509 -pubkey -noout 2>/dev/null || true)
    if [ -n "$rsa_public_key" ]; then
      echo "✅" >&2
      printf '%s' "$rsa_public_key"
      return 0
    fi
  else
    echo "[kong-bootstrap] no x5c in jwk, falling back to n/e" >&2
  fi

  n=$(printf '%s' "$jwk_json" | jq -r '.n // empty' 2>/dev/null || true)
  e=$(printf '%s' "$jwk_json" | jq -r '.e // empty' 2>/dev/null || true)
  if [ -n "$n" ] && [ -n "$e" ]; then
    rsa_public_key=$(python3 <<'PY'
import sys, json, base64

def b64url_decode(value):
    value += '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode(value)

def der_len(length):
    if length < 128:
        return bytes([length])
    s = length.to_bytes((length.bit_length() + 7) // 8, 'big')
    return bytes([0x80 | len(s)]) + s

def der_integer(value):
    data = value.to_bytes((value.bit_length() + 7) // 8 or 1, 'big')
    if data[0] & 0x80:
        data = b'\x00' + data
    return b'\x02' + der_len(len(data)) + data

def der_sequence(data):
    return b'\x30' + der_len(len(data)) + data

def der_oid(oid):
    parts = [int(x) for x in oid.split('.')]
    first = 40 * parts[0] + parts[1]
    body = bytes([first])
    for part in parts[2:]:
        encoded = []
        while True:
            encoded.insert(0, part & 0x7F)
            part >>= 7
            if part == 0:
                break
        for i in range(len(encoded) - 1):
            encoded[i] |= 0x80
        body += bytes(encoded)
    return b'\x06' + der_len(len(body)) + body

def der_null():
    return b'\x05\x00'

def der_bitstring(data):
    return b'\x03' + der_len(len(data) + 1) + b'\x00' + data

jwk = json.load(sys.stdin)
n = int.from_bytes(b64url_decode(jwk['n']), 'big')
e = int.from_bytes(b64url_decode(jwk['e']), 'big')
rsakey = der_sequence(der_integer(n) + der_integer(e))
alg = der_sequence(der_oid('1.2.840.113549.1.1.1') + der_null())
spki = der_sequence(alg + der_bitstring(rsakey))
print('-----BEGIN PUBLIC KEY-----')
print(base64.encodebytes(spki).decode().strip())
print('-----END PUBLIC KEY-----')
PY
    ) || true
    if [ -n "$rsa_public_key" ]; then
      echo "[kong-bootstrap] derived RSA public key from n/e" >&2
      printf '%s' "$rsa_public_key"
      return 0
    fi
  fi

  echo "[kong-bootstrap] jwk entry lacked usable x5c or n/e values" >&2
  return 1
}

wait_for_keycloak() {
  local ready_url="${KEYCLOAK_INTERNAL_URL%/}/realms/${KEYCLOAK_ADMIN_REALM}/.well-known/openid-configuration"
  local retry_count=0

  echo "[kong-bootstrap] waiting for Keycloak at ${ready_url}" >&2
  while [ "$retry_count" -lt "$MAX_RETRIES" ]; do
    if curl -s -f "$ready_url" >/dev/null 2>&1; then
      return 0
    fi
    retry_count=$((retry_count + 1))
    sleep 1
  done

  echo "[kong-bootstrap] Keycloak not ready after ${MAX_RETRIES}s"
  exit 1
}

keycloak_admin_token() {
  local admin_username="$KEYCLOAK_SYSTEM_ADMIN_USERNAME"
  local admin_password="$KEYCLOAK_SYSTEM_ADMIN_PASSWORD"

  if [ "$KEYCLOAK_ADMIN_REALM" = "master" ]; then
    admin_username="${KEYCLOAK_BOOTSTRAP_ADMIN_USERNAME:-$admin_username}"
    admin_password="${KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD:-$admin_password}"
  fi

  if [ -z "$admin_username" ] || [ -z "$admin_password" ]; then
    echo "[kong-bootstrap] missing Keycloak admin credentials"
    exit 1
  fi

  wait_for_keycloak

  local token_response token_value
  token_response=$(curl -fsS -X POST "${KEYCLOAK_INTERNAL_URL%/}/realms/${KEYCLOAK_ADMIN_REALM}/protocol/openid-connect/token" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'grant_type=password' \
    --data-urlencode 'client_id=admin-cli' \
    --data-urlencode "username=${admin_username}" \
    --data-urlencode "password=${admin_password}" || true)
  token_value=$(printf '%s' "$token_response" | jq -r '.access_token // empty' 2>/dev/null || true)
  if [ -z "$token_value" ]; then
    echo "[kong-bootstrap] failed to obtain Keycloak admin token"
    exit 1
  fi

  printf '%s' "$token_value"
}

keycloak_api_get() {
  local token="$1"
  local path="$2"
  curl -fsS -H "Authorization: Bearer ${token}" "${KEYCLOAK_INTERNAL_URL%/}${path}"
}

keycloak_user_roles_json() {
  local token="$1"
  local user_id="$2"
  keycloak_api_get "$token" "/admin/realms/${KEYCLOAK_REALM}/users/${user_id}/role-mappings/realm"
}

keycloak_realm_users_json() {
  local token="$1"
  local first="$2"
  local max="$3"
  keycloak_api_get "$token" "/admin/realms/${KEYCLOAK_REALM}/users?first=${first}&max=${max}"
}

urlencode() {
  printf '%s' "$1" | jq -sRr @uri
}

role_group_from_name() {
  case "$1" in
    admin|cross-admin|user-manager|workspace-manager|r11|r12|r13|r14|r15|r16)
      printf '%s' "admin"
      ;;
    data-steward|rule-approver|r02|r04|r06|r08|r10)
      printf '%s' "data-steward"
      ;;
    analyst|user|r01|r03|r05|r07|r09)
      printf '%s' "analyst"
      ;;
    viewer)
      printf '%s' "viewer"
      ;;
    *)
      printf '%s' ""
      ;;
  esac
}

ensure_consumer_from_roles() {
  local consumer="$1"
  local roles_json="$2"
  local rsa_public_key="$3"
  local role group

  ensure_consumer "$consumer"
  ensure_jwt_credential "$consumer" "$consumer" "$rsa_public_key"
  ensure_acl_group_for_consumer "$consumer" "authenticated"

  while IFS= read -r role; do
    [ -z "$role" ] && continue
    group=$(role_group_from_name "$role")
    [ -z "$group" ] && continue
    ensure_acl_group_for_consumer "$consumer" "$group"
  done < <(printf '%s' "$roles_json" | jq -r '.[]? | .name // empty')
}

ensure_keycloak_user_consumers() {
  local rsa_public_key="$1"
  local admin_token=""
  local first=0
  local page_size=100
  local users_json="[]"
  local count=0
  local user_id username roles_json

  admin_token=$(keycloak_admin_token)

  while :; do
    users_json=$(keycloak_realm_users_json "$admin_token" "$first" "$page_size")
    count=$(printf '%s' "$users_json" | jq 'length' 2>/dev/null || echo 0)
    if [ "$count" -le 0 ]; then
      break
    fi

    while IFS=$'\t' read -r user_id username; do
      [ -z "$user_id" ] && continue
      [ -z "$username" ] && continue
      roles_json=$(keycloak_user_roles_json "$admin_token" "$user_id")
      ensure_consumer_from_roles "$username" "$roles_json" "$rsa_public_key"
    done < <(printf '%s' "$users_json" | jq -r '.[]? | [.id, (.username // .email // empty)] | @tsv')

    if [ "$count" -lt "$page_size" ]; then
      break
    fi
    first=$((first + page_size))
  done
}

ensure_service_account_consumer_for_client() {
  local client_id="$1"
  local rsa_public_key="$2"
  local admin_token=""
  local client_uuid=""
  local service_user_id=""
  local service_username=""
  local roles_json="[]"
  admin_token=$(keycloak_admin_token)
  client_uuid=$(keycloak_api_get "$admin_token" "/admin/realms/${KEYCLOAK_REALM}/clients?clientId=${client_id}" | jq -r '.[0].id // empty' 2>/dev/null || true)
  if [ -z "$client_uuid" ]; then
    echo "[kong-bootstrap] ${client_id} client not found in Keycloak"
    exit 1
  fi

  service_user_id=$(keycloak_api_get "$admin_token" "/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}/service-account-user" | jq -r '.id // empty' 2>/dev/null || true)
  service_username=$(keycloak_api_get "$admin_token" "/admin/realms/${KEYCLOAK_REALM}/clients/${client_uuid}/service-account-user" | jq -r '.username // .email // empty' 2>/dev/null || true)
  if [ -z "$service_user_id" ] || [ -z "$service_username" ]; then
    echo "[kong-bootstrap] service-account user for ${client_id} not found in Keycloak"
    exit 1
  fi

  roles_json=$(keycloak_user_roles_json "$admin_token" "$service_user_id")
  ensure_consumer_from_roles "$service_username" "$roles_json" "$rsa_public_key"
}

ensure_service_account_consumer() {
  ensure_service_account_consumer_for_client "$DQ_ENGINE_OIDC_CLIENT_ID" "$1"
}

ensure_consumer() {
  local consumer="$1"
  local consumer_path current_username
  consumer_path=$(urlencode "$consumer")
  current_username=$(curl -s "$KONG_ADMIN_INTERNAL_URL/consumers/$consumer_path" | jq -r '.username // empty' 2>/dev/null || true)

  if [ "$current_username" != "$consumer" ]; then
    curl -s -X POST "$KONG_ADMIN_INTERNAL_URL/consumers" \
      -H 'Content-Type: application/json' \
      -d "{\"username\":$(printf '%s' "$consumer" | jq -sRr @json),\"custom_id\":$(printf '%s' "$consumer" | jq -sRr @json)}" >/dev/null
  fi
}

ensure_jwt_credential() {
  local consumer="$1"
  local credential_key="$2"
  local rsa_public_key="$3"
  local consumer_path jwt_id

  consumer_path=$(urlencode "$consumer")
  jwt_id=$(curl -s "$KONG_ADMIN_INTERNAL_URL/consumers/$consumer_path/jwt" | jq -r --arg k "$credential_key" '.data[]? | select(.key==$k) | .id // empty' 2>/dev/null | head -1 || true)
  if [ -n "$jwt_id" ]; then
    curl -s -X DELETE "$KONG_ADMIN_INTERNAL_URL/consumers/$consumer_path/jwt/$jwt_id" >/dev/null || true
  fi

  curl -s -X POST "$KONG_ADMIN_INTERNAL_URL/consumers/$consumer_path/jwt" \
    --data "key=$credential_key" \
    --data algorithm=RS256 \
    --data-urlencode "rsa_public_key=$rsa_public_key" >/dev/null
}

ensure_acl_group_for_consumer() {
  local consumer="$1"
  local group="$2"
  local consumer_path

  consumer_path=$(urlencode "$consumer")
  if curl -s "$KONG_ADMIN_INTERNAL_URL/consumers/$consumer_path/acls" | jq -e --arg g "$group" '.data[]? | select(.group==$g)' >/dev/null 2>&1; then
    return 0
  fi

  curl -s -X POST "$KONG_ADMIN_INTERNAL_URL/consumers/$consumer_path/acls" \
    -H 'Content-Type: application/json' \
    -d "{\"group\":\"$group\"}" >/dev/null
}

setup_acl_for_route() {
  local route_name="$1"
  local allow_groups_json="$2"
  upsert_plugin_for_route "$route_name" "acl" "{\"name\":\"acl\",\"config\":{\"allow\":$allow_groups_json,\"hide_groups_header\":false}}"
}

enable_jwt_for_route() {
  local route_name="$1"

  local app_cfg sso_enabled sso_issuer
  local env_sso_enabled env_sso_issuer
  app_cfg=$(curl -s "$APP_CONFIG_INTERNAL_URL" || true)
  sso_enabled=$(json_get_bool "$app_cfg" "ssoEnabled")
  sso_issuer=$(json_get_string "$app_cfg" "ssoIssuer")

  env_sso_enabled=$(printf '%s' "${SSO_ENABLED:-}" | tr '[:upper:]' '[:lower:]')
  env_sso_issuer="${SSO_PUBLIC_ISSUER_URL:-}"

  # Keep app-config protected; when app-config requires auth, fall back to explicit env.
  if [ "$sso_enabled" != "true" ] && [ "$env_sso_enabled" = "true" ]; then
    sso_enabled="true"
  fi
  if [ -z "$sso_issuer" ] && [ -n "$env_sso_issuer" ]; then
    sso_issuer="$env_sso_issuer"
  fi

  if [ "$sso_enabled" != "true" ] || [ -z "$sso_issuer" ]; then
    echo "[kong-bootstrap] SSO disabled or missing issuer; skipping JWT setup"
    return 0
  fi

  local route_id
  route_id=$(curl -s "$KONG_ADMIN_INTERNAL_URL/routes/$route_name" | jq -r '.id // empty' 2>/dev/null || true)
  if [ -z "$route_id" ]; then
    echo "[kong-bootstrap] route id not found for $route_name"
    return 0
  fi

  upsert_plugin_for_route "$route_name" "jwt" '{"name":"jwt","config":{"key_claim_name":"preferred_username","claims_to_verify":["exp"],"run_on_preflight":false}}'

  local jwks_uri x5c cert_pem rsa_public_key issuer_for_jwks

  jwks_uri="${JWT_JWKS_URL:-}"
  if [ -z "$jwks_uri" ]; then
    # Use the internal Keycloak admin URL for JWKS resolution, not the public issuer.
    jwks_uri="${KEYCLOAK_INTERNAL_URL%/}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/certs"
  fi

  rsa_public_key=""
  echo "[kong-bootstrap] fetching jwks from $jwks_uri" >&2
  jwk_json=$(curl -s "$jwks_uri" | jq -c '.keys[] | select(.kty == "RSA" and ((.use // "sig") == "sig"))' 2>/dev/null | head -1 || true)
  if [ -z "$jwk_json" ]; then
    echo "[kong-bootstrap] no RSA signing key found in jwks; falling back to first RSA key" >&2
    jwk_json=$(curl -s "$jwks_uri" | jq -c '.keys[] | select(.kty == "RSA")' 2>/dev/null | head -1 || true)
  fi
  if [ -n "$jwk_json" ]; then
    rsa_public_key=$(build_rsa_public_key_from_jwk "$jwk_json") || true
  fi

  if [ -z "$rsa_public_key" ]; then
    echo "[kong-bootstrap] no usable RSA key found in jwks; failing bootstrap"
    return 1
  fi

  if [ "$REALM_CONSUMERS_SYNCED" != "true" ]; then
    ensure_keycloak_user_consumers "$rsa_public_key"
    ensure_service_account_consumer "$rsa_public_key"
    ensure_service_account_consumer_for_client "${GRAFANA_OIDC_CLIENT_ID:-grafana}" "$rsa_public_key"
    REALM_CONSUMERS_SYNCED=true
  fi
}

disable_jwt_for_route() {
  local route_name="$1"
  local route_id
  route_id=$(curl -s "$KONG_ADMIN_INTERNAL_URL/routes/$route_name" | jq -r '.id // empty' 2>/dev/null || true)
  if [ -z "$route_id" ]; then
    return 0
  fi

  curl -s "$KONG_ADMIN_INTERNAL_URL/routes/$route_id/plugins" | jq -r '.data[]? | select(.name=="jwt") | .id // empty' 2>/dev/null | while IFS= read -r plugin_id; do
    [ -n "$plugin_id" ] && curl -s -X DELETE "$KONG_ADMIN_INTERNAL_URL/plugins/$plugin_id" >/dev/null || true
  done
}

create_service "dq-api" "http://api:4010"
create_route "dq-api" "dq-api-auth-v1" "/auth/v1"
create_route "dq-api" "dq-api-admin-v1" "/admin/v1"
create_route "dq-api" "dq-api-admin-v1-users" "/admin/v1/users"
create_route "dq-api" "dq-api-admin-v1-roles" "/admin/v1/roles"
create_route "dq-api" "dq-api-admin-v1-rules" "/admin/v1/rules"
create_route "dq-api" "dq-api-system-v1" "/system/v1"
create_route "dq-api" "dq-api-system-v1-app-config-read" "/system/v1/app-config" '["GET","HEAD","OPTIONS"]'
create_route "dq-api" "dq-api-system-v1-app-config-write" "/system/v1/app-config" '["POST","PUT","PATCH","DELETE"]'
create_route "dq-api" "dq-api-system-v1-ui-registry" "/api/system/v1/ui-registry"
create_route "dq-api" "dq-api-data-catalog-v1" "/data-catalog/v1"
create_route "dq-api" "dq-api-rulebuilder-v1" "/rulebuilder/v1"
create_route "dq-api" "dq-api-agent-v1" "/agent/v1"
create_route "dq-api" "dq-api-v1" "/v1"
create_route "dq-api" "dq-api-rulebuilder-v1-approvals-read" "/rulebuilder/v1/approvals" '["GET","HEAD","OPTIONS"]'
create_route "dq-api" "dq-api-rulebuilder-v1-approvals-write" "/rulebuilder/v1/approvals" '["POST","PUT","PATCH","DELETE"]'

# Public allowlisted endpoints (must NOT require JWT at Kong)
create_route "dq-api" "dq-api-health" "/health"
create_route "dq-api" "dq-api-admin-v1-me" "/admin/v1/me"
set_route_regex_priority "dq-api-admin-v1-me" 100
create_route "dq-api" "dq-api-auth-v1-redirect" "/auth/v1/redirect"
create_route "dq-api" "dq-api-auth-v1-callback" "/auth/v1/callback"
create_route "dq-api" "dq-api-auth-v1-logout" "/auth/v1/logout"
create_route "dq-api" "dq-api-auth-v1-login" "/auth/v1/login"
create_route "dq-api" "dq-api-system-v1-version-catalog" "/system/v1/version-catalog"
create_route "dq-api" "dq-api-system-v1-system-info" "/system/v1/system-info"
create_route "dq-api" "dq-api-system-v1-health" "/system/v1/health"
create_route "dq-api" "dq-api-system-v1-readiness" "/system/v1/readiness"
create_route "dq-api" "dq-api-system-v1-live" "/system/v1/live"
create_route "dq-api" "dq-api-system-v1-ready" "/system/v1/ready"
create_route "dq-api" "dq-api-docs" "/api-docs"
create_route "dq-api" "dq-api-docs-json" "/api-docs-json"

upsert_plugin_for_service "dq-api" "cors" "{\"name\":\"cors\",\"config\":{\"origins\":[\"${UI_VITE_LOCAL_URL}\",\"${UI_NGINX_LOCAL_URL}\",\"http://localhost:5173\",\"http://127.0.0.1:5173\",\"http://localhost:3000\"],\"methods\":[\"GET\",\"POST\",\"PUT\",\"DELETE\",\"PATCH\",\"OPTIONS\"],\"headers\":[\"Accept\",\"Accept-Version\",\"Content-Length\",\"Content-MD5\",\"Content-Type\",\"Date\",\"X-Auth-Token\",\"Authorization\",\"X-Correlation-ID\",\"traceparent\",\"tracestate\",\"baggage\"],\"exposed_headers\":[\"X-Kong-Response-Latency\",\"X-Kong-Upstream-Latency\",\"X-Correlation-ID\",\"X-Trace-ID\"],\"credentials\":true,\"max_age\":3600}}"
enable_plugin_if_missing "dq-api" "rate-limiting" '{"name":"rate-limiting","config":{"minute":1000,"hour":50000,"policy":"local"}}'

TRUST_PROXY_AUTH_ENABLED=$(printf '%s' "$(require_env TRUST_PROXY_AUTH)" | tr '[:upper:]' '[:lower:]')
if [ "$TRUST_PROXY_AUTH_ENABLED" = "true" ]; then
  enable_jwt_for_route "dq-api-auth-v1"
  enable_jwt_for_route "dq-api-admin-v1"
  enable_jwt_for_route "dq-api-admin-v1-users"
  enable_jwt_for_route "dq-api-admin-v1-roles"
  enable_jwt_for_route "dq-api-admin-v1-rules"
  enable_jwt_for_route "dq-api-admin-v1-me"
  enable_jwt_for_route "dq-api-system-v1"
  enable_jwt_for_route "dq-api-system-v1-app-config-read"
  enable_jwt_for_route "dq-api-system-v1-app-config-write"
  enable_jwt_for_route "dq-api-system-v1-ui-registry"
  enable_jwt_for_route "dq-api-data-catalog-v1"
  enable_jwt_for_route "dq-api-rulebuilder-v1"
  enable_jwt_for_route "dq-api-agent-v1"
  enable_jwt_for_route "dq-api-v1"
  enable_jwt_for_route "dq-api-rulebuilder-v1-approvals-read"
  enable_jwt_for_route "dq-api-rulebuilder-v1-approvals-write"

  setup_acl_for_route "dq-api-auth-v1" "$ALL_AUTHENTICATED_GROUPS"
  setup_acl_for_route "dq-api-admin-v1" "$ADMIN_ONLY_GROUPS"
  setup_acl_for_route "dq-api-admin-v1-users" "$ADMIN_ONLY_GROUPS"
  setup_acl_for_route "dq-api-admin-v1-roles" "$ADMIN_ONLY_GROUPS"
  setup_acl_for_route "dq-api-admin-v1-rules" "$ADMIN_ONLY_GROUPS"
  setup_acl_for_route "dq-api-system-v1" "$ALL_AUTHENTICATED_GROUPS"
  setup_acl_for_route "dq-api-system-v1-app-config-read" "$ALL_AUTHENTICATED_GROUPS"
  setup_acl_for_route "dq-api-system-v1-app-config-write" "$ADMIN_ONLY_GROUPS"
  setup_acl_for_route "dq-api-system-v1-ui-registry" "$ALL_AUTHENTICATED_GROUPS"
  setup_acl_for_route "dq-api-data-catalog-v1" "$ALL_AUTHENTICATED_GROUPS"
  setup_acl_for_route "dq-api-rulebuilder-v1" "$ALL_AUTHENTICATED_GROUPS"
  setup_acl_for_route "dq-api-agent-v1" "$ALL_AUTHENTICATED_GROUPS"
  setup_acl_for_route "dq-api-v1" "$ALL_AUTHENTICATED_GROUPS"
  setup_acl_for_route "dq-api-rulebuilder-v1-approvals-read" "$ALL_AUTHENTICATED_GROUPS"
  setup_acl_for_route "dq-api-rulebuilder-v1-approvals-write" "$STEWARD_GROUPS"
else
  disable_jwt_for_route "dq-api-auth-v1"
  disable_jwt_for_route "dq-api-admin-v1"
  disable_jwt_for_route "dq-api-admin-v1-users"
  disable_jwt_for_route "dq-api-admin-v1-roles"
  disable_jwt_for_route "dq-api-admin-v1-rules"
  disable_jwt_for_route "dq-api-admin-v1-me"
  disable_jwt_for_route "dq-api-system-v1"
  disable_jwt_for_route "dq-api-system-v1-app-config-read"
  disable_jwt_for_route "dq-api-system-v1-app-config-write"
  disable_jwt_for_route "dq-api-system-v1-ui-registry"
  disable_jwt_for_route "dq-api-data-catalog-v1"
  disable_jwt_for_route "dq-api-rulebuilder-v1"
  disable_jwt_for_route "dq-api-agent-v1"
  disable_jwt_for_route "dq-api-rulebuilder-v1-approvals-read"
  disable_jwt_for_route "dq-api-rulebuilder-v1-approvals-write"
  disable_jwt_for_route "dq-api-v1"
fi

# ---------------------------------------------------------------------------
# OpenTelemetry: enable the bundled opentelemetry plugin globally so Kong
# exports request/router/balancer spans to the OTel collector via OTLP/HTTP.
# KONG_TRACING_INSTRUMENTATIONS and KONG_TRACING_SAMPLING_RATE are set as
# server-level env vars in docker-compose; this plugin wires the exporter.
# ---------------------------------------------------------------------------
KONG_OTEL_ENDPOINT="$(require_env KONG_OTEL_ENDPOINT)"

setup_opentelemetry_plugin() {
  local existing_id
  existing_id=$(curl -s "$KONG_ADMIN_INTERNAL_URL/plugins" | jq -r '.data[]? | select(.name=="opentelemetry") | .id // empty' 2>/dev/null | head -1 || true)

  local payload
  payload=$(printf '{"name":"opentelemetry","config":{"endpoint":"%s","resource_attributes":{"service.name":"dq-kong"},"batch_flush_delay":2}}' "$KONG_OTEL_ENDPOINT")

  if [ -n "$existing_id" ]; then
    # Update endpoint in case it changed; leave other fields intact.
    curl -s -X PATCH "$KONG_ADMIN_INTERNAL_URL/plugins/$existing_id" \
      -H 'Content-Type: application/json' \
      -d "$payload" >/dev/null
    echo "[kong-bootstrap] opentelemetry plugin updated (id=$existing_id)"
  else
    curl -s -X POST "$KONG_ADMIN_INTERNAL_URL/plugins" \
      -H 'Content-Type: application/json' \
      -d "$payload" >/dev/null
    echo "[kong-bootstrap] opentelemetry plugin enabled (endpoint=$KONG_OTEL_ENDPOINT)"
  fi
}

setup_opentelemetry_plugin

echo "[kong-bootstrap] configuration complete"
