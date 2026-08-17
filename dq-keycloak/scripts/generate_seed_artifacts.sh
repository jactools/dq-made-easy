#!/usr/bin/env bash
set -euo pipefail

seed_dir="${KEYCLOAK_SEED_OUTPUT_DIR:-/seed-data}"
realm_name="${KEYCLOAK_REALM:?KEYCLOAK_REALM is required}"
realm_display_name="${KEYCLOAK_REALM_DISPLAY_NAME:-Jaccloud Realm}"
redirect_base="${OIDC_REDIRECT_BASE_URL:-${KONG_PUBLIC_URL:?KONG_PUBLIC_URL is required}}"
redirect_base="${redirect_base%/}"

seed_email_domain="${KEYCLOAK_EMAIL_DOMAIN:-}"
domain_args=()
if [ -n "$seed_email_domain" ]; then
  domain_args+=(--domain "$seed_email_domain")
fi

: "${UI_VITE_LOCAL_URL:?UI_VITE_LOCAL_URL is required}"
: "${UI_NGINX_LOCAL_URL:?UI_NGINX_LOCAL_URL is required}"
: "${ZAMMAD_PUBLIC_URL:?ZAMMAD_PUBLIC_URL is required}"
: "${DQ_ENGINE_OIDC_CLIENT_ID:?DQ_ENGINE_OIDC_CLIENT_ID is required}"
# DQ_ENGINE_OIDC_CLIENT_SECRET is optional when re-using an existing setup.
# If unset, leave empty so the Python generator may reuse an existing secret
# or fall back to the local default ("changeme").
DQ_ENGINE_OIDC_CLIENT_SECRET="${DQ_ENGINE_OIDC_CLIENT_SECRET:-}"

mkdir -p "$seed_dir"
workspace_tmp_dir="${WORKSPACE_TMP_DIR:-/workspace-tmp}"
mkdir -p "$workspace_tmp_dir"

workspace_environment_label="$(printf '%s' "${ENVIRONMENT:-}" | tr '[:upper:]' '[:lower:]')"
workspace_stage_suffix=""
case "$workspace_environment_label" in
  dev|development)
    workspace_stage_suffix=".dev"
    ;;
  test|testing)
    workspace_stage_suffix=".test"
    ;;
  prod|production)
    workspace_stage_suffix=".prod"
    ;;
esac

if [ -z "$workspace_stage_suffix" ]; then
  echo "ENVIRONMENT must resolve to dev, test, or prod for seed artifacts" >&2
  exit 2
fi

rotated_users_csv="$seed_dir/users.csv"
roles_csv="$seed_dir/roles.csv"
user_roles_csv="$seed_dir/user_roles.csv"
credentials_csv="$seed_dir/keycloak_seed_user_credentials.csv"
credentials_env="$seed_dir/keycloak_seed_user_credentials.env"
workspace_rotated_users_csv="$workspace_tmp_dir/users${workspace_stage_suffix}.csv"
workspace_roles_csv="$workspace_tmp_dir/roles${workspace_stage_suffix}.csv"
workspace_user_roles_csv="$workspace_tmp_dir/user_roles${workspace_stage_suffix}.csv"
workspace_credentials_csv="$workspace_tmp_dir/keycloak_seed_user_credentials${workspace_stage_suffix}.csv"
workspace_credentials_env="$workspace_tmp_dir/keycloak_seed_user_credentials${workspace_stage_suffix}.env"
workspace_engine_oidc_env="$workspace_tmp_dir/dq_engine_oidc${workspace_stage_suffix}.env"

KEYCLOAK_JACCLOUD_USERNAME="${KEYCLOAK_JACCLOUD_USERNAME:-}"
SMOKE_LOGIN_EMAIL="${SMOKE_LOGIN_EMAIL:-}"
OPERATOR_LOGIN_EMAIL="${OPERATOR_LOGIN_EMAIL:-}"
AUDITOR_LOGIN_EMAIL="${AUDITOR_LOGIN_EMAIL:-}"
REGULATOR_LOGIN_EMAIL="${REGULATOR_LOGIN_EMAIL:-}"
if [ -z "$OPERATOR_LOGIN_EMAIL" ] || [ -z "$AUDITOR_LOGIN_EMAIL" ] || [ -z "$REGULATOR_LOGIN_EMAIL" ]; then
  echo "OPERATOR_LOGIN_EMAIL, AUDITOR_LOGIN_EMAIL, and REGULATOR_LOGIN_EMAIL are required" >&2
  exit 2
fi
export KEYCLOAK_JACCLOUD_USERNAME SMOKE_LOGIN_EMAIL OPERATOR_LOGIN_EMAIL AUDITOR_LOGIN_EMAIL REGULATOR_LOGIN_EMAIL

cp -f /app/mock-data/roles.csv "$roles_csv"
cp -f /app/mock-data/user_roles.csv "$user_roles_csv"
cp -f /app/mock-data/roles.csv "$workspace_roles_csv"
cp -f /app/mock-data/user_roles.csv "$workspace_user_roles_csv"

python /app/seed_password_rotation.py \
  --source /app/mock-data/users.csv \
  --rotated-users "$rotated_users_csv" \
  --credentials-csv "$credentials_csv" \
  --credentials-env "$credentials_env"

cp -f "$rotated_users_csv" "$workspace_rotated_users_csv"
cp -f "$credentials_csv" "$workspace_credentials_csv"
cp -f "$credentials_env" "$workspace_credentials_env"

python /app/generate_keycloak_realm.py \
  --input "$rotated_users_csv" \
  --realm-name "$realm_name" \
  --realm-display-name "$realm_display_name" \
  --redirect "${redirect_base}/auth/v1/callback" \
  --frontend-origin "$UI_VITE_LOCAL_URL" \
  --frontend-origin "$UI_NGINX_LOCAL_URL" \
  --frontend-origin "${KONG_PUBLIC_URL%/}" \
  --zammad-public-url "$ZAMMAD_PUBLIC_URL" \
  "${domain_args[@]}" \
  --output "$seed_dir/${realm_name}-realm.json" \
  --engine-service-client-id "$DQ_ENGINE_OIDC_CLIENT_ID" \
  --engine-service-client-secret "$DQ_ENGINE_OIDC_CLIENT_SECRET" \
  --engine-service-client-env-output "$seed_dir/dq_engine_oidc.env"

test -s "$seed_dir/${realm_name}-realm.json"
test -s "$seed_dir/dq_engine_oidc.env"
test -s "$rotated_users_csv"
test -s "$roles_csv"
test -s "$user_roles_csv"
test -s "$credentials_csv"
test -s "$credentials_env"
test -s "$workspace_rotated_users_csv"
test -s "$workspace_roles_csv"
test -s "$workspace_user_roles_csv"
test -s "$workspace_credentials_csv"
test -s "$workspace_credentials_env"

cp -f "$seed_dir/dq_engine_oidc.env" "$workspace_engine_oidc_env"
test -s "$workspace_engine_oidc_env"

printf '\n'
printf '\n'
printf '\n'
printf '\n'
printf '\n'
printf '\n'
printf '\n'
printf '\n'
printf '\n'
printf '\n'

# Output credentials to stdout for K8s job logging
echo ""
echo "=== KEYCLOAK SEED CREDENTIALS ==="
cat "$credentials_csv"
echo ""
echo "=== KEYCLOAK SEED CREDENTIALS END ==="
echo ""

# Import realm into Keycloak via Admin API
keycloak_url="${KEYCLOAK_SYSTEM_ADMIN_URL:-https://keycloak:8443}"
keycloak_url="${keycloak_url%/}"
admin_user="${KEYCLOAK_ADMIN:-admin}"
admin_password="${KEYCLOAK_SYSTEM_ADMIN_PASSWORD:-changeme}"
ca_bundle="${CURL_CA_BUNDLE:-}"

# Get admin token
admin_token=$(curl -sk --cacert "$ca_bundle" -X POST "$keycloak_url/auth/realms/master/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=admin-cli" \
  -d "username=$admin_user" \
  -d "password=$admin_password" \
  | python -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

if [ -n "$admin_token" ]; then
  echo "Importing realm $realm_name into Keycloak..."
  curl -sk --cacert "$ca_bundle" -X POST "$keycloak_url/auth/admin/realms" \
    -H "Authorization: Bearer $admin_token" \
    -H "Content-Type: application/json" \
    --data-binary "@$seed_dir/${realm_name}-realm.json" \
    && echo "Realm $realm_name imported successfully" || echo "Failed to import realm $realm_name" >&2

  # Update user passwords in Keycloak (covers existing realms)
  echo "Updating user passwords in Keycloak..."
  tail -n +2 "$credentials_csv" | while IFS=',' read -r email password; do
    # Strip quotes
    email=$(echo "$email" | tr -d '"')
    password=$(echo "$password" | tr -d '"')
    
    # Get user ID
    user_id=$(curl -sk --cacert "$ca_bundle" \
      -H "Authorization: Bearer $admin_token" \
      "$keycloak_url/auth/admin/realms/$realm_name/users?email=$email&max=1" \
      | python -c "import sys,json; users=json.load(sys.stdin); print(users[0]['id'] if users else '')" 2>/dev/null)
    
    if [ -n "$user_id" ]; then
      curl -sk --cacert "$ca_bundle" -X PUT \
        "$keycloak_url/auth/admin/realms/$realm_name/users/$user_id/reset-password" \
        -H "Authorization: Bearer $admin_token" \
        -H "Content-Type: application/json" \
        -d "{\"type\":\"password\",\"value\":\"$password\",\"temporary\":false}" \
        > /dev/null 2>&1 && \
        echo "  Updated password for $email" || \
        echo "  Failed to update password for $email" >&2
    else
      echo "  User not found: $email" >&2
    fi
  done
  echo "Password updates complete."
fi

# ---------------------------------------------------------------------------
# Write the seeded password to the K8s secret for downstream jobs (validation)
# ---------------------------------------------------------------------------
SA_TOKEN_FILE="/var/run/secrets/kubernetes.io/serviceaccount/token"
if [ -f "$SA_TOKEN_FILE" ]; then
  SA_TOKEN="$(cat "$SA_TOKEN_FILE")"
  SA_NAMESPACE="$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)"
  K8S_CA_CERT="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
  K8S_API="https://kubernetes.default.svc"

  seed_email="${SMOKE_LOGIN_EMAIL:-alice@jaccloud.nl}"
  seed_password="$(grep "^${seed_email}," "$credentials_csv" | cut -d',' -f2 | tr -d '"')"

  if [ -n "$seed_password" ]; then
    PASSWORD_B64="$(printf '%s' "$seed_password" | base64)"

    echo "Writing seeded password to K8s secret keycloak-user-password in $SA_NAMESPACE..."
    if curl -sk --cacert "$K8S_CA_CERT" \
      -X PUT \
      -H "Authorization: Bearer $SA_TOKEN" \
      -H "Content-Type: application/json" \
      -d "$(cat <<EOJSON
{
  "apiVersion": "v1",
  "kind": "Secret",
  "metadata": {
    "name": "keycloak-user-password",
    "namespace": "${SA_NAMESPACE}"
  },
  "type": "Opaque",
  "data": {
    "password": "${PASSWORD_B64}"
  }
}
EOJSON
)" \
      "$K8S_API/api/v1/namespaces/${SA_NAMESPACE}/secrets/keycloak-user-password"; then
      echo "K8s secret keycloak-user-password updated successfully"
    else
      echo "WARNING: Failed to update K8s secret keycloak-user-password" >&2
    fi
  else
    echo "WARNING: Could not find password for ${seed_email} in credentials CSV" >&2
  fi
else
  echo "INFO: Not running in K8s (no service account token) — skipping secret update"
fi