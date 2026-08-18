#!/usr/bin/env bash
set -euo pipefail

# ========================================================================
# dq-role-assignment
# Uses the tenant-admin service account to create DQ roles, assign them
# to users, and configure DQ OIDC clients in the Keycloak realm.
# ========================================================================

KEYCLOAK_URL="${KEYCLOAK_INTERNAL_URL:?KEYCLOAK_INTERNAL_URL is required}"
KEYCLOAK_URL="${KEYCLOAK_URL%/}"
REALM="${KEYCLOAK_REALM:?KEYCLOAK_REALM is required}"
CLIENT_ID="${TENANT_ADMIN_CLIENT_ID:?TENANT_ADMIN_CLIENT_ID is required}"
CLIENT_SECRET="${TENANT_ADMIN_CLIENT_SECRET:-}"
CA_BUNDLE="${CURL_CA_BUNDLE:-}"

# Tenant-specific config
KONG_PUBLIC_URL="${KONG_PUBLIC_URL:?KONG_PUBLIC_URL is required}"
UI_NGINX_LOCAL_URL="${UI_NGINX_LOCAL_URL:?UI_NGINX_LOCAL_URL is required}"
UI_VITE_LOCAL_URL="${UI_VITE_LOCAL_URL:-$UI_NGINX_LOCAL_URL}"
ZAMMAD_PUBLIC_URL="${ZAMMAD_PUBLIC_URL:-}"
GRAFANA_PUBLIC_URL="${GRAFANA_PUBLIC_URL:-}"
OPENMETADATA_CALLBACK="${OPENMETADATA_CALLBACK:-}"
ENGINE_CLIENT_ID="${DQ_ENGINE_OIDC_CLIENT_ID:-dq-made-easy-engine-gx-worker}"
ENGINE_CLIENT_SECRET="${DQ_ENGINE_OIDC_CLIENT_SECRET:-changeme}"

curl_kc() {
  local args=()
  if [ -n "$CA_BUNDLE" ] && [ -f "$CA_BUNDLE" ]; then
    args+=(--cacert "$CA_BUNDLE")
  fi
  args+=(-sk --max-time 15)
  curl "${args[@]}" "$@"
}

json_get() {
  printf '%s' "$1" | python3 -c "
import sys, json
d = json.load(sys.stdin)
result = $2
if isinstance(result, list) or isinstance(result, dict):
    print(json.dumps(result))
else:
    print(result if result is not None else '')
" 2>/dev/null
}

echo "=== dq-role-assignment ==="
echo "Keycloak: $KEYCLOAK_URL"
echo "Realm:    $REALM"

# ----------------------------------------------------------------------
# 1. Get admin token via client credentials
# ----------------------------------------------------------------------
echo "[1/4] Obtaining admin token..."
if [ -n "$CLIENT_SECRET" ]; then
  # Service account mode (client_credentials)
  TOKEN_RESPONSE=$(curl_kc -sS -X POST \
    "$KEYCLOAK_URL/realms/$REALM/protocol/openid-connect/token" \
    --data-urlencode "grant_type=client_credentials" \
    --data-urlencode "client_id=$CLIENT_ID" \
    --data-urlencode "client_secret=$CLIENT_SECRET")
else
  # Admin password mode (fallback while KC 26 role-mapping API is unresolved)
  ADMIN_USER="${KEYCLOAK_ADMIN:?KEYCLOAK_ADMIN required in admin mode}"
  ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:?KEYCLOAK_ADMIN_PASSWORD required in admin mode}"
  TOKEN_RESPONSE=$(curl_kc -sS -X POST \
    "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
    --data-urlencode "grant_type=password" \
    --data-urlencode "client_id=admin-cli" \
    --data-urlencode "username=$ADMIN_USER" \
    --data-urlencode "password=$ADMIN_PASS")
fi

ADMIN_TOKEN=$(json_get "$TOKEN_RESPONSE" "d.get('access_token', '')")
if [ -z "$ADMIN_TOKEN" ]; then
  echo "ERROR: Failed to obtain token via tenant-admin" >&2
  echo "Response: $TOKEN_RESPONSE" >&2
  exit 1
fi
echo "  Token obtained."

AUTH_HEADER="Authorization: Bearer $ADMIN_TOKEN"

# ----------------------------------------------------------------------
# 2. Create DQ realm roles
# ----------------------------------------------------------------------
echo "[2/4] Creating DQ realm roles..."

# Scope roles (fine-grained permissions)
SCOPE_ROLES=(
  "dq:rules:read" "dq:rules:write" "dq:rules:create" "dq:rules:edit"
  "dq:rules:delete" "dq:rules:test" "dq:rules:approve" "dq:rules:activate"
  "dq:users:manage" "dq:workspace:manage" "dq:workspace:read"
  "dq:config:manage" "dq:admin:read" "dq:profiling:request"
  "dq:data_catalog:read" "dq:reports:read" "dq:audit:read"
  "dq:templates:read" "dq:templates:write" "dq:notifications:read"
  "dq:exceptions:read" "dq:exceptions:detail"
)

# Aggregate roles with composites
declare -A ROLE_COMPOSITES=(
  ["admin"]="dq:rules:read,dq:rules:write,dq:rules:create,dq:rules:edit,dq:rules:delete,dq:rules:test,dq:rules:approve,dq:rules:activate,dq:users:manage,dq:workspace:manage,dq:workspace:read,dq:config:manage,dq:admin:read,dq:profiling:request,dq:data_catalog:read,dq:reports:read,dq:audit:read,dq:templates:read,dq:templates:write,dq:notifications:read,dq:exceptions:read,dq:exceptions:detail"
  ["rule-approver"]="dq:rules:read,dq:rules:test,dq:rules:approve,dq:exceptions:read"
  ["user"]="dq:rules:read,dq:rules:create,dq:rules:edit,dq:rules:test,dq:workspace:read,dq:data_catalog:read,dq:reports:read,dq:templates:read,dq:notifications:read,dq:exceptions:read"
  ["user-manager"]="dq:users:manage,dq:workspace:manage"
  ["workspace-manager"]="dq:workspace:manage,dq:workspace:read,dq:rules:read"
  ["viewer"]="dq:rules:read,dq:workspace:read,dq:data_catalog:read,dq:reports:read,dq:templates:read"
  ["auditor"]="dq:audit:read,dq:rules:read,dq:exceptions:read,dq:exceptions:detail"
  ["regulator"]="dq:rules:read,dq:rules:approve,dq:audit:read,dq:exceptions:read,dq:exceptions:detail"
  ["operator"]="dq:rules:read,dq:rules:write,dq:profiling:request"
  ["cross-admin"]="dq:rules:read,dq:rules:write,dq:rules:create,dq:rules:edit,dq:rules:delete,dq:workspace:manage,dq:workspace:read,dq:config:manage"
)

# Create scope roles first (no composites)
for role in "${SCOPE_ROLES[@]}"; do
  curl_kc -sS -o /dev/null -w '%{http_code}' \
    -X POST \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"$role\"}" \
    "$KEYCLOAK_URL/admin/realms/$REALM/roles" > /dev/null || true
done

# Create aggregate roles with composites
for role in "${!ROLE_COMPOSITES[@]}"; do
  composites="${ROLE_COMPOSITES[$role]}"
  IFS=',' read -r -a comp_array <<< "$composites"
  composites_json="["
  first=true
  for comp in "${comp_array[@]}"; do
    if [ "$first" = true ]; then first=false; else composites_json+=","; fi
    composites_json+="\"$comp\""
  done
  composites_json+="]"

  role_body="{\"name\": \"$role\"}"
  curl_kc -sS -o /dev/null \
    -X POST \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "$role_body" \
    "$KEYCLOAK_URL/admin/realms/$REALM/roles" || true

  # Assign composites
  if [ ${#comp_array[@]} -gt 0 ]; then
    curl_kc -sS -o /dev/null \
      -X POST \
      -H "$AUTH_HEADER" \
      -H "Content-Type: application/json" \
      -d "{\"realm\": $composites_json}" \
      "$KEYCLOAK_URL/admin/realms/$REALM/roles/$role/composites" || true
  fi
done

echo "  Roles created."

# ----------------------------------------------------------------------
# 3. Assign roles to users
# ----------------------------------------------------------------------
echo "[3/4] Assigning roles to users..."

# Get all users in the realm
USERS=$(curl_kc -sS -H "$AUTH_HEADER" "$KEYCLOAK_URL/admin/realms/$REALM/users?max=200")

# Role assignments: email -> comma-separated roles
declare -A USER_ROLES=(
  ["dq-admin@jaccloud.nl"]="admin"
  ["alice@jaccloud.nl"]="admin"
  ["bob@jaccloud.nl"]="user"
  ["charlie@jaccloud.nl"]="user"
  ["sofie@jaccloud.nl"]="viewer"
  ["oliver@jaccloud.nl"]="viewer"
  ["jan@jaccloud.nl"]="viewer"
  ["emma@jaccloud.nl"]="viewer"
  ["william@jaccloud.nl"]="viewer"
  ["maaike@jaccloud.nl"]="viewer"
  ["james@jaccloud.nl"]="viewer"
  ["bram@jaccloud.nl"]="viewer"
  ["charlotte@jaccloud.nl"]="viewer"
  ["daan@jaccloud.nl"]="viewer"
  ["olivia@jaccloud.nl"]="viewer"
  ["ruben@jaccloud.nl"]="viewer"
  ["fleur@jaccloud.nl"]="viewer"
  ["thomas@jaccloud.nl"]="viewer"
  ["jacbeekers@jaccloud.nl"]="admin"
  ["sophie@jaccloud.nl"]="user"
  ["retail-admin@jaccloud.nl"]="admin"
  ["corporate-admin@jaccloud.nl"]="admin,cross-admin"
  ["multi.workspace@jaccloud.nl"]="user"
  ["demo-analyst@jaccloud.nl"]="user"
  ["demo-data-steward@jaccloud.nl"]="user"
  ["demo-viewer@jaccloud.nl"]="viewer"
  ["operator@jaccloud.nl"]="operator"
  ["auditor@jaccloud.nl"]="auditor"
  ["regulator@jaccloud.nl"]="regulator"
  ["openmetadata-admin@jaccloud.nl"]="admin"
)

assigned_count=0
for email in "${!USER_ROLES[@]}"; do
  # Find user ID
  USER_LIST=$(curl_kc -sS -H "$AUTH_HEADER" "$KEYCLOAK_URL/admin/realms/$REALM/users?username=$email&exact=true" 2>/dev/null) || USER_LIST="[]"
  USER_ID=$(json_get "$USER_LIST" "d[0]['id'] if d else ''" 2>/dev/null) || USER_ID=""

  if [ -z "$USER_ID" ]; then
    echo "  WARNING: user not found: $email" >&2
    continue
  fi

  # Remove existing realm roles, then assign new ones
  IFS=',' read -r -a roles_array <<< "${USER_ROLES[$email]}"
  roles_json="["
  first=true
  for role in "${roles_array[@]}"; do
    if [ "$first" = true ]; then first=false; else roles_json+=","; fi
    roles_json+="\"$role\""
  done
  roles_json+="]"

  curl_kc -sS -o /dev/null \
    -X POST \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "$roles_json" \
    "$KEYCLOAK_URL/admin/realms/$REALM/users/$USER_ID/role-mapping/realm" 2>/dev/null || true

  assigned_count=$((assigned_count + 1))
done
echo "  Roles assigned to $assigned_count users."

# ----------------------------------------------------------------------
# 4. Create DQ OIDC clients
# ----------------------------------------------------------------------
echo "[4/4] Creating DQ OIDC clients..."

# Check if client exists (via list)
client_exists() {
  local cid="$1"
  local clients
  clients=$(curl_kc -sS -H "$AUTH_HEADER" "$KEYCLOAK_URL/admin/realms/$REALM/clients")
  local result
  result=$(json_get "$clients" "any(c.get('clientId') == '$cid' for c in d)")
  [ "$result" = "True" ]
}

# --- dq-rules-ui (public browser client) ---
if ! client_exists "dq-rules-ui"; then
  echo "  Creating dq-rules-ui..."
  curl_kc -sS -o /dev/null \
    -X POST \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{
      \"clientId\": \"dq-rules-ui\",
      \"enabled\": true,
      \"publicClient\": true,
      \"protocol\": \"openid-connect\",
      \"redirectUris\": [
        \"${KONG_PUBLIC_URL}/auth/v1/callback\",
        \"${UI_NGINX_LOCAL_URL}/*\",
        \"${UI_VITE_LOCAL_URL}/*\"
      ],
      \"webOrigins\": [\"${UI_NGINX_LOCAL_URL}\", \"${UI_VITE_LOCAL_URL}\"],
      \"directAccessGrantsEnabled\": true,
      \"defaultClientScopes\": [\"profile\", \"email\", \"roles\"],
      \"attributes\": {\"post.logout.redirect.uris\": \"${KONG_PUBLIC_URL}##${UI_NGINX_LOCAL_URL}\"}
    }" \
    "$KEYCLOAK_URL/admin/realms/$REALM/clients"
fi

# --- dq-engine service client ---
if ! client_exists "$ENGINE_CLIENT_ID"; then
  echo "  Creating $ENGINE_CLIENT_ID..."
  curl_kc -sS -o /dev/null \
    -X POST \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{
      \"clientId\": \"$ENGINE_CLIENT_ID\",
      \"name\": \"dq-engine GX worker\",
      \"enabled\": true,
      \"publicClient\": false,
      \"clientAuthenticatorType\": \"client-secret\",
      \"secret\": \"$ENGINE_CLIENT_SECRET\",
      \"protocol\": \"openid-connect\",
      \"serviceAccountsEnabled\": true,
      \"standardFlowEnabled\": false,
      \"implicitFlowEnabled\": false,
      \"directAccessGrantsEnabled\": false,
      \"defaultClientScopes\": [\"openid\", \"profile\", \"email\", \"roles\"]
    }" \
    "$KEYCLOAK_URL/admin/realms/$REALM/clients"
fi

# --- openmetadata (public) ---
if [ -n "$OPENMETADATA_CALLBACK" ] && ! client_exists "openmetadata"; then
  echo "  Creating openmetadata..."
  OM_ORIGIN=$(printf '%s' "$OPENMETADATA_CALLBACK" | sed 's|/callback$||')
  curl_kc -sS -o /dev/null \
    -X POST \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{
      \"clientId\": \"openmetadata\",
      \"enabled\": true,
      \"publicClient\": true,
      \"protocol\": \"openid-connect\",
      \"redirectUris\": [\"$OPENMETADATA_CALLBACK\"],
      \"webOrigins\": [\"$OM_ORIGIN\"],
      \"directAccessGrantsEnabled\": true,
      \"standardFlowEnabled\": true,
      \"implicitFlowEnabled\": true,
      \"defaultClientScopes\": [\"profile\", \"email\", \"roles\"]
    }" \
    "$KEYCLOAK_URL/admin/realms/$REALM/clients"
fi

# --- zammad (public) ---
if [ -n "$ZAMMAD_PUBLIC_URL" ] && ! client_exists "zammad"; then
  echo "  Creating zammad..."
  curl_kc -sS -o /dev/null \
    -X POST \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{
      \"clientId\": \"zammad\",
      \"name\": \"Zammad\",
      \"enabled\": true,
      \"publicClient\": true,
      \"protocol\": \"openid-connect\",
      \"standardFlowEnabled\": true,
      \"redirectUris\": [\"${ZAMMAD_PUBLIC_URL}/auth/openid_connect/callback\"],
      \"webOrigins\": [\"$ZAMMAD_PUBLIC_URL\"],
      \"defaultClientScopes\": [\"profile\", \"email\"],
      \"attributes\": {\"post.logout.redirect.uris\": \"${ZAMMAD_PUBLIC_URL}/*\"}
    }" \
    "$KEYCLOAK_URL/admin/realms/$REALM/clients"
fi

# --- grafana (confidential, service account) ---
if [ -n "$GRAFANA_PUBLIC_URL" ] && ! client_exists "grafana"; then
  echo "  Creating grafana..."
  curl_kc -sS -o /dev/null \
    -X POST \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{
      \"clientId\": \"grafana\",
      \"name\": \"Grafana\",
      \"enabled\": true,
      \"publicClient\": false,
      \"serviceAccountsEnabled\": true,
      \"secret\": \"changeme\",
      \"protocol\": \"openid-connect\",
      \"standardFlowEnabled\": true,
      \"redirectUris\": [\"${GRAFANA_PUBLIC_URL}/login/generic_oauth\"],
      \"webOrigins\": [\"$GRAFANA_PUBLIC_URL\"],
      \"defaultClientScopes\": [\"profile\", \"email\", \"roles\"]
    }" \
    "$KEYCLOAK_URL/admin/realms/$REALM/clients"
fi

echo "=== dq-role-assignment complete ==="
