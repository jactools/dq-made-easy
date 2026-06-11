#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Smoke test: frontend + API endpoints =="

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Required command not found: $1"; exit 2; }
}

require_cmd curl
require_cmd jq

FAILED=0

check_url() {
  local url=$1
  local expect_code=${2:-200}
  local code
  code=$(curl -sS -o /dev/null -w "%{http_code}" "$url" || true)
  if [ "$code" != "$expect_code" ]; then
    echo "FAIL: $url returned HTTP $code (expected $expect_code)"
    FAILED=1
  else
    echo "OK: $url -> $code"
  fi
}

echo "Checking frontend root (http://localhost:5173/)"
check_url http://localhost:5173/ 200

echo "Checking frontend /applied"
check_url http://localhost:5173/applied 200

echo "Checking API endpoints"
# rules
RCOUNT=$(curl -sS http://localhost:4001/rules | jq ". | length" 2>/dev/null || echo "-")
if [ "$RCOUNT" = "-" ] || [ "$RCOUNT" -lt 0 ]; then
  echo "FAIL: /rules did not respond"
  FAILED=1
else
  echo "OK: /rules count=$RCOUNT"
fi

ACOUNT=$(curl -sS http://localhost:4001/attributes-catalog | jq ". | length" 2>/dev/null || echo "-")
if [ "$ACOUNT" = "-" ]; then
  echo "FAIL: /attributes-catalog did not respond"
  FAILED=1
else
  echo "OK: /attributes-catalog count=$ACOUNT"
fi

APPCOUNT=$(curl -sS http://localhost:4001/approvals | jq ". | length" 2>/dev/null || echo "-")
if [ "$APPCOUNT" = "-" ]; then
  echo "FAIL: /approvals did not respond"
  FAILED=1
else
  echo "OK: /approvals count=$APPCOUNT"
fi

UCOUNT=$(curl -sS http://localhost:4001/users | jq ".items | length" 2>/dev/null || echo "-")
if [ "$UCOUNT" = "-" ]; then
  echo "FAIL: /users did not respond"
  FAILED=1
else
  echo "OK: /users items=$UCOUNT"
fi

WCOUNT=$(curl -sS http://localhost:4001/workspaces | jq ". | length" 2>/dev/null || echo "-")
if [ "$WCOUNT" = "-" ]; then
  echo "FAIL: /workspaces did not respond"
  FAILED=1
else
  echo "OK: /workspaces count=$WCOUNT"
fi

APPCONFIG=$(curl -sS http://localhost:4001/app-config 2>/dev/null || echo "")
if [ -z "$APPCONFIG" ]; then
  echo "FAIL: /app-config did not respond"
  FAILED=1
else
  echo "OK: /app-config -> $APPCONFIG"
fi

if [ "$FAILED" -ne 0 ]; then
  echo "Smoke test FAILED"
  exit 1
fi

echo "Smoke test PASSED"
exit 0
