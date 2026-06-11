#!/usr/bin/env bash
set -euo pipefail

# Purpose: Smoke-test the onboarding end-to-end flow in a seeded environment.
#
# What it does:
# - Loads connection details from the selected env file (--env dev|test|prod).
# - Obtains a Keycloak access token for the seeded user.
# - Resolves the seeded workspace UUID by looking up the canonical seeded
#   workspace name ("Default Workspace") via GET /workspaces.
# - Calls POST /rulebuilder/v1/onboarding/scope-summary (workspace scope) and
#   asserts attributes > 0.
# - Calls POST /rulebuilder/v1/onboarding/generate-proposals and asserts
#   total_proposals > 0 and proposals array is non-empty.
# - Submits the first uncovered proposal_id to POST /rulebuilder/v1/onboarding/create-batch
#   and asserts created >= 1 (or skipped >= 1 if already run before) and
#   batch_id is present.
#
# validate: groups=api,regression
#
# Version: 1.3
# Last modified: 2026-06-01
# Changelog:
# - 1.3 (2026-06-01): Construct proposal_id as template_id::data_object_version_id::attribute_id instead of reading a non-existent .proposal_id field.
# - 1.2 (2026-06-01): Load env via root_env_file.sh; bake in seeded workspace name constant; remove all external env-var dependencies.
# - 1.1 (2026-06-01): Resolve workspace ID by name via GET /workspaces so callers need not know the internal UUID.
# - 1.0 (2026-06-01): Initial implementation for ONB-1 acceptance criterion.

# ── Seeded workspace this smoke test targets ─────────────────────────────────
# This is the canonical name of the workspace created by the standard DB seed.
# It is a constant, not a caller-supplied value.
SMOKE_WORKSPACE_NAME="Retail Banking"

# ── Bootstrap ────────────────────────────────────────────────────────────────
__dq_scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${__dq_scripts_dir}/../.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

SCRIPT_NAME="smoke_onboarding_flow.sh"
set_log_level INFO

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  exit 1
fi
set -- "${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"

validate_selected_root_env_file "$ROOT_DIR" full

if ! source_selected_root_env_file; then
  exit 1
fi

if [[ $# -gt 0 ]]; then
  error "$SCRIPT_NAME" "Unknown argument: $1"
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/auth.sh"
dq_source_seeded_user_credentials --quiet

# ── Derived connection details (from sourced env file) ───────────────────────
KONG_PUBLIC_URL="${KONG_PUBLIC_URL:?KONG_PUBLIC_URL must be set in the selected env file}"
KEYCLOAK_ISSUER_URL="${SSO_PUBLIC_ISSUER_URL:?SSO_PUBLIC_ISSUER_URL must be set in the selected env file}"
KEYCLOAK_CLIENT_ID="${VITE_KEYCLOAK_CLIENT_ID:?VITE_KEYCLOAK_CLIENT_ID must be set in the selected env file}"
LOGIN_EMAIL="${KEYCLOAK_JACCLOUD_USERNAME:?KEYCLOAK_JACCLOUD_USERNAME must be set (loaded from seeded credentials)}"
LOGIN_PASSWORD="${KEYCLOAK_JACCLOUD_PASSWORD:?KEYCLOAK_JACCLOUD_PASSWORD must be set (loaded from seeded credentials)}"

if [[ "$KONG_PUBLIC_URL" != https://* ]]; then
  error "$SCRIPT_NAME" "KONG_PUBLIC_URL must use https:// (got ${KONG_PUBLIC_URL})"
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  error "$SCRIPT_NAME" "curl is required"
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  error "$SCRIPT_NAME" "jq is required"
  exit 1
fi

KEYCLOAK_TOKEN_URL="${KEYCLOAK_ISSUER_URL%/}/protocol/openid-connect/token"
ONBOARDING_BASE="${KONG_PUBLIC_URL%/}/rulebuilder/v1/onboarding"

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

SCOPE_SUMMARY_BODY="${TMP_DIR}/scope_summary.json"
PROPOSALS_BODY="${TMP_DIR}/proposals.json"
BATCH_BODY="${TMP_DIR}/batch.json"

print_body() {
  local f="$1"
  if jq -e . "$f" >/dev/null 2>&1; then jq . "$f"; else cat "$f"; fi
}

# ────────────────────────────────────────────────────────────────────────────
info "$SCRIPT_NAME" "========================================"
info "$SCRIPT_NAME" "Onboarding End-to-End Smoke Test"
info "$SCRIPT_NAME" "========================================"

# Step 1: Authenticate
info "$SCRIPT_NAME" "[1/4] Obtaining Keycloak access token for ${LOGIN_EMAIL}..."
TOKEN="$(dq_keycloak_password_grant_access_token "$KEYCLOAK_TOKEN_URL" "$KEYCLOAK_CLIENT_ID" "$LOGIN_EMAIL" "$LOGIN_PASSWORD")"
case "$TOKEN" in
  *.*.*)  ;;
  *)
    error "$SCRIPT_NAME" "Keycloak returned a non-JWT token"
    exit 1
    ;;
esac
success "$SCRIPT_NAME" "Token obtained for ${LOGIN_EMAIL}"

# Step 1b: Resolve the seeded workspace UUID from its canonical name.
info "$SCRIPT_NAME" "[1b] Resolving workspace ID for seeded workspace '${SMOKE_WORKSPACE_NAME}'..."
WORKSPACES_BODY="${TMP_DIR}/workspaces.json"
WORKSPACES_CODE="$(curl -sS \
  -H "Authorization: Bearer ${TOKEN}" \
  -G \
  --data-urlencode "limit=100" \
  -o "$WORKSPACES_BODY" -w "%{http_code}" \
  "${KONG_PUBLIC_URL%/}/rulebuilder/v1/workspaces")"
if [ "$WORKSPACES_CODE" != "200" ]; then
  error "$SCRIPT_NAME" "GET /workspaces returned HTTP ${WORKSPACES_CODE}"
  print_body "$WORKSPACES_BODY"
  exit 1
fi
WORKSPACE_ID="$(jq -r --arg name "$SMOKE_WORKSPACE_NAME" \
  '.data[] | select(.name == $name) | .id // empty' \
  "$WORKSPACES_BODY" | head -1)"
if [ -z "$WORKSPACE_ID" ]; then
  error "$SCRIPT_NAME" "Seeded workspace '${SMOKE_WORKSPACE_NAME}' not found. Is the database seeded? Available workspaces:"
  jq -r '.data[] | "  \(.id)  \(.name)"' "$WORKSPACES_BODY" >&2
  exit 1
fi
success "$SCRIPT_NAME" "Resolved '${SMOKE_WORKSPACE_NAME}' → workspace_id=${WORKSPACE_ID}"

# Step 2: scope-summary (workspace level)
info "$SCRIPT_NAME" "[2/4] POST /onboarding/scope-summary (workspace scope)..."
SCOPE_CODE="$(curl -sS \
  -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"scope_type\":\"workspace\",\"scope_id\":\"${WORKSPACE_ID}\",\"workspace_id\":\"${WORKSPACE_ID}\"}" \
  -o "$SCOPE_SUMMARY_BODY" -w "%{http_code}" \
  "${ONBOARDING_BASE}/scope-summary")"

if [ "$SCOPE_CODE" != "200" ]; then
  error "$SCRIPT_NAME" "scope-summary returned HTTP ${SCOPE_CODE}"
  print_body "$SCOPE_SUMMARY_BODY"
  exit 1
fi

ATTR_COUNT="$(jq -r '.attribute_count // 0' "$SCOPE_SUMMARY_BODY")"
if [ "${ATTR_COUNT:-0}" -lt 1 ]; then
  error "$SCRIPT_NAME" "scope-summary returned attribute_count=${ATTR_COUNT}; seeded environment must have at least 1 attribute"
  print_body "$SCOPE_SUMMARY_BODY"
  exit 1
fi
success "$SCRIPT_NAME" "scope-summary: attribute_count=${ATTR_COUNT}"

# Step 3: generate-proposals
info "$SCRIPT_NAME" "[3/4] POST /onboarding/generate-proposals (workspace scope)..."
PROPOSALS_CODE="$(curl -sS \
  -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"scope_type\":\"workspace\",\"scope_id\":\"${WORKSPACE_ID}\",\"workspace_id\":\"${WORKSPACE_ID}\"}" \
  -o "$PROPOSALS_BODY" -w "%{http_code}" \
  "${ONBOARDING_BASE}/generate-proposals")"

if [ "$PROPOSALS_CODE" != "200" ]; then
  error "$SCRIPT_NAME" "generate-proposals returned HTTP ${PROPOSALS_CODE}"
  print_body "$PROPOSALS_BODY"
  exit 1
fi

TOTAL_PROPOSALS="$(jq -r '.total_proposals // 0' "$PROPOSALS_BODY")"
if [ "${TOTAL_PROPOSALS:-0}" -lt 1 ]; then
  error "$SCRIPT_NAME" "generate-proposals returned total_proposals=${TOTAL_PROPOSALS}; expected > 0 in a seeded environment"
  print_body "$PROPOSALS_BODY"
  exit 1
fi
success "$SCRIPT_NAME" "generate-proposals: total_proposals=${TOTAL_PROPOSALS}"

# Log a proposal breakdown: per-template counts and covered vs uncovered totals.
UNCOVERED_TOTAL="$(jq '[.proposals[].by_dataset[][] | .attributes[] | select(.already_covered == false)] | length' "$PROPOSALS_BODY")"
COVERED_TOTAL="$(jq '[.proposals[].by_dataset[][] | .attributes[] | select(.already_covered == true)] | length' "$PROPOSALS_BODY")"
info "$SCRIPT_NAME" "  uncovered=${UNCOVERED_TOTAL}  already_covered=${COVERED_TOTAL}  (total_proposals counts all, both covered and uncovered)"
info "$SCRIPT_NAME" "  proposals by template:"
jq -r '
  [ .proposals[] | {t: .template_name, dim: .dimension, total: .total_count} ]
  | sort_by(.dim, .t)[]
  | "    \(.dim) | \(.t): \(.total) proposals"
' "$PROPOSALS_BODY" | while IFS= read -r line; do info "$SCRIPT_NAME" "$line"; done

# Extract the first non-covered proposal and construct its proposal_id.
# The create-batch endpoint expects the canonical format:
#   template_id::data_object_version_id::attribute_id
# The generate-proposals response does not include a pre-built proposal_id field;
# it must be composed from the nested structure.
FIRST_PROPOSAL_ID="$(jq -r '
  first(
    .proposals[] as $tg |
    $tg.by_dataset[][] as $og |
    $og.attributes[] |
    select(.already_covered == false) |
    [$tg.template_id, $og.data_object_version_id, .attribute_id] | join("::")
  ) // empty
' "$PROPOSALS_BODY")"

if [ -z "$FIRST_PROPOSAL_ID" ]; then
  error "$SCRIPT_NAME" "No uncovered proposal found in generate-proposals response; seeded environment must have at least one uncovered attribute"
  exit 1
fi
info "$SCRIPT_NAME" "First uncovered proposal_id: ${FIRST_PROPOSAL_ID}"

# Step 4: create-batch (single proposal — smoke test submits 1 to keep it minimal and idempotent)
info "$SCRIPT_NAME" "[4/4] POST /onboarding/create-batch (1 of ${UNCOVERED_TOTAL} uncovered proposals; smoke submits first as a representative sample)..."
BATCH_PAYLOAD="$(printf '{"workspace_id":"%s","accepted_proposal_ids":["%s"]}' "$WORKSPACE_ID" "$FIRST_PROPOSAL_ID")"
BATCH_CODE="$(curl -sS \
  -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$BATCH_PAYLOAD" \
  -o "$BATCH_BODY" -w "%{http_code}" \
  "${ONBOARDING_BASE}/create-batch")"

if [ "$BATCH_CODE" != "200" ]; then
  error "$SCRIPT_NAME" "create-batch returned HTTP ${BATCH_CODE}"
  print_body "$BATCH_BODY"
  exit 1
fi

BATCH_ID="$(jq -r '.batch_id // empty' "$BATCH_BODY")"
CREATED_COUNT="$(jq -r '.created // 0' "$BATCH_BODY")"
if [ -z "$BATCH_ID" ] || [ "$BATCH_ID" = "null" ]; then
  error "$SCRIPT_NAME" "create-batch response did not include batch_id"
  print_body "$BATCH_BODY"
  exit 1
fi
if [ "${CREATED_COUNT:-0}" -lt 1 ]; then
  # Proposal may already exist from a previous smoke run; skip is acceptable.
  SKIPPED_COUNT="$(jq -r '.skipped // 0' "$BATCH_BODY")"
  if [ "${SKIPPED_COUNT:-0}" -lt 1 ]; then
    error "$SCRIPT_NAME" "create-batch: created=${CREATED_COUNT} skipped=${SKIPPED_COUNT}; expected created>=1 or skipped>=1"
    print_body "$BATCH_BODY"
    exit 1
  fi
  info "$SCRIPT_NAME" "create-batch: batch_id=${BATCH_ID} created=${CREATED_COUNT} skipped=${SKIPPED_COUNT} (already exists — acceptable)"
else
  success "$SCRIPT_NAME" "create-batch: batch_id=${BATCH_ID} created=${CREATED_COUNT}"
fi

info "$SCRIPT_NAME" "========================================"
success "$SCRIPT_NAME" "Onboarding end-to-end smoke test PASSED"
info "$SCRIPT_NAME" "========================================"
