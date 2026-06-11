#!/usr/bin/env bash
set -euo pipefail

# Request a Keycloak token from inside the Docker Compose network using curlimages/curl.
# Usage:
#   ./scripts/patches/keycloak-compose-token.sh [--realm REALM] [--grant password|client_credentials] [--client-id ID]
# Env vars:
#   KEYCLOAK_ADMIN_USER, KEYCLOAK_ADMIN_PASSWORD (for password grant)
#   KEYCLOAK_ADMIN_SECRET (for client_credentials grant)

REALM=master
GRANT=password
CLIENT_ID=admin-cli

usage(){
  cat <<EOF
Usage: $0 [--realm REALM] [--grant password|client_credentials] [--client-id ID]

Example:
  KEYCLOAK_ADMIN_USER=admin KEYCLOAK_ADMIN_PASSWORD=secret \ 
    ./scripts/patches/keycloak-compose-token.sh --realm master --grant password

EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --realm) REALM="$2"; shift 2 ;;
    --grant) GRANT="$2"; shift 2 ;;
    --client-id) CLIENT_ID="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

project_dir=$(basename "$(pwd)")
candidate_network="${project_dir}_default"

if docker network inspect "$candidate_network" >/dev/null 2>&1; then
  NETWORK="$candidate_network"
else
  NETWORK=$(docker network ls --format '{{.Name}}' | grep -m1 "${project_dir}" || true)
fi

if [ -z "${NETWORK}" ]; then
  echo "Could not detect a Compose network for project '${project_dir}'." >&2
  echo "Available networks:" >&2
  docker network ls --format '  {{.ID}}\t{{.Name}}\t{{.Driver}}' >&2
  exit 3
fi

echo "Using Docker network: $NETWORK"

KC_URL="http://keycloak:8080/realms/${REALM}/protocol/openid-connect/token"

if [ "$GRANT" = "password" ]; then
  if [ -z "${KEYCLOAK_ADMIN_USER:-}" ] || [ -z "${KEYCLOAK_ADMIN_PASSWORD:-}" ]; then
    echo "Environment variables KEYCLOAK_ADMIN_USER and KEYCLOAK_ADMIN_PASSWORD are required for password grant." >&2
    exit 4
  fi
  echo "Requesting password grant token for user '${KEYCLOAK_ADMIN_USER}' in realm '${REALM}'..."
  docker run --rm --network "$NETWORK" curlimages/curl:8.7.1 \
    curl -v -X POST "$KC_URL" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "grant_type=password" \
      -d "client_id=${CLIENT_ID}" \
      -d "username=${KEYCLOAK_ADMIN_USER}" \
      -d "password=${KEYCLOAK_ADMIN_PASSWORD}"

elif [ "$GRANT" = "client_credentials" ]; then
  if [ -z "${KEYCLOAK_ADMIN_SECRET:-}" ]; then
    echo "Environment variable KEYCLOAK_ADMIN_SECRET is required for client_credentials grant." >&2
    exit 5
  fi
  echo "Requesting client_credentials token for client '${CLIENT_ID}' in realm '${REALM}'..."
  docker run --rm --network "$NETWORK" curlimages/curl:8.7.1 \
    curl -v -X POST "$KC_URL" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "grant_type=client_credentials" \
      -d "client_id=${CLIENT_ID}" \
      -d "client_secret=${KEYCLOAK_ADMIN_SECRET}"

else
  echo "Unsupported grant type: $GRANT" >&2
  usage
  exit 6
fi

echo "Done."
