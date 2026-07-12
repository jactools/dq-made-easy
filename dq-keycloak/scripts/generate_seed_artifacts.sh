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

printf '.'
printf '.'
printf '.'
printf '.'
printf '.'
printf '.'
printf '.'
printf '.'
printf '.'
printf '.'