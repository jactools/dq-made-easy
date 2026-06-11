#!/usr/bin/env bash
set -euo pipefail

# Purpose: Enforce testing-adapter ownership boundaries for the FastAPI backend.
#
# What it does:
# - Fails if any live app module imports the testing_route_support compatibility surface.
# - Fails if non-API layers import endpoint modules directly.
# - Allows testing_route_support imports only in the small set of explicit compatibility-focused tests.
#
# validate: groups=repo,api
#
# Version: 1.0
# Last modified: 2026-04-25
# Changelog:
# - 1.0 (2026-04-25): Added static enforcement for testing compatibility-surface usage and non-API endpoint imports.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_testing_architecture_boundaries.sh"

COMPAT_IMPORT_REGEX='^[[:space:]]*(from[[:space:]]+app\.api\.v1([[:space:]]+import[[:space:]]+testing_route_support|\.testing_route_support[[:space:]]+import)|import[[:space:]]+app\.api\.v1\.testing_route_support([[:space:]]|$))'
ENDPOINT_IMPORT_REGEX='^[[:space:]]*(from[[:space:]]+app\.api\.v1\.endpoints[[:space:]]+import|import[[:space:]]+app\.api\.v1\.endpoints(\.|[[:space:]]|$))'

is_allowed_compat_test() {
  local rel="$1"
  case "$rel" in
    dq-api/fastapi/tests/api/test_testing_endpoint_helpers_focus.py|dq-api/fastapi/tests/api/test_testing_route_support_materialization.py|dq-api/fastapi/tests/api/test_testing_route_support_queueing.py)
      return 0
      ;;
  esac
  return 1
}

report_matches() {
  local rel="$1"
  local regex="$2"
  local description="$3"
  local matches

  matches="$(grep -nE "$regex" "$ROOT_DIR/$rel" || true)"
  [[ -n "$matches" ]] || return 0

  while IFS= read -r match_line; do
    [[ -n "$match_line" ]] || continue
    error "$my_name" "$rel:$match_line: $description"
  done <<EOF
$matches
EOF
  return 1
}

main() {
  local rel
  local failures=0

  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    if report_matches "$rel" "$COMPAT_IMPORT_REGEX" "Live app modules must not import testing_route_support; use the owner adapters instead."; then
      :
    else
      failures=$((failures + 1))
    fi
  done < <(
    find "$ROOT_DIR/dq-api/fastapi/app" -type f -name '*.py' \
      ! -path "$ROOT_DIR/dq-api/fastapi/app/api/v1/testing_route_support.py" \
      | LC_ALL=C sort \
      | sed "s#^$ROOT_DIR/##"
  )

  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    if report_matches "$rel" "$ENDPOINT_IMPORT_REGEX" "Non-API layers must not import endpoint modules directly."; then
      :
    else
      failures=$((failures + 1))
    fi
  done < <(
    find \
      "$ROOT_DIR/dq-api/fastapi/app/application" \
      "$ROOT_DIR/dq-api/fastapi/app/domain" \
      "$ROOT_DIR/dq-api/fastapi/app/infrastructure" \
      "$ROOT_DIR/dq-api/fastapi/app/core" \
      -type f -name '*.py' \
      | LC_ALL=C sort \
      | sed "s#^$ROOT_DIR/##"
  )

  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    if ! grep -qE "$COMPAT_IMPORT_REGEX" "$ROOT_DIR/$rel"; then
      continue
    fi
    if is_allowed_compat_test "$rel"; then
      continue
    fi

    report_matches "$rel" "$COMPAT_IMPORT_REGEX" "Only explicit compatibility-focused tests may import testing_route_support." || true
    failures=$((failures + 1))
  done < <(
    find "$ROOT_DIR/dq-api/fastapi/tests" -type f -name '*.py' \
      | LC_ALL=C sort \
      | sed "s#^$ROOT_DIR/##"
  )

  if [[ $failures -gt 0 ]]; then
    error "$my_name" "testing architecture boundary validation found ${failures} violation set(s)."
    exit 1
  fi

  success "$my_name" "testing architecture boundaries are enforced"
}

main "$@"