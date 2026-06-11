#!/usr/bin/env bash
set -euo pipefail

# Smoke test for the docker "stack" dev environment.
# Checks: Keycloak (HTTP + realm import via kcadm), API, and frontend availability.

RETRIES=30
SLEEP=2

KC_URL="${KEYCLOAK_LOCAL_URL:-http://localhost:8080}"
API_URL="${DQ_API_LOCAL_URL:-http://localhost:4010}"
UI_URL="${UI_NGINX_LOCAL_URL:-${UI_VITE_LOCAL_URL:-http://localhost:5173}}"
REALM=jaccloud

function wait_for_http() {
  local url=$1
  local tries=0
  while [ $tries -lt $RETRIES ]; do
    status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "$url" || echo 000)
    if [ "$status" != "000" ]; then
      echo "$url -> HTTP $status"
      return 0
    fi
    tries=$((tries+1))
    sleep $SLEEP
  done
  echo "Timed out waiting for $url"
  return 1
}

echo "Checking Keycloak at $KC_URL"
wait_for_http "$KC_URL"

echo "Checking API at $API_URL"
wait_for_http "$API_URL"

echo "Checking UI at $UI_URL"
wait_for_http "$UI_URL"

# Locate Keycloak container (heuristic: name contains 'keycloak')
KC_CONTAINER=$(docker ps --format '{{.ID}} {{.Names}}' | awk '/[Kk]eycloak/ {print $1; exit}' || true)
if [ -z "$KC_CONTAINER" ]; then
  echo "Keycloak container not found via docker ps; skipping kcadm checks."
  exit 0
fi

echo "Found Keycloak container: $KC_CONTAINER"

# Check for kcadm.sh inside the container
if docker exec "$KC_CONTAINER" test -x /opt/keycloak/bin/kcadm.sh >/dev/null 2>&1; then
  echo "kcadm.sh found in container; configuring admin credentials..."
  printf '.'
  docker exec "$KC_CONTAINER" /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 --realm master --user admin --password admin >/dev/null 2>&1

  echo "Checking realm '$REALM' via kcadm..."
  if docker exec "$KC_CONTAINER" /opt/keycloak/bin/kcadm.sh get realms/$REALM >/dev/null 2>&1; then
    echo "Realm '$REALM' exists."
  else
    echo "Realm '$REALM' not found; attempting import via kcadm create..."
    if docker exec "$KC_CONTAINER" /opt/keycloak/bin/kcadm.sh create realms -f /opt/keycloak/data/import/${REALM}-realm.json >/dev/null 2>&1; then
      echo "Import command completed; proceeding to verification."
    else
      echo "kcadm import command failed. Check container logs for details." >&2
      exit 2
    fi
  fi

  # Verify users and roles exist for the realm
  USERS_JSON=$(docker exec "$KC_CONTAINER" /opt/keycloak/bin/kcadm.sh get users -r $REALM 2>/dev/null || true)
  if [ -z "$USERS_JSON" ] || [ "$USERS_JSON" = "[]" ]; then
    echo "No users found in realm '$REALM' (or fetch failed)." >&2
    exit 3
  else
    echo "Users present in realm '$REALM'."
  fi

  ROLES_JSON=$(docker exec "$KC_CONTAINER" /opt/keycloak/bin/kcadm.sh get roles -r $REALM 2>/dev/null || true)
  if [ -z "$ROLES_JSON" ] || [ "$ROLES_JSON" = "[]" ]; then
    echo "No roles found in realm '$REALM' (or fetch failed)." >&2
    exit 4
  else
    echo "Roles present in realm '$REALM'."
  fi

  echo "Keycloak realm and import verification succeeded."
  # Ensure the dq-rules-ui service account has the required realm-management role
  ENSURE_SCRIPT="$ROOT_DIR/scripts/keycloak/ensure_service_account_role.sh"
  if [ -x "$ENSURE_SCRIPT" ]; then
    echo "Ensuring service-account role mapping for dq-rules-ui..."
    KEYCLOAK_LOCAL_URL="$KC_URL" \
      KEYCLOAK_ADMIN_USER="${KEYCLOAK_ADMIN:-admin}" \
      KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}" \
      KEYCLOAK_ADMIN_REALM=master \
      KEYCLOAK_TARGET_REALM="$REALM" \
      SERVICE_CLIENT_ID="dq-rules-ui" \
      ROLE_NAME="view-users" \
      bash "$ENSURE_SCRIPT" || echo "Warning: ensure_service_account_role.sh failed (check logs)"
  else
    echo "ensure_service_account_role.sh not found or not executable; skipping service-account role enforcement"
  fi
else
  echo "kcadm.sh not found in Keycloak container; skipping realm import verification."
fi

echo "Smoke test completed successfully."
exit 0
