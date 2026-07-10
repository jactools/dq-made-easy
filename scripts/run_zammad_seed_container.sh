#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/workspace"
FASTAPI_DIR="$ROOT_DIR/dq-api/fastapi"
WORK_DIR="${ZAMMAD_SEED_WORK_DIR:-$ROOT_DIR/tmp/zammad-seed}"
AUTO_WIZARD_FILE="$WORK_DIR/zammad-auto-wizard.json"
GENERATED_USERS_FILE="$WORK_DIR/zammad-generated-users.csv"
SUPPORT_TOKEN_FILE="$WORK_DIR/zammad-support-token.txt"
ZAMMAD_ADMIN_CSV="$ROOT_DIR/dq-db/mock-data/zammad-admin.csv"

DQ_DB_INTERNAL_URL="${DQ_DB_INTERNAL_URL:?DQ_DB_INTERNAL_URL is required}"
APP_CONFIG_ENCRYPTION_KEY="${APP_CONFIG_ENCRYPTION_KEY:?APP_CONFIG_ENCRYPTION_KEY is required}"
ZAMMAD_PUBLIC_URL="${ZAMMAD_PUBLIC_URL:?ZAMMAD_PUBLIC_URL is required}"
KEYCLOAK_INTERNAL_URL="${KEYCLOAK_INTERNAL_URL:?KEYCLOAK_INTERNAL_URL is required}"
KEYCLOAK_ADMIN_REALM="${KEYCLOAK_ADMIN_REALM:?KEYCLOAK_ADMIN_REALM is required}"
KEYCLOAK_SYSTEM_ADMIN_USERNAME="${KEYCLOAK_SYSTEM_ADMIN_USERNAME:?KEYCLOAK_SYSTEM_ADMIN_USERNAME is required}"
KEYCLOAK_SYSTEM_ADMIN_PASSWORD="${KEYCLOAK_SYSTEM_ADMIN_PASSWORD:?KEYCLOAK_SYSTEM_ADMIN_PASSWORD is required}"
KEYCLOAK_ADMIN_USER="${KEYCLOAK_ADMIN_USER:-${KEYCLOAK_ADMIN:-}}"
KEYCLOAK_ADMIN_PASS="${KEYCLOAK_ADMIN_PASS:-${KEYCLOAK_ADMIN_PASSWORD:-}}"
KEYCLOAK_SERVER_SIDE_URL="${KEYCLOAK_SERVER_SIDE_URL:?KEYCLOAK_SERVER_SIDE_URL is required}"
SSO_PUBLIC_ISSUER_URL="${SSO_PUBLIC_ISSUER_URL:?SSO_PUBLIC_ISSUER_URL is required}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:?KEYCLOAK_REALM is required}"
ZAMMAD_OIDC_CLIENT_ID="${ZAMMAD_OIDC_CLIENT_ID:-zammad}"
ZAMMAD_OIDC_DISPLAY_NAME="${ZAMMAD_OIDC_DISPLAY_NAME:-Keycloak}"
ZAMMAD_OIDC_UID_FIELD="${ZAMMAD_OIDC_UID_FIELD:-email}"
ZAMMAD_OIDC_SCOPES="${ZAMMAD_OIDC_SCOPES:-openid email profile}"
ZAMMAD_OIDC_PKCE="${ZAMMAD_OIDC_PKCE:-true}"
ZAMMAD_SUPPORT_TOKEN_NAME="${ZAMMAD_SUPPORT_TOKEN_NAME:-dq-made-easy support integration}"
ZAMMAD_SUPPORT_TOKEN_PERMISSION="${ZAMMAD_SUPPORT_TOKEN_PERMISSION:-ticket.agent}"
ZAMMAD_SUPPORT_GROUP_NAME="${ZAMMAD_SUPPORT_GROUP_NAME:-Users}"

mkdir -p "$WORK_DIR"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/readiness.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/keycloak_readiness.sh"

my_name="run_zammad_seed_container.sh"

generate_seed_artifacts() {
  local keycloak_ready_url

  python "$ROOT_DIR/scripts/generate_zammad_autowizard.py" --output "$AUTO_WIZARD_FILE"

  keycloak_ready_url="${KEYCLOAK_INTERNAL_URL%/}/realms/${KEYCLOAK_ADMIN_REALM}/.well-known/openid-configuration"
  wait_for_keycloak_ready "$keycloak_ready_url" "Keycloak Admin Realm"

  python "$ROOT_DIR/scripts/generate_zammad_generated_users.py" \
    --source keycloak \
    --keycloak-internal-url "$KEYCLOAK_INTERNAL_URL" \
    --keycloak-admin-realm "$KEYCLOAK_ADMIN_REALM" \
    --keycloak-admin-user "$KEYCLOAK_ADMIN_USER" \
    --keycloak-admin-pass "$KEYCLOAK_ADMIN_PASS" \
    --keycloak-system-admin-username "$KEYCLOAK_SYSTEM_ADMIN_USERNAME" \
    --keycloak-system-admin-password "$KEYCLOAK_SYSTEM_ADMIN_PASSWORD" \
    --keycloak-realm "$KEYCLOAK_REALM" \
    --output "$GENERATED_USERS_FILE"
}

seed_zammad_auto_wizard() {
  local railsserver_id
  local image_name
  local env_file
  local encoded_payload

  railsserver_id="$(find_running_container_id zammad-railsserver)"
  if [ -z "$railsserver_id" ]; then
    error "$my_name" "zammad-railsserver is not running"
    exit 36
  fi

  image_name="$(docker inspect -f '{{.Config.Image}}' "$railsserver_id")"
  env_file="$WORK_DIR/zammad-service.env"
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$railsserver_id" > "$env_file"

  encoded_payload="$(base64 < "$AUTO_WIZARD_FILE" | tr -d '\n')"
  if [ -z "$encoded_payload" ]; then
    error "$my_name" "failed to encode Zammad auto wizard payload"
    exit 36
  fi

  docker run --rm \
    --env-file "$env_file" \
    -e AUTOWIZARD_JSON="$encoded_payload" \
    -e AUTOWIZARD_RELATIVE_PATH=tmp/auto_wizard.json \
    --volumes-from "$railsserver_id" \
    --network "container:$railsserver_id" \
    --user 0:0 \
    "$image_name" \
    zammad-init
}

seed_zammad_organizations() {
  local railsserver_id
  local seed_script

  railsserver_id="$(find_running_container_id zammad-railsserver)"
  seed_script="$WORK_DIR/seed_zammad_organizations.rb"

  docker cp "$GENERATED_USERS_FILE" "${railsserver_id}:/tmp/zammad-generated-users.csv"

  cat > "$seed_script" <<'RUBY'
require 'csv'
csv_file = '/tmp/zammad-generated-users.csv'
names = []
seen = {}
CSV.foreach(csv_file, headers: true) do |row|
  [row['organization'], row['organizations']].compact.each do |value|
    value.to_s.split('~~~').each do |name|
      name = name.strip
      next if name.empty? || seen[name]
      seen[name] = true
      names << name
    end
  end
end
names.each do |name|
  Organization.create_or_update(name: name, active: true, shared: true, created_by_id: 1, updated_by_id: 1)
end
puts 'Zammad organization summary:'
puts "  created_or_updated: #{names.length}"
if names.empty?
  puts '  organizations: none'
else
  puts '  organizations:'
  names.each { |name| puts "    - #{name}" }
end
exit(0)
RUBY

  docker cp "$seed_script" "${railsserver_id}:/tmp/seed_zammad_organizations.rb"
  docker exec "$railsserver_id" bundle exec rails runner /tmp/seed_zammad_organizations.rb
  docker exec --user root "$railsserver_id" rm -f /tmp/seed_zammad_organizations.rb
}

seed_zammad_generated_users() {
  local railsserver_id
  local import_script

  railsserver_id="$(find_running_container_id zammad-railsserver)"
  import_script="$WORK_DIR/import_zammad_users.rb"

  cat > "$import_script" <<'RUBY'
require 'json'
require 'csv'
csv_file = '/tmp/zammad-generated-users.csv'
result = User.csv_import(string: File.read(csv_file), parse_params: { col_sep: ',' }, try: false, delete: false)
stats = result[:stats] || {}
support_group_name = ENV.fetch('ZAMMAD_SUPPORT_GROUP_NAME')
support_group = Group.find_by(name: support_group_name)
raise "Zammad support group not found for #{support_group_name}" if support_group.nil?
role_updates = 0
agent_access_updated = 0
CSV.foreach(csv_file, headers: true) do |row|
  login = row['login'].to_s.strip.downcase
  email = row['email'].to_s.strip.downcase
  user = User.find_by(email: email)
  user ||= User.find_by(login: login)
  raise "Imported Zammad user not found for #{email}" if user.nil?

  role_names = row['roles'].to_s.split('~~~').map(&:strip).reject(&:empty?)
  desired_roles = role_names.map do |role_name|
    Role.find_by(name: role_name) || raise("Zammad role not found for #{role_name}")
  end
  current_role_names = user.roles.pluck(:name).sort
  if desired_roles.map(&:name).sort != current_role_names
    user.roles = desired_roles
    role_updates += 1
  end

  next unless role_names.include?('Agent') || role_names.include?('Admin')

  group_access_map = (user.group_names_access_map || {}).dup
  next if group_access_map[support_group_name] == ['full']

  group_access_map[support_group_name] = ['full']
  user.group_names_access_map = group_access_map
  agent_access_updated += 1
  user.save!
end
puts 'Zammad users import summary:'
puts "  result: #{result[:result]}"
puts "  created: #{stats[:created] || 0}"
puts "  updated: #{stats[:updated] || 0}"
puts "  role_updates: #{role_updates}"
puts "  agent_group_access_updated: #{agent_access_updated}"
errors = Array(result[:errors]).compact
if errors.empty?
  puts '  errors: none'
else
  puts '  errors:'
  errors.each { |error| puts "    - #{error}" }
end
exit(result[:result] == 'success' ? 0 : 1)
RUBY

  docker cp "$import_script" "${railsserver_id}:/tmp/import_zammad_users.rb"
  docker exec \
    -e ZAMMAD_SUPPORT_GROUP_NAME="$ZAMMAD_SUPPORT_GROUP_NAME" \
    "$railsserver_id" \
    bundle exec rails runner /tmp/import_zammad_users.rb
  docker exec --user root "$railsserver_id" rm -f /tmp/import_zammad_users.rb
}

read_zammad_admin_email() {
  python - "$ZAMMAD_ADMIN_CSV" <<'PY'
import csv
import sys
from pathlib import Path

path = Path(sys.argv[1])
with path.open(newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))

if len(rows) != 1:
    raise SystemExit(f"Expected exactly one admin row in {path}, found {len(rows)}")

email = str(rows[0].get("email") or "").strip()
if not email:
    raise SystemExit(f"Admin CSV row is missing email: {path}")

print(email)
PY
}

provision_zammad_support_token() {
  local railsserver_id
  local token_script
  local admin_email

  railsserver_id="$(find_running_container_id zammad-railsserver)"
  token_script="$WORK_DIR/provision_zammad_support_token.rb"
  admin_email="$(read_zammad_admin_email)"

  cat > "$token_script" <<'RUBY'
admin_email = ENV.fetch('ZAMMAD_ADMIN_EMAIL')
token_name = ENV.fetch('ZAMMAD_SUPPORT_TOKEN_NAME')
token_permission = ENV.fetch('ZAMMAD_SUPPORT_TOKEN_PERMISSION')
support_group_name = ENV.fetch('ZAMMAD_SUPPORT_GROUP_NAME')
user = User.find_by(email: admin_email.downcase.strip) || User.find_by(login: admin_email.downcase.strip)
raise "Zammad admin user not found for #{admin_email}" if user.nil?
group = Group.find_by(name: support_group_name)
raise "Zammad support group not found for #{support_group_name}" if group.nil?
group_access_map = (user.group_names_access_map || {}).dup
group_access_map[support_group_name] = 'full'
user.group_names_access_map = group_access_map
user.save!
Token.where(action: 'api', user_id: user.id, name: token_name).destroy_all
token = Service::User::AccessToken::Create.new(user, name: token_name, permission: [token_permission]).execute
File.write('/tmp/zammad-support-token.txt', token.token)
RUBY

  docker cp "$token_script" "${railsserver_id}:/tmp/provision_zammad_support_token.rb"
  docker exec \
    -e ZAMMAD_ADMIN_EMAIL="$admin_email" \
    -e ZAMMAD_SUPPORT_TOKEN_NAME="$ZAMMAD_SUPPORT_TOKEN_NAME" \
    -e ZAMMAD_SUPPORT_TOKEN_PERMISSION="$ZAMMAD_SUPPORT_TOKEN_PERMISSION" \
    -e ZAMMAD_SUPPORT_GROUP_NAME="$ZAMMAD_SUPPORT_GROUP_NAME" \
    "$railsserver_id" \
    bundle exec rails runner /tmp/provision_zammad_support_token.rb

  docker cp "${railsserver_id}:/tmp/zammad-support-token.txt" "$SUPPORT_TOKEN_FILE"
  docker exec --user root "$railsserver_id" rm -f /tmp/provision_zammad_support_token.rb /tmp/zammad-support-token.txt

  DQ_API_ROOT="$FASTAPI_DIR" DQ_DB_INTERNAL_URL="$DQ_DB_INTERNAL_URL" APP_CONFIG_ENCRYPTION_KEY="$APP_CONFIG_ENCRYPTION_KEY" \
    python "$ROOT_DIR/dq-api/scripts/update_support_itsm_token.py" --token-file "$SUPPORT_TOKEN_FILE"
}

configure_zammad_openid_connect() {
  local railsserver_id
  local oidc_script
  local callback_url

  railsserver_id="$(find_running_container_id zammad-railsserver)"
  if [ -z "$railsserver_id" ]; then
    error "$my_name" "zammad-railsserver is not running"
    exit 36
  fi

  callback_url="${ZAMMAD_PUBLIC_URL%/}/auth/openid_connect/callback"
  oidc_script="$WORK_DIR/configure_zammad_openid_connect.rb"

  cat > "$oidc_script" <<'RUBY'
require 'uri'

public_url = ENV.fetch('ZAMMAD_PUBLIC_URL')
public_uri = URI.parse(public_url)
public_fqdn = public_uri.host
public_fqdn = "#{public_fqdn}:#{public_uri.port}" if public_uri.port != public_uri.default_port

issuer = ENV.fetch('SSO_PUBLIC_ISSUER_URL')
client_id = ENV.fetch('ZAMMAD_OIDC_CLIENT_ID')
display_name = ENV.fetch('ZAMMAD_OIDC_DISPLAY_NAME')
uid_field = ENV.fetch('ZAMMAD_OIDC_UID_FIELD')
scopes = ENV.fetch('ZAMMAD_OIDC_SCOPES')
pkce = ENV.fetch('ZAMMAD_OIDC_PKCE') == 'true'
callback_url = ENV.fetch('ZAMMAD_OIDC_CALLBACK_URL')

Setting.set('auth_openid_connect', true)
Setting.set('http_type', public_uri.scheme)
Setting.set('fqdn', public_fqdn)
Setting.set('auth_openid_connect_credentials', {
  display_name: display_name,
  identifier: client_id,
  issuer: issuer,
  uid_field: uid_field,
  scope: scopes,
  pkce: pkce,
  callback_url: callback_url,
})
Setting.set('auth_third_party_auto_link_at_inital_login', true)

puts 'Zammad OpenID Connect settings updated:'
puts "  http_type: #{public_uri.scheme}"
puts "  fqdn: #{public_fqdn}"
puts "  issuer: #{issuer}"
puts "  client_id: #{client_id}"
puts "  callback_url: #{callback_url}"
puts '  auto_link_at_initial_login: true'
RUBY

  docker cp "$oidc_script" "${railsserver_id}:/tmp/configure_zammad_openid_connect.rb"
  docker exec \
    -e ZAMMAD_PUBLIC_URL="$ZAMMAD_PUBLIC_URL" \
    -e SSO_PUBLIC_ISSUER_URL="$SSO_PUBLIC_ISSUER_URL" \
    -e ZAMMAD_OIDC_CLIENT_ID="$ZAMMAD_OIDC_CLIENT_ID" \
    -e ZAMMAD_OIDC_DISPLAY_NAME="$ZAMMAD_OIDC_DISPLAY_NAME" \
    -e ZAMMAD_OIDC_UID_FIELD="$ZAMMAD_OIDC_UID_FIELD" \
    -e ZAMMAD_OIDC_SCOPES="$ZAMMAD_OIDC_SCOPES" \
    -e ZAMMAD_OIDC_PKCE="$ZAMMAD_OIDC_PKCE" \
    -e ZAMMAD_OIDC_CALLBACK_URL="$callback_url" \
    "$railsserver_id" \
    bundle exec rails runner /tmp/configure_zammad_openid_connect.rb
  docker exec --user root "$railsserver_id" rm -f /tmp/configure_zammad_openid_connect.rb
}

reconcile_zammad_system_setup_state() {
  local railsserver_id
  local setup_script

  railsserver_id="$(find_running_container_id zammad-railsserver)"
  if [ -z "$railsserver_id" ]; then
    error "$my_name" "zammad-railsserver is not running"
    exit 36
  fi

  setup_script="$WORK_DIR/reconcile_zammad_system_setup_state.rb"

  cat > "$setup_script" <<'RUBY'
setup = Service::System::CheckSetup.new
setup.execute
puts "Zammad system setup status: #{setup.status}"
puts "Zammad system setup type: #{setup.type}"
puts "Zammad system_init_done: #{Setting.get('system_init_done')}"
RUBY

  docker cp "$setup_script" "${railsserver_id}:/tmp/reconcile_zammad_system_setup_state.rb"
  docker exec "$railsserver_id" bundle exec rails runner /tmp/reconcile_zammad_system_setup_state.rb
  docker exec --user root "$railsserver_id" rm -f /tmp/reconcile_zammad_system_setup_state.rb
}

info "$my_name" "Containerized Zammad seed starting"
if ! wait_for_zammad_support_services_ready 60 2; then
  error "$my_name" "Zammad support services did not become ready in time"
  exit 36
fi
if ! wait_for_zammad_app_database_ready "$DQ_DB_INTERNAL_URL" 60 2; then
  error "$my_name" "Application database did not become ready in time"
  exit 36
fi
generate_seed_artifacts

info "$my_name" "Running Zammad auto wizard seed..."
seed_zammad_auto_wizard

info "$my_name" "Seeding Zammad organizations..."
seed_zammad_organizations

info "$my_name" "Importing Zammad users..."
seed_zammad_generated_users

info "$my_name" "Provisioning Zammad support token..."
provision_zammad_support_token

info "$my_name" "Configuring Zammad OpenID Connect..."
configure_zammad_openid_connect

info "$my_name" "Reconciling Zammad system setup state..."
reconcile_zammad_system_setup_state

success "$my_name" "Containerized Zammad seed completed successfully"