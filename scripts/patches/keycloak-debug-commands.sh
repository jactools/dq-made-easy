#!/usr/bin/env bash
set -euo pipefail

# Helper: run Keycloak debug commands and optionally create a confidential automation client
# Usage examples:
#   ./scripts/patches/keycloak-debug-commands.sh                # run client-credentials checks (requires KEYCLOAK_ADMIN_SECRET)
#   ./scripts/patches/keycloak-debug-commands.sh --use-password # also attempt password grant (requires KEYCLOAK_ADMIN_USER/PASSWORD)
#   ./scripts/patches/keycloak-debug-commands.sh --create-client automation-client --realm master --use-password

REALM=master
USE_PASSWORD=0
CREATE_CLIENT=""

print_usage() {
  cat <<EOF
Usage: $0 [--use-password] [--create-client CLIENT_ID] [--realm REALM] [--tail-logs]

Options:
  --use-password           Attempt password grant (admin username/password) to obtain admin token.
  --create-client NAME     Create or update (idempotent) a confidential client with service account enabled.
  --realm NAME             Keycloak realm to operate in (default: master)
  --tail-logs              Tail Keycloak logs after diagnostics
  --help                   Show this help
EOF
}

TAIL_LOGS=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --use-password) USE_PASSWORD=1; shift ;;
    --create-client) CREATE_CLIENT="$2"; shift 2 ;;
    --realm) REALM="$2"; shift 2 ;;
    --tail-logs) TAIL_LOGS=1; shift ;;
    --help) print_usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; print_usage; exit 2 ;;
  esac
done

if [ -f .env ]; then
  echo "Sourcing .env..."
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
else
  echo "Warning: .env not found in cwd; ensure relevant env vars are set." >&2
fi

command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required (install it)" >&2; exit 2; }

token_client_credentials_host() {
  if [ -z "${KEYCLOAK_ADMIN_SECRET:-}" ]; then
    echo "Skipping client_credentials host request: KEYCLOAK_ADMIN_SECRET not set" >&2
    return 1
  fi
  echo
  echo "=== Verbose token request on host (client_credentials) ==="
  curl -v -X POST "http://localhost:8080/realms/${REALM}/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=client_credentials" \
    -d "client_id=admin-cli" \
    -d "client_secret=${KEYCLOAK_ADMIN_SECRET}"
}

token_client_credentials_compose() {
  if [ -z "${KEYCLOAK_ADMIN_SECRET:-}" ]; then
    echo "Skipping client_credentials compose request: KEYCLOAK_ADMIN_SECRET not set" >&2
    return 1
  fi
  echo
  echo "=== Verbose token request from inside the Compose network (client_credentials) ==="
  docker compose exec -T keycloak \
    curl -v -X POST "http://keycloak:8080/realms/${REALM}/protocol/openid-connect/token" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "grant_type=client_credentials" \
      -d "client_id=admin-cli" \
      -d "client_secret=${KEYCLOAK_ADMIN_SECRET}"
}

token_password_host() {
  if [ -z "${KEYCLOAK_ADMIN_USER:-}" ] || [ -z "${KEYCLOAK_ADMIN_PASSWORD:-}" ]; then
    echo "Skipping password grant host request: KEYCLOAK_ADMIN_USER/PASSWORD not set" >&2
    return 1
  fi
  echo
  echo "=== Verbose token request on host (password grant) ==="
  curl -v -X POST "http://localhost:8080/realms/${REALM}/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=password" \
    -d "client_id=admin-cli" \
    -d "username=${KEYCLOAK_ADMIN_USER}" \
    -d "password=${KEYCLOAK_ADMIN_PASSWORD}"
}

token_password_compose() {
  if [ -z "${KEYCLOAK_ADMIN_USER:-}" ] || [ -z "${KEYCLOAK_ADMIN_PASSWORD:-}" ]; then
    echo "Skipping password grant compose request: KEYCLOAK_ADMIN_USER/PASSWORD not set" >&2
    return 1
  fi
  echo
  echo "=== Verbose token request from inside the Compose network (password grant) ==="
  docker compose exec -T keycloak \
    curl -v -X POST "http://keycloak:8080/realms/${REALM}/protocol/openid-connect/token" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "grant_type=password" \
      -d "client_id=admin-cli" \
      -d "username=${KEYCLOAK_ADMIN_USER}" \
      -d "password=${KEYCLOAK_ADMIN_PASSWORD}"
}

create_or_update_client() {
  CLIENT_ID="$1"
  if [ -z "${ADMIN_TOKEN:-}" ]; then
    echo "ERROR: ADMIN_TOKEN not set. Run with --use-password or set ADMIN_TOKEN env." >&2
    return 2
  fi
  echo
  echo "=== Ensure client '${CLIENT_ID}' exists (idempotent) in realm '${REALM}' ==="

  # check existing
  existing=$(curl -sS -H "Authorization: Bearer ${ADMIN_TOKEN}" "http://localhost:8080/admin/realms/${REALM}/clients?clientId=${CLIENT_ID}")
  count=$(echo "$existing" | jq 'length')
  if [ "$count" -eq 0 ]; then
    echo "Client not found — creating '${CLIENT_ID}'"
    curl -sS -X POST "http://localhost:8080/admin/realms/${REALM}/clients" \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"clientId\":\"${CLIENT_ID}\",\"redirectUris\":[\"http://localhost/*\"],\"publicClient\":false,\"protocol\":\"openid-connect\",\"enabled\":true}"
    sleep 1
    existing=$(curl -sS -H "Authorization: Bearer ${ADMIN_TOKEN}" "http://localhost:8080/admin/realms/${REALM}/clients?clientId=${CLIENT_ID}")
  else
    echo "Client '${CLIENT_ID}' already present — will update config idempotently"
  fi

  CLIENT_UUID=$(echo "$existing" | jq -r '.[0].id')
  if [ -z "$CLIENT_UUID" ] || [ "$CLIENT_UUID" = "null" ]; then
    echo "ERROR: failed to resolve client UUID for ${CLIENT_ID}" >&2
    return 3
  fi

  echo "Updating client settings to enable service account and confidential auth (id=${CLIENT_UUID})"
  client_json=$(curl -sS -H "Authorization: Bearer ${ADMIN_TOKEN}" "http://localhost:8080/admin/realms/${REALM}/clients/${CLIENT_UUID}")
  updated=$(echo "$client_json" | jq '.serviceAccountsEnabled=true | .publicClient=false | .clientAuthenticatorType="client-secret"')
  curl -sS -X PUT "http://localhost:8080/admin/realms/${REALM}/clients/${CLIENT_UUID}" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$updated"

  echo "Creating/fetching client secret"
  secret_json=$(curl -sS -X POST "http://localhost:8080/admin/realms/${REALM}/clients/${CLIENT_UUID}/client-secret" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}")
  echo "Client secret: " $(echo "$secret_json" | jq -r '.value')
}

# Run diagnostics
token_client_credentials_host || true
token_client_credentials_compose || true

if [ "$USE_PASSWORD" -eq 1 ]; then
  echo
  echo "Attempting password grant to obtain admin token (for admin API operations)"
  resp=$(curl -sS -X POST "http://localhost:8080/realms/${REALM}/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=password" \
    -d "client_id=admin-cli" \
    -d "username=${KEYCLOAK_ADMIN_USER:-}" \
    -d "password=${KEYCLOAK_ADMIN_PASSWORD:-}") || true
  ADMIN_TOKEN=$(echo "$resp" | jq -r '.access_token // empty') || true
  if [ -n "${ADMIN_TOKEN:-}" ]; then
    echo "Obtained ADMIN_TOKEN via password grant"
  else
    echo "Password grant did not return an access token; response: $resp" >&2
  fi
  token_password_compose || true
fi

if [ -n "$CREATE_CLIENT" ]; then
  create_or_update_client "$CREATE_CLIENT"
fi

if [ "$TAIL_LOGS" -eq 1 ]; then
  echo
  echo "=== Tail Keycloak logs (last 500 lines) ==="
  docker compose logs --no-color --tail=500 keycloak
fi

echo
echo "Done."
