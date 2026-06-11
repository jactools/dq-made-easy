#!/bin/bash
set -euo pipefail


# Purpose: Provision Grafana teams and dashboard permissions.
#
# What it does:
# - Creates baseline teams in Grafana.
# - Grants dashboard permissions for a configured dashboard UID.
#!/bin/bash
set -euo pipefail

# Purpose: Provision Grafana teams and dashboard permissions.
#
# What it does:
# - Creates baseline teams in Grafana.
# - Grants dashboard permissions for a configured dashboard UID.
# - Requires Grafana to be reachable and jq available.
#
# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
my_name="grafana-teams-setup.sh"

source "$ROOT_DIR/scripts/supporting/logging.sh"

# Configuration
GRAFANA_URL="${1:-http://observability.jac.dot}"
ADMIN_USER="${2:-admin}"
ADMIN_PASSWORD="${3:-changeme}"
DASHBOARD_UID="${GRAFANA_DASHBOARD_UID:-dq-execution-monitoring}"
DASHBOARD_TITLE="${GRAFANA_DASHBOARD_TITLE:-Data Quality Made Easy - Execution Monitoring}"

check_prerequisites() {
  info "$my_name" "Checking prerequisites..."

  if ! command -v jq >/dev/null 2>&1; then
    error "$my_name" "jq is not installed. Install with: brew install jq"
    exit 1
  fi

  if ! command -v curl >/dev/null 2>&1; then
    error "$my_name" "curl is not installed"
    exit 1
  fi

  success "$my_name" "Prerequisites OK"
}

wait_for_grafana() {
  info "$my_name" "Waiting for Grafana to be healthy..."

  local max_attempts=30
  local attempt=0

  while [ "$attempt" -lt "$max_attempts" ]; do
    if curl -sf "${GRAFANA_URL}/api/health" >/dev/null 2>&1; then
      success "$my_name" "Grafana is healthy"
      return 0
    fi

    attempt=$((attempt + 1))
    echo -n "."
    sleep 2
  done

  error "$my_name" "Grafana did not become healthy after ${max_attempts} attempts"
  exit 1
}

create_team() {
  local team_name="$1"
  local team_email="$2"

  info "$my_name" "Creating team: $team_name"

  local response
  response=$(curl -s -X POST \
    -u "${ADMIN_USER}:${ADMIN_PASSWORD}" \
    -H "Content-Type: application/json" \
    "${GRAFANA_URL}/api/teams" \
    -d "{\"name\": \"$team_name\", \"email\": \"$team_email\"}")

  local team_id
  team_id=$(echo "$response" | jq -r '.id // empty')

  if [ -z "$team_id" ]; then
    local existing
    existing=$(curl -s -X GET \
      -u "${ADMIN_USER}:${ADMIN_PASSWORD}" \
      "${GRAFANA_URL}/api/teams/search?query=$team_name")

    team_id=$(echo "$existing" | jq -r '.teams[0].id // empty')

    if [ -z "$team_id" ]; then
      warning "$my_name" "Could not create or find team: $team_name"
      return 1
    fi

    warning "$my_name" "Team already exists: $team_name (ID: $team_id)"
  else
    success "$my_name" "Created team: $team_name (ID: $team_id)"
  fi

  echo "$team_id"
}

get_dashboard_id() {
  local dashboard_uid="$1"
  local dashboard_title="$2"

  info "$my_name" "Finding dashboard by UID: $dashboard_uid"

  local response
  response=$(curl -s -X GET \
    -u "${ADMIN_USER}:${ADMIN_PASSWORD}" \
    "${GRAFANA_URL}/api/search?type=dash-db&query=$dashboard_uid")

  local dashboard_id
  dashboard_id=$(echo "$response" | jq -r 'map(select(.uid == "'"$dashboard_uid"'"))[0].id // empty')

  if [ -z "$dashboard_id" ]; then
    info "$my_name" "UID lookup failed, trying title: $dashboard_title"
    response=$(curl -s -X GET \
      -u "${ADMIN_USER}:${ADMIN_PASSWORD}" \
      "${GRAFANA_URL}/api/search?type=dash-db&query=$dashboard_title")
    dashboard_id=$(echo "$response" | jq -r '.[0].id // empty')
  fi

  if [ -z "$dashboard_id" ]; then
    warning "$my_name" "Dashboard not found (UID: $dashboard_uid, title: $dashboard_title)"
    return 1
  fi

  success "$my_name" "Found dashboard (ID: $dashboard_id)"
  echo "$dashboard_id"
}

set_dashboard_permission() {
  local dashboard_id="$1"
  local team_id="$2"
  local team_name="$3"
  local permission="$4"

  info "$my_name" "Setting permission for team $team_name on dashboard $dashboard_id: permission=$permission"

  local response
  response=$(curl -s -X POST \
    -u "${ADMIN_USER}:${ADMIN_PASSWORD}" \
    -H "Content-Type: application/json" \
    "${GRAFANA_URL}/api/dashboards/id/${dashboard_id}/permissions" \
    -d "{\"items\":[{\"teamId\": ${team_id}, \"permission\": ${permission}}]}")

  if echo "$response" | jq -e '.message' >/dev/null 2>&1; then
    local message
    message=$(echo "$response" | jq -r '.message')
    success "$my_name" "Permission set: $message"
  else
    success "$my_name" "Permission set for team $team_name"
  fi
}

main() {
  echo ""
  echo "╔═══════════════════════════════════════════════════════════╗"
  echo "║    Grafana Teams & Dashboard Permissions Setup            ║"
  echo "╚═══════════════════════════════════════════════════════════╝"
  echo ""

  check_prerequisites
  wait_for_grafana

  info "$my_name" "Grafana URL: $GRAFANA_URL"
  info "$my_name" "Admin User: $ADMIN_USER"
  echo ""

  VIEWER_TEAM_ID=$(create_team "Viewers" "viewers@dq-rulebuilder.local")
  EDITOR_TEAM_ID=$(create_team "Editors" "editors@dq-rulebuilder.local")
  ADMIN_TEAM_ID=$(create_team "Admins" "admins@dq-rulebuilder.local")

  echo ""

  DASHBOARD_ID=$(get_dashboard_id "$DASHBOARD_UID" "$DASHBOARD_TITLE" || true)

  if [ -z "$DASHBOARD_ID" ]; then
    warning "$my_name" "Could not find dashboard. Skipping permission setup."
    info "$my_name" "Teams have been created successfully."
    echo ""
    info "$my_name" "Next steps:"
    echo "  1. Users with Keycloak role 'viewer' will be added to Viewers team"
    echo "  2. Users with Keycloak roles 'rule-approver', 'user', 'r0X', 'r1X' will be added to Editors team"
    echo "  3. Users with Keycloak roles 'admin', 'cross-admin' will be added to Admins team"
    echo "  4. Teams inherit dashboard permissions based on their role"
  else
    info "$my_name" "Setting dashboard permissions..."
    set_dashboard_permission "$DASHBOARD_ID" "$VIEWER_TEAM_ID" "Viewers" 1
    set_dashboard_permission "$DASHBOARD_ID" "$EDITOR_TEAM_ID" "Editors" 2
    set_dashboard_permission "$DASHBOARD_ID" "$ADMIN_TEAM_ID" "Admins" 4

    echo ""
    success "$my_name" "Dashboard permissions configured"
  fi

  echo ""
  echo "╔═══════════════════════════════════════════════════════════╗"
  echo "║    Teams Setup Complete ✅                                 ║"
  echo "╚═══════════════════════════════════════════════════════════╝"
  echo ""
  info "$my_name" "Summary:"
  echo "  Viewers Team ID:  $VIEWER_TEAM_ID (View-only access)"
  echo "  Editors Team ID:  $EDITOR_TEAM_ID (Create/edit access)"
  echo "  Admins Team ID:   $ADMIN_TEAM_ID (Full admin access)"
  echo ""
  info "$my_name" "Next: When OIDC is active, users will auto-map to teams based on Keycloak roles"
  echo ""
}

main "$@"
  echo "╚═══════════════════════════════════════════════════════════╝"
