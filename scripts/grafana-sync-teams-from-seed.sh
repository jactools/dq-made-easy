#!/usr/bin/env bash
set -euo pipefail


# Purpose: Sync Grafana teams/users based on seeded CSV data.
#
# What it does:
# - Reads user and role seed CSV files.
# - Calls Grafana HTTP APIs using admin credentials.
# - Creates/updates teams (and optionally users) to match the seed.
#
# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"

source "$ROOT_DIR/scripts/supporting/logging.sh"

GRAFANA_URL="${GRAFANA_URL:-http://observability.jac.dot:3000}"
ADMIN_USER="${GRAFANA_ADMIN_USER:-admin}"
ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-changeme}"
USERS_CSV="${USERS_CSV:-$ROOT_DIR/dq-db/mock-data/users.csv}"
USER_ROLES_CSV="${USER_ROLES_CSV:-$ROOT_DIR/dq-db/mock-data/user_roles.csv}"
WAIT_SECONDS="${GRAFANA_SYNC_WAIT_SECONDS:-120}"
CREATE_MISSING_USERS="${GRAFANA_SYNC_CREATE_MISSING_USERS:-true}"
DEFAULT_PASSWORD="${GRAFANA_SYNC_DEFAULT_PASSWORD:-LocalOnly123!}"
CURL_CONNECT_TIMEOUT="${GRAFANA_SYNC_CONNECT_TIMEOUT:-3}"
CURL_MAX_TIME="${GRAFANA_SYNC_MAX_TIME:-15}"
SYNC_PARALLELISM="${GRAFANA_SYNC_PARALLELISM:-8}"
TMP_DIR=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

cleanup_tmp_dir() {
  if [ -n "${TMP_DIR:-}" ] && [ -d "${TMP_DIR}" ]; then
    rm -rf "${TMP_DIR}"
  fi
}

require_tools() {
  local missing=0
  for tool in curl jq; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      error "$my_name" "Required tool not found: $tool"
      missing=1
    fi
  done
  if [ ! -x "$PYTHON_RUNNER" ]; then
    error "$my_name" "Required tool not found or not executable: $PYTHON_RUNNER"
    missing=1
  fi
  if [ "$missing" -ne 0 ]; then
    exit 1
  fi
}

wait_for_grafana() {
  local attempts=$((WAIT_SECONDS / 2))
  local i
  for ((i = 1; i <= attempts; i++)); do
    if curl -sSf --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" "${GRAFANA_URL}/api/health" >/dev/null 2>&1; then
      success "$my_name" "Grafana is healthy at ${GRAFANA_URL}"
      return 0
    fi
    sleep 2
  done
  error "$my_name" "Grafana is not reachable at ${GRAFANA_URL}"
  return 1
}

api_get() {
  local path="$1"
  curl -sS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" \
    -u "${ADMIN_USER}:${ADMIN_PASSWORD}" "${GRAFANA_URL}${path}"
}

api_post() {
  local path="$1"
  local payload="$2"
  curl -sS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" -X POST \
    -u "${ADMIN_USER}:${ADMIN_PASSWORD}" \
    -H "Content-Type: application/json" \
    "${GRAFANA_URL}${path}" \
    -d "$payload"
}

api_post_with_status() {
  local path="$1"
  local payload="$2"
  local response
  response=$(curl -sS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" -X POST \
    -u "${ADMIN_USER}:${ADMIN_PASSWORD}" \
    -H "Content-Type: application/json" \
    "${GRAFANA_URL}${path}" \
    -d "$payload" \
    -w $'\n%{http_code}')

  local code
  code="${response##*$'\n'}"
  local body
  body="${response%$'\n'*}"
  printf '%s\t%s\n' "$code" "$body"
}

api_delete_with_status() {
  local path="$1"
  local response
  response=$(curl -sS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" -X DELETE \
    -u "${ADMIN_USER}:${ADMIN_PASSWORD}" \
    "${GRAFANA_URL}${path}" \
    -w $'\n%{http_code}')

  local code
  code="${response##*$'\n'}"
  local body
  body="${response%$'\n'*}"
  printf '%s\t%s\n' "$code" "$body"
}

get_team_id() {
  local team_name="$1"
  api_get "/api/teams/search?query=${team_name}" | jq -r --arg n "$team_name" '.teams[]? | select(.name == $n) | .id' | head -1
}

ensure_team_exists() {
  local team_name="$1"
  local team_email="$2"

  local team_id
  team_id="$(get_team_id "$team_name")"

  if [ -n "$team_id" ]; then
    echo "$team_id"
    return 0
  fi

  api_post "/api/teams" "$(jq -nc --arg name "$team_name" --arg email "$team_email" '{name:$name,email:$email}')" >/dev/null
  team_id="$(get_team_id "$team_name")"
  if [ -z "$team_id" ]; then
    error "$my_name" "Unable to create or locate team: $team_name"
    return 1
  fi
  echo "$team_id"
}

create_user_if_missing() {
  local name="$1"
  local email="$2"

  if [ "$CREATE_MISSING_USERS" != "true" ]; then
    return 0
  fi

  local payload
  payload="$(jq -nc --arg name "$name" --arg login "$email" --arg email "$email" --arg password "$DEFAULT_PASSWORD" '{name:$name,login:$login,email:$email,password:$password}')"
  api_post "/api/admin/users" "$payload" >/dev/null || true
}

fetch_all_grafana_users() {
  local out_file="$1"
  local page=1
  local perpage=1000
  local users_json='[]'

  while true; do
    local page_data
    page_data="$(api_get "/api/users/search?perpage=${perpage}&page=${page}" 2>/dev/null || true)"

    local page_users
    page_users="$(printf '%s' "$page_data" | jq -c '.users // []' 2>/dev/null || echo '[]')"

    users_json="$(jq -c -s '.[0] + .[1]' <(printf '%s' "$users_json") <(printf '%s' "$page_users"))"

    local count
    count="$(printf '%s' "$page_users" | jq 'length')"
    if [ "$count" -lt "$perpage" ]; then
      break
    fi
    page=$((page + 1))
  done

  printf '%s\n' "$users_json" > "$out_file"
}

build_user_index() {
  local users_json_file="$1"
  local out_index="$2"
  jq -r '.[] | [.email, .id] | @tsv' "$users_json_file" > "$out_index"
}

lookup_user_id_from_index() {
  local user_index_file="$1"
  local email="$2"
  awk -F '\t' -v key="$email" '$1 == key { print $2; exit }' "$user_index_file"
}

fetch_team_members_to_map() {
  local team_id="$1"
  local out_file="$2"

  api_get "/api/teams/${team_id}/members" | jq -r --arg tid "$team_id" '.[]? | [.userId, $tid] | @tsv' >> "$out_file"
}

is_member_of_team() {
  local membership_file="$1"
  local user_id="$2"
  local team_id="$3"
  awk -F '\t' -v uid="$user_id" -v tid="$team_id" '$1 == uid && $2 == tid { found=1; exit } END { exit(found ? 0 : 1) }' "$membership_file"
}

queue_action() {
  local actions_file="$1"
  local action="$2"
  local path="$3"
  local payload_b64="$4"
  local message="$5"
  printf '%s\t%s\t%s\t%s\n' "$action" "$path" "$payload_b64" "$message" >> "$actions_file"
}

run_action() {
  local action="$1"
  local path="$2"
  local payload_b64="$3"
  local message="$4"
  local failure_file="$5"

  local payload=""
  if [ -n "$payload_b64" ] && [ "$payload_b64" != "-" ]; then
    payload="$("$PYTHON_RUNNER" -c 'import base64,sys; print(base64.b64decode(sys.stdin.read().encode()).decode())' <<< "$payload_b64")"
  fi

  local result
  local code
  local body

  if [ "$action" = "POST" ]; then
    result="$(api_post_with_status "$path" "$payload")"
  else
    result="$(api_delete_with_status "$path")"
  fi

  code="${result%%$'\t'*}"
  body="${result#*$'\t'}"

  if [ "$action" = "POST" ]; then
    if [ "$code" = "200" ] || [ "$code" = "201" ] || [ "$code" = "409" ]; then
      success "$my_name" "$message"
      return 0
    fi
  else
    if [ "$code" = "200" ] || [ "$code" = "202" ] || [ "$code" = "404" ]; then
      info "$my_name" "$message"
      return 0
    fi
  fi

  {
    echo "action=$action path=$path code=$code"
    echo "body=$body"
  } >> "$failure_file"
  warning "$my_name" "Action failed: $message (HTTP $code)"
  return 1
}

encode_payload_b64() {
  "$PYTHON_RUNNER" -c 'import base64,sys; print(base64.b64encode(sys.stdin.read().encode()).decode())'
}

run_actions_parallel() {
  local actions_file="$1"
  local failure_file="$2"
  local parallelism="$3"

  if [ ! -s "$actions_file" ]; then
    return 0
  fi

  while IFS=$'\t' read -r action path payload_b64 message; do
    while [ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$parallelism" ]; do
      sleep 0.1
    done
    run_action "$action" "$path" "$payload_b64" "$message" "$failure_file" &
  done < "$actions_file"

  wait
}

build_sync_plan() {
  "$PYTHON_RUNNER" - "$USERS_CSV" "$USER_ROLES_CSV" <<'PY'
import csv
import re
import sys
from collections import defaultdict

users_csv, roles_csv = sys.argv[1], sys.argv[2]

roles_by_user = defaultdict(set)
with open(roles_csv, newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        uid = row.get('user_id', '').strip()
        role = row.get('role_id', '').strip()
        if uid and role:
            roles_by_user[uid].add(role)

with open(users_csv, newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        uid = row.get('id', '').strip()
    first_name = row.get('first_name', '').strip()
    last_name = row.get('last_name', '').strip()
        email = row.get('email', '').strip()
        if not uid or not email:
            continue
    if not first_name or not last_name:
      raise SystemExit(f"users.csv row is missing required first_name/last_name for {email or uid}")

    name = f"{first_name} {last_name}"

        roles = roles_by_user.get(uid, set())
        if 'admin' in roles or 'cross-admin' in roles:
            team = 'Admins'
        elif 'rule-approver' in roles or 'user' in roles or any(re.match(r'^r[01]\d+$', r) for r in roles):
            team = 'Editors'
        elif 'viewer' in roles:
            team = 'Viewers'
        else:
            team = 'Viewers'

        print(f"{uid}\t{name}\t{email}\t{team}")
PY
}

main() {
  require_tools

  if [ ! -f "$USERS_CSV" ]; then
    error "$my_name" "Users CSV not found: $USERS_CSV"
    exit 1
  fi
  if [ ! -f "$USER_ROLES_CSV" ]; then
    error "$my_name" "User roles CSV not found: $USER_ROLES_CSV"
    exit 1
  fi

  wait_for_grafana

  local viewer_team_id
  local editor_team_id
  local admin_team_id

  viewer_team_id="$(ensure_team_exists "Viewers" "viewers@dq-rulebuilder.local")"
  editor_team_id="$(ensure_team_exists "Editors" "editors@dq-rulebuilder.local")"
  admin_team_id="$(ensure_team_exists "Admins" "admins@dq-rulebuilder.local")"

  TMP_DIR="$(mktemp -d)"
  trap cleanup_tmp_dir EXIT

  local users_json_file="$TMP_DIR/grafana_users.json"
  local user_index_file="$TMP_DIR/grafana_user_index.tsv"
  local managed_membership_file="$TMP_DIR/managed_memberships.tsv"
  local actions_file="$TMP_DIR/actions.tsv"
  local failure_file="$TMP_DIR/failures.log"

  : > "$managed_membership_file"
  : > "$actions_file"
  : > "$failure_file"

  # One bulk user prefetch avoids O(n) lookup calls.
  fetch_all_grafana_users "$users_json_file"
  build_user_index "$users_json_file" "$user_index_file"

  local total=0
  local mapped_or_kept=0
  local created_users=0

  while IFS=$'\t' read -r _user_id name email _target_team; do
    [ -z "$email" ] && continue
    local existing
    existing="$(lookup_user_id_from_index "$user_index_file" "$email")"
    if [ -n "$existing" ]; then
      continue
    fi
    create_user_if_missing "$name" "$email"
    created_users=$((created_users + 1))
  done < <(build_sync_plan)

  if [ "$created_users" -gt 0 ]; then
    fetch_all_grafana_users "$users_json_file"
    build_user_index "$users_json_file" "$user_index_file"
  fi

  # Bulk team membership prefetch for managed teams.
  fetch_team_members_to_map "$viewer_team_id" "$managed_membership_file"
  fetch_team_members_to_map "$editor_team_id" "$managed_membership_file"
  fetch_team_members_to_map "$admin_team_id" "$managed_membership_file"

  while IFS=$'\t' read -r user_id name email target_team; do
    [ -z "$email" ] && continue
    total=$((total + 1))

    local target_team_id=""
    case "$target_team" in
      Viewers) target_team_id="$viewer_team_id" ;;
      Editors) target_team_id="$editor_team_id" ;;
      Admins) target_team_id="$admin_team_id" ;;
      *)
        warning "$my_name" "Skipping unknown team mapping for $email: $target_team"
        continue
        ;;
    esac

    local grafana_user_id
    grafana_user_id="$(lookup_user_id_from_index "$user_index_file" "$email")"

    if [ -z "$grafana_user_id" ]; then
      warning "$my_name" "Grafana user not found and could not be created: $email"
      continue
    fi

    local has_target=false
    if is_member_of_team "$managed_membership_file" "$grafana_user_id" "$target_team_id"; then
      has_target=true
      mapped_or_kept=$((mapped_or_kept + 1))
      info "$my_name" "User already mapped: ${email} -> ${target_team}"
    fi

    local managed_team_id
    for managed_team_id in "$viewer_team_id" "$editor_team_id" "$admin_team_id"; do
      if [ "$managed_team_id" = "$target_team_id" ]; then
        continue
      fi
      if is_member_of_team "$managed_membership_file" "$grafana_user_id" "$managed_team_id"; then
        queue_action "$actions_file" "DELETE" "/api/teams/${managed_team_id}/members/${grafana_user_id}" "-" "Removed ${email} from team ${managed_team_id}"
      fi
    done

    if [ "$has_target" = false ]; then
      local payload
      payload="$(jq -nc --argjson uid "$grafana_user_id" '{userId:$uid}')"
      queue_action "$actions_file" "POST" "/api/teams/${target_team_id}/members" "$(printf '%s' "$payload" | encode_payload_b64)" "Mapped ${email} -> ${target_team}"
      mapped_or_kept=$((mapped_or_kept + 1))
    fi
  done < <(build_sync_plan)

  run_actions_parallel "$actions_file" "$failure_file" "$SYNC_PARALLELISM"

  if [ -s "$failure_file" ]; then
    error "$my_name" "Grafana team sync completed with failures"
    cat "$failure_file"
    exit 1
  fi

  success "$my_name" "Grafana team sync complete: processed=${total}, created_users=${created_users}, mapped_or_kept=${mapped_or_kept}"
}

main "$@"
