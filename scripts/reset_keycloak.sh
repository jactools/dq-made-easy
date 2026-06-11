#!/usr/bin/env bash
set -euo pipefail

# Purpose: Back up Keycloak data volume(s), remove stale data, restart Keycloak
#          and ensure the realm JWKS contains RSA signing keys required by Kong.
# What it does:
#  - Back up any compose volumes matching `keycloak_data` or `*_keycloak_data`
#  - Stop and remove the Keycloak service/container
#  - Remove the identified Keycloak volume(s)
#  - Start Keycloak via docker compose (auto-import of realm is expected)
#  - Poll the Keycloak JWKS and, if missing, attempt an Admin-API realm import
# Version: 0.1.0
# Last modified: 2026-04-13

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$ROOT/tmp/keycloak-backup"
LOGFILE="$ROOT/tmp/keycloak_reset.log"
REALM_JSON="$ROOT/dq-keycloak/jaccloud-realm.json"
PYTHON_RUNNER="$ROOT/scripts/python_arm64.sh"

source "$ROOT/scripts/supporting/logging.sh"
source "$ROOT/scripts/supporting/root_env_file.sh"
source "$ROOT/scripts/supporting/compose/invocation.sh"
init_root_env_file "$ROOT"

if [ ! -f "$ROOT_ENV_FILE" ]; then
  error "reset_keycloak.sh" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT" full

mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname "$LOGFILE")"

echo "Logging to $LOGFILE"
exec > >(tee -a "$LOGFILE") 2>&1

info "reset_keycloak.sh" "== Keycloak reset helper =="

TS=$(date +%Y%m%d_%H%M%S)

info "reset_keycloak.sh" "Looking for keycloak-related Docker volumes..."
VOLUMES=$(docker volume ls -q | grep -E '(^keycloak_data$|_keycloak_data$)' || true)
if [ -z "$VOLUMES" ]; then
  info "reset_keycloak.sh" "No 'keycloak_data' volumes found. Listing all volumes for inspection:"
  docker volume ls || true
else
  for v in $VOLUMES; do
    BACKUP_FILE="$BACKUP_DIR/${v}_backup_${TS}.tgz"
    info "reset_keycloak.sh" "Backing up volume $v -> $BACKUP_FILE"
    docker run --rm -v "$v":/data alpine sh -c 'cd /data && tar czf - .' > "$BACKUP_FILE"
    info "reset_keycloak.sh" "Saved: $BACKUP_FILE"
  done
fi

info "reset_keycloak.sh" "Stopping and removing Keycloak service/container (compose service 'keycloak')"
docker_compose stop keycloak || true
docker_compose rm -f keycloak || true

if [ -n "$VOLUMES" ]; then
  info "reset_keycloak.sh" "Removing volumes: $VOLUMES"
  for v in $VOLUMES; do
    docker volume rm "$v" || true
  done
else
  info "reset_keycloak.sh" "No volumes to remove."
fi

info "reset_keycloak.sh" "Starting Keycloak (compose service 'keycloak')"
docker_compose up -d keycloak

info "reset_keycloak.sh" "Polling JWKS for realm 'jaccloud' (120s timeout)..."
found=0
for i in $(seq 1 40); do
  sleep 3
  printf '.'
  # Try HTTP first
  rsa_count=$(curl -sS http://localhost:8080/realms/jaccloud/protocol/openid-connect/certs 2>/dev/null | "$PYTHON_RUNNER" --python-bin python3 - <<'PY'
import sys, json
s=sys.stdin.read()
try:
    j=json.loads(s)
except Exception:
    print(0)
    sys.exit(0)
print(sum(1 for k in j.get('keys',[]) if k.get('kty')=='RSA'))
PY
)
  if [ "${rsa_count:-0}" -gt 0 ]; then
    printf '\n'
    info "reset_keycloak.sh" "Found RSA JWKS via HTTP (count=${rsa_count})"
    found=1
    break
  fi

  # Try HTTPS (ignoring self-signed certs)
  rsa_count=$(curl -skS https://localhost:9444/realms/jaccloud/protocol/openid-connect/certs 2>/dev/null | "$PYTHON_RUNNER" --python-bin python3 - <<'PY'
import sys, json
s=sys.stdin.read()
try:
    j=json.loads(s)
except Exception:
    print(0)
    sys.exit(0)
print(sum(1 for k in j.get('keys',[]) if k.get('kty')=='RSA'))
PY
)
  if [ "${rsa_count:-0}" -gt 0 ]; then
    printf '\n'
    info "reset_keycloak.sh" "Found RSA JWKS via HTTPS (count=${rsa_count})"
    found=1
    break
  fi
done
printf '\n'

if [ "$found" -eq 1 ]; then
  success "reset_keycloak.sh" "Keycloak JWKS contains RSA signing key(s)."
  exit 0
fi

warning "reset_keycloak.sh" "JWKS does not contain RSA keys. Attempting Admin API realm import."
if [ ! -f "$REALM_JSON" ]; then
  error "reset_keycloak.sh" "Realm JSON not found at $REALM_JSON. Cannot import. Exiting."
  exit 2
fi

info "reset_keycloak.sh" "Requesting admin token (HTTPS, ignoring cert verification)."
TOKEN=$(curl -skS -X POST 'https://localhost:9444/realms/master/protocol/openid-connect/token' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=password&client_id=admin-cli&username=admin&password=admin' | "$PYTHON_RUNNER" --python-bin python3 - <<'PY'
import sys, json
try:
    j=json.load(sys.stdin)
    print(j.get('access_token') or '')
except Exception:
    print('')
PY
)

if [ -z "$TOKEN" ]; then
  error "reset_keycloak.sh" "Failed to obtain admin token. Ensure admin credentials are correct and Keycloak is reachable."
  exit 3
fi

info "reset_keycloak.sh" "Importing realm via Admin API"
HTTP=$(curl -sk -o /tmp/realm_import_resp -w "%{http_code}" -X POST "https://localhost:9444/admin/realms" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" --data-binary @"$REALM_JSON" || true)
info "reset_keycloak.sh" "HTTP status: $HTTP"
if [ -s /tmp/realm_import_resp ]; then
  info "reset_keycloak.sh" "Response body:"
  sed -n '1,200p' /tmp/realm_import_resp || true
fi

info "reset_keycloak.sh" "Polling JWKS again (30s)..."
for i in $(seq 1 10); do
  sleep 3
  rsa_count=$(curl -skS https://localhost:9444/realms/jaccloud/protocol/openid-connect/certs 2>/dev/null | "$PYTHON_RUNNER" --python-bin python3 - <<'PY'
import sys, json
s=sys.stdin.read()
try:
    j=json.loads(s)
except Exception:
    print(0)
    sys.exit(0)
print(sum(1 for k in j.get('keys',[]) if k.get('kty')=='RSA'))
PY
)
  if [ "${rsa_count:-0}" -gt 0 ]; then
    echo "Found RSA keys (count=${rsa_count}). Success."
    curl -skS https://localhost:9444/realms/jaccloud/protocol/openid-connect/certs | jq . || true
    exit 0
  fi
done

echo "Failed to obtain RSA JWKS after realm import. Check Keycloak logs and container status." >&2
exit 4
