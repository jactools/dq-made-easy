#!/bin/bash
set -e

# ==========================================================================
# Trust-bundle initialization
# ==========================================================================
# The trust-bundle container generates:
#   /certs/trust/trust-bundle.pem      — CA bundle for curl/Python/etc.
#   /certs/trust/trust-bundle.jks      — Java keystore with all CAs.
#   /certs/trust/java-truststore-env.sh — JAVA_OPTS / KC_OPTS for JVMs.
TRUST_ENV="/certs/trust/java-truststore-env.sh"
if [ -f "$TRUST_ENV" ]; then
  . "$TRUST_ENV"
  echo "[entrypoint] sourced trust-bundle env from ${TRUST_ENV}"
else
  echo "[entrypoint] WARNING: trust-bundle env not found at ${TRUST_ENV}" >&2
  echo "[entrypoint] using system truststore" >&2
fi

# Ensure the realm JSON is always present in data/import/ before Keycloak
# starts, regardless of what the named volume contains.  The source file lives
# outside /opt/keycloak/data so the volume mount can never shadow it.
mkdir -p /opt/keycloak/realm-import
if [ -z "${KEYCLOAK_REALM:-}" ]; then
      echo "[entrypoint] ERROR: KEYCLOAK_REALM is not set" >&2
      exit 1
fi

realm_file="/opt/keycloak/realm-import/${KEYCLOAK_REALM}-realm.json"
import_file="/opt/keycloak/data/import/${KEYCLOAK_REALM}-realm.json"

if [ -f "$realm_file" ]; then
      mkdir -p /opt/keycloak/data/import
      cp -f "$realm_file" \
            "$import_file"
else
      echo "[entrypoint] ERROR: realm import file not found at ${realm_file}" >&2
      echo "[entrypoint]        Expected docker-compose to mount the keycloak_seed_artifacts volume" >&2
      exit 1
fi
# Use direct PEM certificate and key files for HTTPS when configured.
# This avoids relying on an openssl binary inside the Keycloak image.
if [ -n "${KEYCLOAK_HTTPS_CERT_FILE:-}" ] && [ -n "${KEYCLOAK_HTTPS_KEY_FILE:-}" ]; then
      echo "[entrypoint] using HTTPS certificate and key files directly"
else
      echo "[entrypoint] no HTTPS certificate/key pair configured; falling back to default Keycloak TLS settings"
fi

# Start Keycloak in background so we can perform an initial admin tweak
# (disable master realm SSL requirement for local/dev convenience).

# Start Keycloak
/opt/keycloak/bin/kc.sh "$@" &
KC_PID=$!

keycloak_https_relative_path="${KEYCLOAK_HTTPS_RELATIVE_PATH:-${KC_HTTPS_RELATIVE_PATH:-}}"
if [ -n "$keycloak_https_relative_path" ]; then
      keycloak_https_relative_path="/${keycloak_https_relative_path#/}"
      keycloak_https_relative_path="${keycloak_https_relative_path%/}"
fi
keycloak_admin_base_url="https://127.0.0.1:8443${keycloak_https_relative_path}"

seed_credentials_file="/opt/keycloak/realm-import/keycloak_seed_user_credentials.csv"
if [ ! -f "$seed_credentials_file" ]; then
      echo "[entrypoint] ERROR: seeded user credential file not found at ${seed_credentials_file}" >&2
      exit 1
fi

# Keycloak admin credentials: use the system admin vars if set,
# otherwise fall back to the KEYCLOAK_ADMIN* env vars that Keycloak
# itself uses for the initial master-realm admin account.
ADMIN_USERNAME="${KEYCLOAK_SYSTEM_ADMIN_USERNAME:-${KEYCLOAK_ADMIN:-}}"
ADMIN_PASSWORD="${KEYCLOAK_SYSTEM_ADMIN_PASSWORD:-${KEYCLOAK_ADMIN_PASSWORD:-}}"

if [ -z "${ADMIN_USERNAME:-}" ] || [ -z "${ADMIN_PASSWORD:-}" ]; then
      echo "[entrypoint] ERROR: admin username and password are required (KEYCLOAK_ADMIN or KEYCLOAK_SYSTEM_ADMIN_USERNAME)" >&2
      exit 1
fi

require_public_url() {
      local value="$1"
      local label="$2"

      if [ -z "$value" ]; then
            echo "[entrypoint] ERROR: ${label} is required" >&2
            exit 1
      fi

      case "$value" in
            http://*|https://*)
                  ;;
            *)
                  echo "[entrypoint] ERROR: ${label} must be an absolute http(s) URL (got ${value})" >&2
                  exit 1
                  ;;
      esac
}

json_array_from_args() {
      local json="["
      local sep=""
      local value

      for value in "$@"; do
            json="${json}${sep}\"${value}\""
            sep=","
      done

      json="${json}]"
      printf '%s' "$json"
}

join_with_delimiter() {
      local delimiter="$1"
      shift

      local value=""
      local result=""

      for value in "$@"; do
            if [ -z "$result" ]; then
                  result="$value"
            else
                  result="${result}${delimiter}${value}"
            fi
      done

      printf '%s' "$result"
}

sync_dq_rules_ui_client() {
      require_public_url "${OIDC_REDIRECT_BASE_URL:-}" "OIDC_REDIRECT_BASE_URL"
      require_public_url "${KONG_PUBLIC_URL:-}" "KONG_PUBLIC_URL"
      require_public_url "${UI_VITE_LOCAL_URL:-}" "UI_VITE_LOCAL_URL"
      require_public_url "${UI_NGINX_LOCAL_URL:-}" "UI_NGINX_LOCAL_URL"

      local redirect_base="${OIDC_REDIRECT_BASE_URL%/}"
      local vite_origin="${UI_VITE_LOCAL_URL%/}"
      local nginx_origin="${UI_NGINX_LOCAL_URL%/}"
      local kong_origin="${KONG_PUBLIC_URL%/}"
      local redirect_uris_json="$(json_array_from_args \
            "${redirect_base}/auth/v1/callback" \
            "${vite_origin}/*" \
            "${nginx_origin}/*" \
            "${kong_origin}/*" \
            "${vite_origin}" \
            "${nginx_origin}" \
            "${kong_origin}")"
      local web_origins_json="$(json_array_from_args \
            "${vite_origin}" \
            "${nginx_origin}" \
            "${kong_origin}" \
            "${redirect_base}")"
      local post_logout_redirects="$(join_with_delimiter '##' \
            "${vite_origin}" \
            "${nginx_origin}" \
            "${kong_origin}" \
            "${redirect_base}")"
      local client_json=""
      local client_id=""

      client_json="$(/opt/keycloak/bin/kcadm.sh get clients -r "${KEYCLOAK_REALM}" -q clientId=dq-rules-ui --fields id)"
      client_id="$(printf '%s\n' "$client_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
      if [ -z "$client_id" ]; then
            echo "[entrypoint] ERROR: dq-rules-ui client not found in realm ${KEYCLOAK_REALM}" >&2
            exit 1
      fi

      /opt/keycloak/bin/kcadm.sh update "clients/${client_id}" -r "${KEYCLOAK_REALM}" \
            -s "redirectUris=${redirect_uris_json}" \
            -s "webOrigins=${web_origins_json}" \
            -s "attributes.\"post.logout.redirect.uris\"=\"${post_logout_redirects}\"" >/dev/null

      echo "[entrypoint] synced dq-rules-ui client redirects for ${redirect_base}"
}

sync_grafana_client() {
      require_public_url "${GRAFANA_PUBLIC_URL:-}" "GRAFANA_PUBLIC_URL"

      local grafana_public_url="${GRAFANA_PUBLIC_URL%/}"
      local redirect_uris_json="$(json_array_from_args \
            "${grafana_public_url}/login/generic_oauth")"
      local web_origins_json="$(json_array_from_args \
            "${grafana_public_url}")"
      local client_json=""
      local client_id=""

      client_json="$(/opt/keycloak/bin/kcadm.sh get clients -r "${KEYCLOAK_REALM}" -q clientId=grafana --fields id)"
      client_id="$(printf '%s\n' "$client_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
      if [ -z "$client_id" ]; then
            echo "[entrypoint] ERROR: grafana client not found in realm ${KEYCLOAK_REALM}" >&2
            exit 1
      fi

      /opt/keycloak/bin/kcadm.sh update "clients/${client_id}" -r "${KEYCLOAK_REALM}" \
            -s "redirectUris=${redirect_uris_json}" \
            -s "webOrigins=${web_origins_json}" \
            -s 'serviceAccountsEnabled=true' >/dev/null

      echo "[entrypoint] synced grafana client redirects for ${grafana_public_url}"
}

sync_grafana_service_account_role() {
      local client_name="grafana"
      local required_role="${GRAFANA_OIDC_REALM_ROLE:-dq:rules:read}"
      local client_json=""
      local client_id=""
      local service_account_json=""
      local service_account_id=""
      local has_required_role=""

      if [ -z "$required_role" ]; then
            echo "[entrypoint] ERROR: GRAFANA_OIDC_REALM_ROLE is required" >&2
            exit 1
      fi

      client_json="$(/opt/keycloak/bin/kcadm.sh get clients -r "${KEYCLOAK_REALM}" -q clientId=${client_name} --fields id)"
      client_id="$(printf '%s\n' "$client_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
      if [ -z "$client_id" ]; then
            echo "[entrypoint] ERROR: ${client_name} client not found in realm ${KEYCLOAK_REALM}" >&2
            exit 1
      fi

      service_account_json="$(/opt/keycloak/bin/kcadm.sh get "clients/${client_id}/service-account-user" -r "${KEYCLOAK_REALM}" --fields id)"
      service_account_id="$(printf '%s\n' "$service_account_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
      if [ -z "$service_account_id" ]; then
            echo "[entrypoint] ERROR: service-account user not found for client ${client_name}" >&2
            exit 1
      fi

      has_required_role="$(/opt/keycloak/bin/kcadm.sh get "users/${service_account_id}/role-mappings/realm" -r "${KEYCLOAK_REALM}" | grep -F '"name" : "'"${required_role}"'"' || true)"
      if [ -n "$has_required_role" ]; then
            echo "[entrypoint] ${client_name} service-account already has realm role ${required_role}"
            return
      fi

      /opt/keycloak/bin/kcadm.sh add-roles -r "${KEYCLOAK_REALM}" --uid "$service_account_id" --rolename "$required_role" >/dev/null
      echo "[entrypoint] assigned realm role ${required_role} to ${client_name} service-account"
}

sync_zammad_client() {
      require_public_url "${ZAMMAD_PUBLIC_URL:-}" "ZAMMAD_PUBLIC_URL"

      local zammad_public_url="${ZAMMAD_PUBLIC_URL%/}"
      local redirect_uris_json="$(json_array_from_args \
            "${zammad_public_url}/auth/openid_connect/callback")"
      local web_origins_json="$(json_array_from_args \
            "${zammad_public_url}")"
      local client_json=""
      local client_id=""

      client_json="$(/opt/keycloak/bin/kcadm.sh get clients -r "${KEYCLOAK_REALM}" -q clientId=zammad --fields id)"
      client_id="$(printf '%s\n' "$client_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
      if [ -z "$client_id" ]; then
            echo "[entrypoint] ERROR: zammad client not found in realm ${KEYCLOAK_REALM}" >&2
            exit 1
      fi

      /opt/keycloak/bin/kcadm.sh update "clients/${client_id}" -r "${KEYCLOAK_REALM}" \
            -s "redirectUris=${redirect_uris_json}" \
            -s "webOrigins=${web_origins_json}" >/dev/null

      echo "[entrypoint] synced zammad client redirects for ${zammad_public_url}"
}

sync_engine_worker_service_account_role() {
      local client_name="${DQ_ENGINE_OIDC_CLIENT_ID:-}"
      local required_role="${DQ_ENGINE_OIDC_REALM_ROLE:-dq:rules:write}"
      local client_json=""
      local client_id=""
      local service_account_json=""
      local service_account_id=""
      local has_required_role=""

      if [ -z "$client_name" ]; then
            echo "[entrypoint] ERROR: DQ_ENGINE_OIDC_CLIENT_ID is required" >&2
            exit 1
      fi

      if [ -z "$required_role" ]; then
            echo "[entrypoint] ERROR: DQ_ENGINE_OIDC_REALM_ROLE is required" >&2
            exit 1
      fi

      client_json="$(/opt/keycloak/bin/kcadm.sh get clients -r "${KEYCLOAK_REALM}" -q clientId="${client_name}" --fields id)"
      client_id="$(printf '%s\n' "$client_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
      if [ -z "$client_id" ]; then
            echo "[entrypoint] ERROR: ${client_name} client not found in realm ${KEYCLOAK_REALM}" >&2
            exit 1
      fi

      service_account_json="$(/opt/keycloak/bin/kcadm.sh get "clients/${client_id}/service-account-user" -r "${KEYCLOAK_REALM}" --fields id)"
      service_account_id="$(printf '%s\n' "$service_account_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
      if [ -z "$service_account_id" ]; then
            echo "[entrypoint] ERROR: service-account user not found for client ${client_name}" >&2
            exit 1
      fi

      has_required_role="$(/opt/keycloak/bin/kcadm.sh get "users/${service_account_id}/role-mappings/realm" -r "${KEYCLOAK_REALM}" | grep -F '"name" : "'"${required_role}"'"' || true)"
      if [ -n "$has_required_role" ]; then
            echo "[entrypoint] ${client_name} service-account already has realm role ${required_role}"
            return
      fi

      /opt/keycloak/bin/kcadm.sh add-roles -r "${KEYCLOAK_REALM}" --uid "$service_account_id" --rolename "$required_role" >/dev/null
      echo "[entrypoint] assigned realm role ${required_role} to ${client_name} service-account"
}

# Wait for Keycloak admin endpoint to be available
echo "[entrypoint] waiting for Keycloak admin endpoint..."
for i in {1..30}; do
      if /opt/keycloak/bin/kcadm.sh config credentials --server "$keycloak_admin_base_url" --realm master --user "${ADMIN_USERNAME}" --password "${ADMIN_PASSWORD}" >/dev/null 2>&1; then
            echo "[entrypoint] Keycloak is up"
            break
      fi
      sleep 1
done

echo "[entrypoint] configuring master realm sslRequired=none (dev only)"
/opt/keycloak/bin/kcadm.sh update realms/master -s sslRequired=none >/dev/null

echo "[entrypoint] syncing dq-rules-ui client redirect configuration"
sync_dq_rules_ui_client

echo "[entrypoint] syncing grafana client redirect configuration"
sync_grafana_client

echo "[entrypoint] reconciling grafana service-account role"
sync_grafana_service_account_role

echo "[entrypoint] syncing zammad client redirect configuration"
sync_zammad_client

echo "[entrypoint] reconciling engine worker service-account role"
sync_engine_worker_service_account_role

echo "[entrypoint] applying rotated seeded user passwords"
rotated_password_count=0
while IFS= read -r credential_line || [ -n "$credential_line" ]; do
      credential_line="${credential_line%$'\r'}"
      if [ -z "$credential_line" ] || [ "$credential_line" = '"email","password"' ]; then
            continue
      fi

      email="${credential_line%%\",\"*}"
      email="${email#\"}"
      password="${credential_line#*\",\"}"
      password="${password%$'\r'}"
      password="${password%\"}"

      if [ "$email" = "email" ] && [ "$password" = "password" ]; then
            continue
      fi

      if [ -z "$email" ] || [ -z "$password" ]; then
            echo "[entrypoint] ERROR: invalid seeded credential row" >&2
            exit 1
      fi

      user_json="$(/opt/keycloak/bin/kcadm.sh get users -r "${KEYCLOAK_REALM}" -q "username=${email}" --fields id)"
      user_id="$(printf '%s\n' "$user_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
      if [ -z "$user_id" ]; then
            echo "[entrypoint] ERROR: seeded Keycloak user not found: ${email}" >&2
            exit 1
      fi

      # Use "--new-password=${password}" (no space) to avoid kcadm argument
      # parsing issues with passwords containing special characters.
      /opt/keycloak/bin/kcadm.sh set-password -r "${KEYCLOAK_REALM}" --userid "$user_id" "--new-password=${password}" >/dev/null
      rotated_password_count=$((rotated_password_count + 1))
done < "$seed_credentials_file"
echo "[entrypoint] applied ${rotated_password_count} rotated seeded user passwords"

# Wait for Keycloak process (keep container running with Keycloak in foreground)
wait $KC_PID
