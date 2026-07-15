#!/bin/sh
set -eu

GRAFANA_HOST="${GRAFANA_HOST:-}"
GRAFANA_PORT="${GRAFANA_HTTPS_HOST_PORT:-}"
GRAFANA_USER="${GRAFANA_ADMIN_USER:-}"
GRAFANA_PASS="${GRAFANA_ADMIN_PASSWORD:-}"

if [ -z "$GRAFANA_HOST" ]; then echo "GRAFANA_HOST is required"; exit 1; fi
if [ -z "$GRAFANA_PORT" ]; then echo "GRAFANA_HTTPS_HOST_PORT is required"; exit 1; fi
if [ -z "$GRAFANA_USER" ]; then echo "GRAFANA_ADMIN_USER is required"; exit 1; fi
if [ -z "$GRAFANA_PASS" ]; then echo "GRAFANA_ADMIN_PASSWORD is required"; exit 1; fi

echo "Waiting for Grafana to be ready..."
until curl --fail --silent --show-error \
  --cacert /etc/grafana-init/mkcert-rootCA.pem \
  "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/health" \
  > /dev/null 2>&1; do
  echo "  Grafana not ready yet, waiting..."
  sleep 2
done
echo "Grafana is ready!"
echo "Setting up teams and dashboard permissions..."
echo ""

create_team() {
  _name="$1"
  _email="$2"
  _response=""
  _id=""
  
  _response=$(curl -s -X POST \
    -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    -H "Content-Type: application/json" \
    "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/teams" \
    -d "{\"name\": \"${_name}\", \"email\": \"${_email}\"}")
  
  _id=$(echo "$_response" | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*') || _id=""
  
  if [ -z "$_id" ]; then
    _id=$(curl -s -X GET \
      -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
      "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/teams/search?query=${_name}" \
      | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*') || _id=""
  fi
  
  echo "OK ${_name} team ID: ${_id}"
  return 0
}

# Create teams
create_team "Viewers" "viewers@dq-rulebuilder.local"
VIEWER_ID=$(curl -s -X GET \
  -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/teams/search?query=Viewers" \
  | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*') || VIEWER_ID=""

create_team "Editors" "editors@dq-rulebuilder.local"
EDITOR_ID=$(curl -s -X GET \
  -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/teams/search?query=Editors" \
  | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*') || EDITOR_ID=""

create_team "Admins" "admins@dq-rulebuilder.local"
ADMIN_ID=$(curl -s -X GET \
  -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/teams/search?query=Admins" \
  | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*') || ADMIN_ID=""

echo ""
echo "Setting dashboard permissions..."

DASHBOARD_ID=$(curl -s -X GET \
  -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/search?type=dash-db&query=${OBSERVABILITY_DASHBOARD_UID}" \
  | sed -n 's/.*"id":\([0-9][0-9]*\).*/\1/p' | head -1) || DASHBOARD_ID=""

if [ -z "$DASHBOARD_ID" ]; then
  echo "WARNING Dashboard not found. Skipping permissions setup."
  echo "  You can set permissions manually after the dashboard is available."
else
  echo "OK Found dashboard ID: ${DASHBOARD_ID}"

  curl -s -X POST \
    -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    -H "Content-Type: application/json" \
    "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/dashboards/id/${DASHBOARD_ID}/permissions" \
    -d "{\"items\":[{\"teamId\": ${VIEWER_ID}, \"permission\": 1},{\"teamId\": ${EDITOR_ID}, \"permission\": 2},{\"teamId\": ${ADMIN_ID}, \"permission\": 4}]}" \
    > /dev/null 2>&1
  echo "OK Viewers: Read-only access (permission: 1)"
  echo "OK Editors: Edit access (permission: 2)"
  echo "OK Admins: Admin access (permission: 4)"
fi

echo ""
echo "DONE Grafana provisioning complete!"
echo "   Teams: Viewers, Editors, Admins"
echo "   Ready for OIDC + permission enforcement"
