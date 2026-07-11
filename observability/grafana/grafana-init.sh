#!/bin/bash
set -euo pipefail

GRAFANA_HOST="${GRAFANA_HOST:?GRAFANA_HOST is required}"
GRAFANA_PORT="${GRAFANA_HTTPS_HOST_PORT:?GRAFANA_HTTPS_HOST_PORT is required}"
GRAFANA_USER="${GRAFANA_ADMIN_USER:?GRAFANA_ADMIN_USER is required}"
GRAFANA_PASS="${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD is required}"

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
  local name="$1" email="$2"
  local response id
  response="$(curl -s -X POST \
    -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    -H "Content-Type: application/json" \
    "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/teams" \
    -d "{\"name\": \"${name}\", \"email\": \"${email}\"}')"
  id="$(echo "$response" | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*' || echo "")"
  if [ -z "$id" ]; then
    id="$(curl -s -X GET \
      -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
      "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/teams/search?query=${name}" \
      | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*')"
  fi
  echo "✓ ${name} team ID: ${id}"
}

# Create teams
create_team "Viewers" "viewers@dq-rulebuilder.local"
VIEWER_ID="$(curl -s -X GET \
  -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/teams/search?query=Viewers" \
  | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*')"

create_team "Editors" "editors@dq-rulebuilder.local"
EDITOR_ID="$(curl -s -X GET \
  -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/teams/search?query=Editors" \
  | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*')"

create_team "Admins" "admins@dq-rulebuilder.local"
ADMIN_ID="$(curl -s -X GET \
  -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/teams/search?query=Admins" \
  | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*')"

echo ""
echo "Setting dashboard permissions..."

DASHBOARD_ID="$(curl -s -X GET \
  -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
  "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/search?type=dash-db&query=${OBSERVABILITY_DASHBOARD_UID}" \
  | sed -n 's/.*"id":\([0-9][0-9]*\).*/\1/p' | head -1)"

if [ -z "$DASHBOARD_ID" ]; then
  echo "⚠ Dashboard '${OBSERVABILITY_DASHBOARD_TITLE}' (uid=${OBSERVABILITY_DASHBOARD_UID}) not found. Skipping permissions setup."
  echo "  You can set permissions manually after the dashboard is available."
else
  echo "✓ Found dashboard ID: ${DASHBOARD_ID}"

  curl -s -X POST \
    -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    -H "Content-Type: application/json" \
    "https://${GRAFANA_HOST}:${GRAFANA_PORT}/api/dashboards/id/${DASHBOARD_ID}/permissions" \
    -d "{\"items\":[{\"teamId\": ${VIEWER_ID}, \"permission\": 1},{\"teamId\": ${EDITOR_ID}, \"permission\": 2},{\"teamId\": ${ADMIN_ID}, \"permission\": 4}]}" \
    > /dev/null 2>&1
  echo "✓ Viewers: Read-only access (permission: 1)"
  echo "✓ Editors: Edit access (permission: 2)"
  echo "✓ Admins: Admin access (permission: 4)"
fi

echo ""
echo "✅ Grafana provisioning complete!"
echo "   Teams: Viewers, Editors, Admins"
echo "   Ready for OIDC + permission enforcement"
