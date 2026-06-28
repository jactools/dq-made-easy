#!/usr/bin/env bash
set -euo pipefail

# Purpose: Enforce narrow ownership of compatibility and adapter-facing FastAPI API modules.
#
# What it does:
# - Fails if `app/api/v1/testing_api.py` is imported outside the testing endpoint and its explicit compatibility-focused tests.
# - Fails if `app/api/v1/gx_runtime_api.py` is imported outside the GX/data-catalog endpoint owners, its shared GX execution adapter, and explicit GX adapter tests.
# - Keeps compatibility delegates and runtime adapter modules from quietly becoming shared ownership surfaces again.
#
# validate: groups=repo,api
#
# Version: 1.1
# Last modified: 2026-06-28
# Changelog:
# - 1.1 (2026-05-14): Updated the allowlist for the renamed execution monitoring endpoint test file.
# - 1.2 (2026-06-28): Added the GX endpoint, validation run plan adapter, and focused testing adapter test imports to the allowlist.

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_fastapi_api_adapter_boundaries.sh"

TESTING_API_IMPORT_REGEX='^[[:space:]]*(from[[:space:]]+app\.api\.v1([[:space:]]+import[[:space:]]+testing_api|\.testing_api[[:space:]]+import)|import[[:space:]]+app\.api\.v1\.testing_api([[:space:]]|$))'
GX_RUNTIME_API_IMPORT_REGEX='^[[:space:]]*(from[[:space:]]+app\.api\.v1([[:space:]]+import[[:space:]]+gx_runtime_api|\.gx_runtime_api[[:space:]]+import)|import[[:space:]]+app\.api\.v1\.gx_runtime_api([[:space:]]|$))'

is_allowed_testing_api_importer() {
  local rel="$1"
  case "$rel" in
    dq-api/fastapi/app/api/v1/endpoints/testing.py|dq-api/fastapi/tests/api/test_endpoint_focus.py|dq-api/fastapi/tests/api/test_testing_api_focus.py|dq-api/fastapi/tests/api/test_testing_generated_proof_persistence.py)
      return 0
      ;;
  esac
  return 1
}

is_allowed_gx_runtime_api_importer() {
  local rel="$1"
  case "$rel" in
    dq-api/fastapi/app/api/v1/endpoints/execution_monitoring.py|dq-api/fastapi/app/api/v1/endpoints/data_catalog.py|dq-api/fastapi/app/api/v1/endpoints/gx.py|dq-api/fastapi/app/api/v1/gx_execution_api.py|dq-api/fastapi/app/api/v1/validation_run_plan_api.py|dq-api/fastapi/tests/api/test_execution_monitoring_payload_building.py|dq-api/fastapi/tests/api/test_gx_endpoint_payload_building.py|dq-api/fastapi/tests/api/test_gx_queue_status.py)
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

scan_import_boundary() {
  local regex="$1"
  local description="$2"
  local allow_fn="$3"
  local rel
  local failures=0

  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    if ! grep -qE "$regex" "$ROOT_DIR/$rel"; then
      continue
    fi
    if "$allow_fn" "$rel"; then
      continue
    fi

    report_matches "$rel" "$regex" "$description" || true
    failures=$((failures + 1))
  done < <(
    find "$ROOT_DIR/dq-api/fastapi/app" "$ROOT_DIR/dq-api/fastapi/tests" -type f -name '*.py' \
      | LC_ALL=C sort \
      | sed "s#^$ROOT_DIR/##"
  )

  if [[ $failures -gt 0 ]]; then
    return 1
  fi

  return 0
}

main() {
  local failures=0

  if ! scan_import_boundary \
    "$TESTING_API_IMPORT_REGEX" \
    "Only app/api/v1/endpoints/testing.py and explicit compatibility-focused tests may import testing_api; use owner adapters directly elsewhere." \
    is_allowed_testing_api_importer; then
    failures=$((failures + 1))
  fi

  if ! scan_import_boundary \
    "$GX_RUNTIME_API_IMPORT_REGEX" \
    "Only the GX/data-catalog endpoint owners, gx_execution_api, and explicit GX adapter tests may import gx_runtime_api." \
    is_allowed_gx_runtime_api_importer; then
    failures=$((failures + 1))
  fi

  if [[ $failures -gt 0 ]]; then
    error "$my_name" "FastAPI API adapter boundary validation found ${failures} violation set(s)."
    exit 1
  fi

  success "$my_name" "FastAPI API adapter boundaries are enforced"
}

main "$@"