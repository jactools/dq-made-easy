#!/usr/bin/env bash
set -euo pipefail


# Purpose: Interactive debug helper for /admin/v1/me and JWT/session lookups.
#
# What it does:
# - Calls /admin/v1/me with a provided ACCESS_TOKEN.
# - Decodes the JWT payload locally.
# - Optionally queries Postgres and tails API logs for related events.
#
# Version: 1.0
# Last modified: 2026-04-07

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/supporting/logging.sh"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/supporting/root_env_file.sh"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/supporting/compose/invocation.sh"

my_name="debug_auth_me.sh"

info "$my_name" "Debug helper: check /admin/v1/me, decode token, and query DB rows."
info "$my_name" "Press Ctrl-C to cancel at any prompt."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_RUNNER="${SCRIPT_DIR}/python_arm64.sh"
init_root_env_file "$ROOT_DIR"

if [ ! -f "$ROOT_ENV_FILE" ]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full
KONG_LOCAL_URL="${KONG_LOCAL_URL:-}"
KONG_CA_CERT="${KONG_CA_CERT:-$ROOT_DIR/tmp/certs/mkcert-rootCA.pem}"
if [ -f "$KONG_CA_CERT" ] && [ -z "${CURL_CA_BUNDLE:-}" ]; then
  export CURL_CA_BUNDLE="$KONG_CA_CERT"
fi

if [ -n "${ACCESS_TOKEN:-}" ]; then
  info "$my_name" "Using ACCESS_TOKEN provided in environment"
else
  read -rp "Paste ACCESS_TOKEN (keep it private) and press Enter: " ACCESS_TOKEN
  info "$my_name" ""
fi

info "$my_name" "== /admin/v1/me response =="
# Request body only (avoid printing headers which breaks jq)
if [ -z "${KONG_LOCAL_URL:-}" ]; then
  error "$my_name" "KONG_LOCAL_URL must be set to query /admin/v1/me"
  exit 1
fi
curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" "${KONG_LOCAL_URL%/}/admin/v1/me" | jq . || { info "$my_name" "(/admin/v1/me not JSON or empty)"; }
info "$my_name" ""

info "$my_name" "== Decoded token payload =="
"$PYTHON_RUNNER" --python-bin python3 - <<'PY'
import os,sys,json,base64
t=os.environ.get('ACCESS_TOKEN','')
if not t:
    print('ACCESS_TOKEN empty', file=sys.stderr); sys.exit(1)
parts=t.split('.')
if len(parts)<2:
    print('token invalid', file=sys.stderr); sys.exit(1)
seg=parts[1]
pad='='*((4-len(seg)%4)%4)
try:
    raw=base64.urlsafe_b64decode(seg+pad)
    parsed=json.loads(raw)
    print(json.dumps(parsed, indent=2))
except Exception as e:
    print('Failed to decode token payload:', e, file=sys.stderr); sys.exit(1)
PY
info "$my_name" ""

read -rp "If you got a user id from /admin/v1/me, paste it here (or leave empty to skip): " USER_ID
if [ -n "${USER_ID}" ]; then
  info "$my_name" ""
  info "$my_name" "== users row for ${USER_ID} =="
  docker_compose exec -T db psql -U postgres -d dq -c "SELECT id,name,email,external_id,workspaces,preferences FROM users WHERE id = '${USER_ID}';" || true
  info "$my_name" ""
  info "$my_name" "== user_roles for ${USER_ID} =="
  docker_compose exec -T db psql -U postgres -d dq -c "SELECT role_id FROM user_roles WHERE user_id = '${USER_ID}' ORDER BY role_id;" || true
  info "$my_name" ""
fi

read -rp "If the token had a sid claim, paste SID here (or leave empty to skip): " SID
if [ -n "${SID}" ]; then
  info "$my_name" ""
  info "$my_name" "== app_sessions for ${SID} =="
  # Check for table existence first to avoid noisy errors on different schemas
  EXISTS=$(docker_compose exec -T db psql -U postgres -d dq -tAc "SELECT to_regclass('public.app_sessions');" || true)
  if [ "${EXISTS}" = "app_sessions" ]; then
    docker_compose exec -T db psql -U postgres -d dq -c "SELECT id,user_id,last_activity FROM app_sessions WHERE id = '${SID}';" || true
  else
    info "$my_name" "app_sessions table not present; skipping session lookup"
  fi
  info "$my_name" ""
fi

info "$my_name" "== Tail api logs (last 200 lines) grep auth/me events =="
docker_compose logs --no-color --tail=200 api | grep -E "admin.me.get|auth.callback|auth.login" -n || true

success "$my_name" "Done."
