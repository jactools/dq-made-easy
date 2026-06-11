KEYCLOAK_HOST="keycloak.local:8080"
KEYCLOAK_REALM="jaccloud"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Testing Keycloak connectivity and token retrieval from host against $KEYCLOAK_HOST..."
response=$(curl -s -X POST \
  -d "client_id=admin-cli" \
  -d "username=admin" \
  -d "password=admin" \
  -d "grant_type=password" \
  "http://${KEYCLOAK_HOST}/realms/master/protocol/openid-connect/token")

access_token=$(echo "$response" | jq -r '.access_token')

if [ -z "$access_token" ]; then
  echo "Failed to obtain access token."
  exit 1
fi

echo "Creating a new client in Keycloak using the obtained token..."
rc=$(curl -s -X POST \
  -H "Authorization: Bearer $access_token" \
  -H "Content-Type: application/json" \
  -d '{
    "clientId": "dq-service-client",
    "name": "DQ Service Client",
    "enabled": true,
    "protocol": "openid-connect",
    "publicClient": false,
    "standardFlowEnabled": false,
    "directAccessGrantsEnabled": true,
    "serviceAccountsEnabled": true
  }' \
  "http://${KEYCLOAK_HOST}/admin/realms/${KEYCLOAK_REALM}/clients")

echo "Response from client creation:"
echo "$rc" | jq .

echo "Fetching clients to verify creation..."
response=$(curl -s -X GET \
  -H "Authorization: Bearer $access_token" \
  "http://${KEYCLOAK_HOST}/admin/realms/${KEYCLOAK_REALM}/clients?clientId=dq-service-client")

secret=$(echo "$response" | jq -r '.[0].secret')

if [ -z "$secret" ] || [ "$secret" = "null" ]; then
  echo "Failed to retrieve client secret."
  exit 1
fi

# Get a list of users in the jaccloud realm to verify admin API access
echo "Fetching users in realm ${KEYCLOAK_REALM} to verify admin API access..."
users_response=$(curl -s -X GET \
  -H "Authorization: Bearer $access_token" \
  "http://${KEYCLOAK_HOST}/admin/realms/${KEYCLOAK_REALM}/users")       

if [ -z "$users_response" ]; then
  echo "Failed to fetch users from Keycloak. Check admin API access."
  exit 1
fi

echo "$users_response" | jq -r '.[] | [.id, .username, .email] | @csv' > tmp/keycloak_users.csv
echo "User list saved to tmp/keycloak_users.csv"
