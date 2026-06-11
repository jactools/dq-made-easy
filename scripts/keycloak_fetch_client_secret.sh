#!/usr/bin/env bash
set -euo pipefail


# Purpose: Fetch (and convert if needed) a Keycloak client's secret.
#
# What it does:
# - Supports docker-compose kcadm or host-side REST API method.
# - Converts a public client to confidential when needed.
# - Prints the resolved client secret to stdout.
#
# Version: 1.0
# Last modified: 2026-04-07

usage() {
  printf '%s\n' \
    "Usage: $0 [-m method] -r REALM -c CLIENT_ID -u ADMIN_USER -p ADMIN_PASS" \
    "" \
    "Fetch (and convert if needed) a Keycloak client's secret." \
    "" \
    "Options:" \
    "  -m method        Method to use: kcadm (default) or rest" \
    "  -r REALM         Keycloak realm (e.g. jaccloud)" \
    "  -c CLIENT_ID     Client ID (e.g. dq-rules-ui)" \
    "  -u ADMIN_USER    Keycloak admin username (master realm)" \
    "  -p ADMIN_PASS    Keycloak admin password (master realm)" \
    "" \
    "Examples:" \
    "  # Using kcadm via docker-compose" \
    "  ./scripts/keycloak_fetch_client_secret.sh -m kcadm -r jaccloud -c dq-rules-ui -u admin -p admin" \
    "" \
    "  # Using REST from host" \
    "  ./scripts/keycloak_fetch_client_secret.sh -m rest -r jaccloud -c dq-rules-ui -u admin -p admin"
}

METHOD="kcadm"
REALM=""
CLIENT_ID=""
ADMIN_USER=""
ADMIN_PASS=""

while getopts ":m:r:c:u:p:h" opt; do
  case ${opt} in
    m ) METHOD=${OPTARG} ;;
    r ) REALM=${OPTARG} ;;
    c ) CLIENT_ID=${OPTARG} ;;
    u ) ADMIN_USER=${OPTARG} ;;
    p ) ADMIN_PASS=${OPTARG} ;;
    h ) usage; exit 0 ;;
    \? ) echo "Invalid Option: -$OPTARG" 1>&2; usage; exit 1 ;;
  esac
done

if [[ -z "$REALM" || -z "$CLIENT_ID" || -z "$ADMIN_USER" || -z "$ADMIN_PASS" ]]; then
  echo "Missing required arguments." >&2
  usage
  exit 2
fi

KEYCLOAK_HOST=${KEYCLOAK_HOST:-127.0.0.1}
KEYCLOAK_PORT=${KEYCLOAK_PORT:-8080}
BASE_URL="http://${KEYCLOAK_HOST}:${KEYCLOAK_PORT}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Required command '$1' not found" >&2; exit 3; }
}

if [[ "$METHOD" == "kcadm" ]]; then
  require_cmd docker
  require_cmd jq

  source "$ROOT_DIR/scripts/supporting/logging.sh"
  source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
  source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
  init_root_env_file "$ROOT_DIR"

  if [ ! -f "$ROOT_ENV_FILE" ]; then
    error "keycloak_fetch_client_secret.sh" "Env file not found: $ROOT_ENV_FILE"
    exit 1
  fi

  validate_selected_root_env_file "$ROOT_DIR" full

  info "keycloak_fetch_client_secret.sh" "Using kcadm (docker compose) method against $BASE_URL"

  # Authenticate kcadm against master realm
  docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh config credentials \
    --server "${BASE_URL}" --realm master --user "${ADMIN_USER}" --password "${ADMIN_PASS}" >/dev/null 2>&1

  # Get client UUID
  CLIENT_JSON=$(docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get clients -r "${REALM}" -q clientId="${CLIENT_ID}")
  CLIENT_UUID=$(echo "$CLIENT_JSON" | jq -r '.[0].id')
  if [[ -z "$CLIENT_UUID" || "$CLIENT_UUID" == "null" ]]; then
    echo "Client '${CLIENT_ID}' not found in realm '${REALM}'" >&2
    exit 4
  fi

  echo "Found client UUID: $CLIENT_UUID"

  # Check if public. If public, convert to confidential
  IS_PUBLIC=$(echo "$CLIENT_JSON" | jq -r '.[0].publicClient')
  if [[ "$IS_PUBLIC" == "true" ]]; then
    info "keycloak_fetch_client_secret.sh" "Client is public - converting to confidential and enabling direct access grants"
    docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh update clients/${CLIENT_UUID} -r "${REALM}" \
      -s publicClient=false -s clientAuthenticatorType=client-secret -s directAccessGrantsEnabled=true
  else
    info "keycloak_fetch_client_secret.sh" "Client already confidential"
  fi

  # Fetch secret
  SECRET_JSON=$(docker_compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get clients/${CLIENT_UUID}/client-secret -r "${REALM}")
  SECRET=$(echo "$SECRET_JSON" | jq -r .value)
  printf '%s\n' "$SECRET"
  exit 0

elif [[ "$METHOD" == "rest" ]]; then
  require_cmd curl
  require_cmd jq

  echo "Using Admin REST API method against $BASE_URL"

  # Obtain admin token from master realm
  TOKEN=$(curl -s -X POST "${BASE_URL}/realms/master/protocol/openid-connect/token" \
    -d "grant_type=password&client_id=admin-cli&username=${ADMIN_USER}&password=${ADMIN_PASS}" | jq -r .access_token)
  if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
    echo "Failed to obtain admin token" >&2
    exit 5
  fi

  CLIENT_ID_UUID=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
    "${BASE_URL}/admin/realms/${REALM}/clients?clientId=${CLIENT_ID}" | jq -r '.[0].id')
  if [[ -z "$CLIENT_ID_UUID" || "$CLIENT_ID_UUID" == "null" ]]; then
    echo "Client '${CLIENT_ID}' not found in realm '${REALM}'" >&2
    exit 6
  fi

  echo "Found client UUID: $CLIENT_ID_UUID"

  # Check if public and convert if needed
  IS_PUBLIC=$(curl -s -H "Authorization: Bearer ${TOKEN}" "${BASE_URL}/admin/realms/${REALM}/clients/${CLIENT_ID_UUID}" | jq -r .publicClient)
  if [[ "$IS_PUBLIC" == "true" ]]; then
    echo "Client is public — converting to confidential and enabling direct access grants (REST)"
    curl -s -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
      "${BASE_URL}/admin/realms/${REALM}/clients/${CLIENT_ID_UUID}" \
      -d '{"publicClient":false,"clientAuthenticatorType":"client-secret","directAccessGrantsEnabled":true}'
  else
    echo "Client already confidential"
  fi

  # Get client secret
  SECRET=$(curl -s -H "Authorization: Bearer ${TOKEN}" "${BASE_URL}/admin/realms/${REALM}/clients/${CLIENT_ID_UUID}/client-secret" | jq -r .value)
  echo "$SECRET"
  exit 0

else
  echo "Unknown method: ${METHOD}" >&2
  usage
  exit 7
fi
