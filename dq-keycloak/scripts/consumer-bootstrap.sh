#!/bin/bash
set -e

# dq-made-easy — Keycloak consumer bootstrap for DQ-specific configuration.
#
# Mounted at /opt/platform-keycloak/scripts/consumer-bootstrap.sh
# Handles: client redirect syncs, DQ service-account role assignments.
#
# Called by platform-keycloak bootstrap after realm import and password rotation.

# ==========================================================================
# Helpers
# ==========================================================================

keycloak_https_relative_path="${KC_HTTPS_RELATIVE_PATH:-}"
if [ -n "$keycloak_https_relative_path" ]; then
      keycloak_https_relative_path="/${keycloak_https_relative_path#/}"
      keycloak_https_relative_path="${keycloak_https_relative_path%/}"
fi
keycloak_admin_base_url="https://localhost:${KC_HTTPS_PORT:-8443}${keycloak_https_relative_path}"

ADMIN_USERNAME="${KEYCLOAK_SYSTEM_ADMIN_USERNAME:-${KEYCLOAK_ADMIN:-}}"
ADMIN_PASSWORD="${KEYCLOAK_SYSTEM_ADMIN_PASSWORD:-${KEYCLOAK_ADMIN_PASSWORD:-}}"

require_public_url() {
      local value="$1"
      local label="$2"
      if [ -z "$value" ]; then
            echo "[dq-bootstrap] ERROR: ${label} is required" >&2
            return 0
      fi
      case "$value" in
            http://*|https://*) ;;
            *)
                  echo "[dq-bootstrap] ERROR: ${label} must be an absolute http(s) URL (got ${value})" >&2
                  return 0
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

kcadm() {
      /opt/platform-keycloak/scripts/kcadm-trust.sh "$@"
}

# ==========================================================================
# Client sync helpers
# ==========================================================================

sync_client_redirects() {
      local client_id_name="$1"
      local redirect_uris_json="$2"
      local web_origins_json="$3"
      local post_logout_redirects="${4:-}"
      local client_json=""
      local client_id=""

      client_json="$(kcadm get clients -r "${KEYCLOAK_REALM}" -q clientId="${client_id_name}" --fields id 2>/dev/null)" || return 0
      client_id="$(printf '%s\n' "$client_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
      if [ -z "$client_id" ]; then
            echo "[dq-bootstrap] ${client_id_name} client not found in realm ${KEYCLOAK_REALM}; skipping redirect sync"
            return 0
      fi

      local update_args=()
      update_args+=("redirectUris=${redirect_uris_json}")
      update_args+=("webOrigins=${web_origins_json}")
      if [ -n "$post_logout_redirects" ]; then
            update_args+=("attributes.\"post.logout.redirect.uris\"=\"${post_logout_redirects}\"")
      fi

      kcadm update "clients/${client_id}" -r "${KEYCLOAK_REALM}" "${update_args[@]}" >/dev/null 2>&1
      echo "[dq-bootstrap] synced ${client_id_name} client redirects"
}

sync_service_account_role() {
      local client_name="$1"
      local required_role="$2"
      local client_json=""
      local client_id=""
      local service_account_json=""
      local service_account_id=""

      if [ -z "$required_role" ]; then
            echo "[dq-bootstrap] WARNING: required role for ${client_name} service-account is not set" >&2
            return 0
      fi

      client_json="$(kcadm get clients -r "${KEYCLOAK_REALM}" -q clientId="${client_name}" --fields id 2>/dev/null)" || return 0
      client_id="$(printf '%s\n' "$client_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
      if [ -z "$client_id" ]; then
            echo "[dq-bootstrap] ${client_name} client not found in realm ${KEYCLOAK_REALM}; skipping role assignment"
            return 0
      fi

      service_account_json="$(kcadm get "clients/${client_id}/service-account-user" -r "${KEYCLOAK_REALM}" --fields id 2>/dev/null)" || return 0
      service_account_id="$(printf '%s\n' "$service_account_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
      if [ -z "$service_account_id" ]; then
            echo "[dq-bootstrap] service-account user not found for client ${client_name}; skipping role assignment"
            return 0
      fi

      local has_role
      has_role="$(kcadm get "users/${service_account_id}/role-mappings/realm" -r "${KEYCLOAK_REALM}" 2>/dev/null | grep -F '"name" : "'"${required_role}"'"' || true)"
      if [ -n "$has_role" ]; then
            echo "[dq-bootstrap] ${client_name} service-account already has realm role ${required_role}"
            return 0
      fi

      kcadm add-roles -r "${KEYCLOAK_REALM}" --uid "$service_account_id" --rolename "$required_role" >/dev/null 2>&1
      echo "[dq-bootstrap] assigned realm role ${required_role} to ${client_name} service-account"
}

sync_grafana_client() {
      local grafana_public_url="${GRAFANA_PUBLIC_URL%/}"
      local redirect_uris_json
      local web_origins_json
      local grafana_client_json=""
      local grafana_client_id=""

      redirect_uris_json="$(json_array_from_args "${grafana_public_url}/login/generic_oauth")"
      web_origins_json="$(json_array_from_args "${grafana_public_url}")"
      sync_client_redirects "grafana" "$redirect_uris_json" "$web_origins_json"

      grafana_client_json="$(kcadm get clients -r "${KEYCLOAK_REALM}" -q clientId=grafana --fields id 2>/dev/null)" || true
      grafana_client_id="$(printf '%s\n' "$grafana_client_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
      if [ -n "$grafana_client_id" ]; then
            kcadm update "clients/${grafana_client_id}" -r "${KEYCLOAK_REALM}" -s serviceAccountsEnabled=true >/dev/null 2>&1 || true
      fi
      sync_service_account_role "grafana" "${GRAFANA_OIDC_REALM_ROLE:?GRAFANA_OIDC_REALM_ROLE is required}"
}

# ==========================================================================
# Sync dq-rules-ui client redirects
# ==========================================================================

if [ -n "${OIDC_REDIRECT_BASE_URL:-}" ] && [ -n "${KONG_PUBLIC_URL:-}" ] && [ -n "${UI_VITE_LOCAL_URL:-}" ] && [ -n "${UI_NGINX_LOCAL_URL:-}" ]; then
      require_public_url "${OIDC_REDIRECT_BASE_URL:?OIDC_REDIRECT_BASE_URL is required}" "OIDC_REDIRECT_BASE_URL"
      require_public_url "${KONG_PUBLIC_URL:?KONG_PUBLIC_URL is required}" "KONG_PUBLIC_URL"
      require_public_url "${UI_VITE_LOCAL_URL:?UI_VITE_LOCAL_URL is required}" "UI_VITE_LOCAL_URL"
      require_public_url "${UI_NGINX_LOCAL_URL:?UI_NGINX_LOCAL_URL is required}" "UI_NGINX_LOCAL_URL"

      redirect_base="${OIDC_REDIRECT_BASE_URL%/}"
      vite_origin="${UI_VITE_LOCAL_URL%/}"
      nginx_origin="${UI_NGINX_LOCAL_URL%/}"
      kong_origin="${KONG_PUBLIC_URL%/}"
      redirect_uris_json="$(json_array_from_args \
            "${redirect_base}/auth/v1/callback" \
            "${vite_origin}/*" \
            "${nginx_origin}/*" \
            "${kong_origin}/*" \
            "${vite_origin}" \
            "${nginx_origin}" \
            "${kong_origin}")"
      web_origins_json="$(json_array_from_args \
            "${vite_origin}" \
            "${nginx_origin}" \
            "${kong_origin}" \
            "${redirect_base}")"
      post_logout_redirects="$(join_with_delimiter '##' \
            "${vite_origin}" \
            "${nginx_origin}" \
            "${kong_origin}" \
            "${redirect_base}")"
      sync_client_redirects "dq-rules-ui" "$redirect_uris_json" "$web_origins_json" "$post_logout_redirects"
fi

# ==========================================================================
# Sync other client redirects
# ==========================================================================

if [ -n "${GRAFANA_PUBLIC_URL:-}" ]; then
      sync_grafana_client
fi

if [ -n "${ZAMMAD_PUBLIC_URL:-}" ]; then
      zammad_public_url="${ZAMMAD_PUBLIC_URL%/}"
      redirect_uris_json="$(json_array_from_args "${zammad_public_url}/auth/openid_connect/callback")"
      web_origins_json="$(json_array_from_args "${zammad_public_url}")"
      sync_client_redirects "zammad" "$redirect_uris_json" "$web_origins_json"
fi

# ==========================================================================
# Sync DQ service-account roles
# ==========================================================================

sync_service_account_role "${DQ_ENGINE_OIDC_CLIENT_ID:?DQ_ENGINE_OIDC_CLIENT_ID is required}" "${DQ_ENGINE_OIDC_REALM_ROLE:?DQ_ENGINE_OIDC_REALM_ROLE is required}"
sync_service_account_role "openmetadata-admin" "${OM_ADMIN_OIDC_REALM_ROLE:?OM_ADMIN_OIDC_REALM_ROLE is required}"

echo "[dq-bootstrap] DQ Keycloak configuration complete"
