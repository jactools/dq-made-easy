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

python - "$rotated_users_csv" "$credentials_csv" "$credentials_env" "$workspace_rotated_users_csv" "$workspace_credentials_csv" "$workspace_credentials_env" <<'PY'
import csv
import os
import secrets
import string
import sys
from pathlib import Path

source = Path("/app/mock-data/users.csv")
rotated_users = Path(sys.argv[1])
credentials_csv = Path(sys.argv[2])
credentials_env = Path(sys.argv[3])
workspace_rotated_users = Path(sys.argv[4])
workspace_credentials_csv = Path(sys.argv[5])
workspace_credentials_env = Path(sys.argv[6])

allowed_password_chars = string.ascii_letters + string.digits + "-_"


def rotated_password():
  return "".join(secrets.choice(allowed_password_chars) for _ in range(32))


def shell_quote(value):
  text = str(value or "")
  return "'" + text.replace("'", "'\"'\"'") + "'"


with source.open(newline="", encoding="utf-8") as handle:
  reader = csv.DictReader(handle)
  fieldnames = list(reader.fieldnames or [])
  if "password" not in fieldnames:
    raise SystemExit(f"{source} is missing required password column")
  rows = list(reader)

seen_passwords = set()
for row in rows:
  email = (row.get("email") or "").strip()
  if not email:
    continue
  next_password = rotated_password()
  while next_password in seen_passwords:
    next_password = rotated_password()
  seen_passwords.add(next_password)
  row["password"] = next_password

rotated_users.parent.mkdir(parents=True, exist_ok=True)
with rotated_users.open("w", newline="", encoding="utf-8") as handle:
  writer = csv.DictWriter(handle, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, lineterminator="\n")
  writer.writeheader()
  writer.writerows(rows)

with credentials_csv.open("w", newline="", encoding="utf-8") as handle:
  writer = csv.DictWriter(handle, fieldnames=["email", "password"], quoting=csv.QUOTE_ALL, lineterminator="\n")
  writer.writeheader()
  for row in rows:
    email = (row.get("email") or "").strip()
    if email:
      writer.writerow({"email": email, "password": row["password"]})

credential_aliases = [
  ("KEYCLOAK_JACCLOUD_USERNAME", "KEYCLOAK_JACCLOUD_PASSWORD", (os.environ.get("KEYCLOAK_JACCLOUD_USERNAME") or "").strip()),
  ("SMOKE_LOGIN_EMAIL", "SMOKE_LOGIN_PASSWORD", (os.environ.get("SMOKE_LOGIN_EMAIL") or "").strip()),
  ("OPERATOR_LOGIN_EMAIL", "OPERATOR_LOGIN_PASSWORD", (os.environ.get("OPERATOR_LOGIN_EMAIL") or "").strip()),
  ("AUDITOR_LOGIN_EMAIL", "AUDITOR_LOGIN_PASSWORD", (os.environ.get("AUDITOR_LOGIN_EMAIL") or "").strip()),
  ("REGULATOR_LOGIN_EMAIL", "REGULATOR_LOGIN_PASSWORD", (os.environ.get("REGULATOR_LOGIN_EMAIL") or "").strip()),
]
password_by_email = {(row.get("email") or "").strip(): row.get("password") for row in rows}
with credentials_env.open("w", encoding="utf-8") as handle:
  handle.write("# Generated by dq-keycloak/scripts/generate_seed_artifacts.sh\n")
  handle.write("# Do not commit. Credentials rotate on each seed-artifacts run.\n")
  for username_key, password_key, selected_email in credential_aliases:
    if not selected_email:
      continue
    if selected_email not in password_by_email:
      raise SystemExit(f"{username_key} not found in users.csv: {selected_email}")
    handle.write(f"{username_key}={shell_quote(selected_email)}\n")
    handle.write(f"{password_key}={shell_quote(password_by_email[selected_email])}\n")

try:
  os.chown(credentials_csv, 1000, 0)
  os.chown(credentials_env, 1000, 0)
  os.chmod(credentials_csv, 0o640)
  os.chmod(credentials_env, 0o640)
except Exception:
  pass

import sys
sys.stderr.write('.')
sys.stderr.flush()
PY

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