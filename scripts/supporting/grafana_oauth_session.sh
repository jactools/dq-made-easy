#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="grafana_oauth_session.sh"

# Purpose: Obtain a validation-only Grafana session cookie over HTTP.
# What it does:
# - Posts the configured local Grafana admin credentials to /login.
# - Returns a Cookie header value suitable for Grafana API requests.
# - Avoids coupling telemetry smoke checks to the separate OIDC callback path.
# Version: 3.0
# Last modified: 2026-05-02

_grafana_cookie_header_from_jar() {
  local cookie_jar="$1"
  awk '
    BEGIN { first = 1 }
    /^#HttpOnly_/ {
      sub(/^#HttpOnly_/, "", $1)
    }
    /^#/ { next }
    NF >= 7 {
      name = $6
      value = $7
      for (i = 8; i <= NF; i++) {
        value = value "\t" $i
      }
      if (!first) {
        printf "; "
      }
      printf "%s=%s", name, value
      first = 0
    }
  ' "$cookie_jar"
}

grafana_validation_cookie_header() {
  local _root_dir="$1"
  local grafana_url="$2"
  local login_user="$3"
  local login_password="$4"
  local tmp_dir
  local cookie_jar
  local login_body
  local login_headers
  local auth_check_body
  local auth_check_code
  local cookie_header

  if ! command -v curl >/dev/null 2>&1; then
    error "$my_name" "curl is required to complete the Grafana validation session"
    return 1
  fi

  tmp_dir="$(mktemp -d /tmp/grafana-oauth-session.XXXXXX)"
  cookie_jar="${tmp_dir}/cookies.txt"
  login_body="${tmp_dir}/login.json"
  login_headers="${tmp_dir}/login.headers"
  auth_check_body="${tmp_dir}/auth-check.json"

  trap 'rm -rf "$tmp_dir"' RETURN

  if ! curl -fsS -c "$cookie_jar" -b "$cookie_jar" -o "$login_body" -D "$login_headers" \
    -H 'Content-Type: application/json' \
    --data "{\"user\":\"${login_user}\",\"password\":\"${login_password}\"}" \
    "${grafana_url%/}/login" >/dev/null; then
    error "$my_name" "Unable to create Grafana validation session at ${grafana_url}"
    return 1
  fi

  if ! grep -q '"message":"Logged in"' "$login_body"; then
    error "$my_name" "Grafana validation login did not report success"
    cat "$login_body" >&2 || true
    return 1
  fi

  auth_check_code="$(curl -sS -o "$auth_check_body" -w '%{http_code}' -b "$cookie_jar" "${grafana_url%/}/api/user" || true)"
  if [[ "$auth_check_code" != "200" ]]; then
    error "$my_name" "Grafana validation login did not yield a usable session (HTTP ${auth_check_code})"
    cat "$auth_check_body" >&2 || true
    return 1
  fi

  cookie_header="$(_grafana_cookie_header_from_jar "$cookie_jar")"

  if [[ -z "$cookie_header" ]]; then
    error "$my_name" "Grafana validation login completed but no cookies were returned"
    return 1
  fi

  printf '%s\n' "$cookie_header"
}