#!/usr/bin/env bash
set -euo pipefail

# Purpose: Smoke test the dq-llm container endpoints.
# What it does:
# - Calls /health and verifies the service reports ok.
# - Calls /extract_rules with a sample payload.
# - Calls /generate_data_definitions with a BCBS 239-oriented sample payload.
# - Fails fast and prints response bodies on errors.
# Version: 1.1
# Last modified: 2026-05-26

BASE_URL="${DQ_LLM_BASE_URL:-https://127.0.0.1:8123}"
HEALTH_URL="${BASE_URL%/}/health"
EXTRACT_URL="${BASE_URL%/}/extract_rules"
GENERATE_DEFINITIONS_URL="${BASE_URL%/}/generate_data_definitions"
CA_BUNDLE="${DQ_LLM_CA_BUNDLE:-/etc/internal-certs/internal-ca-bundle.pem}"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

log_err() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log_err "FAIL: Missing required command: ${cmd}"
    exit 1
  fi
}

print_body() {
  local file_path="$1"
  if jq -e . "$file_path" >/dev/null 2>&1; then
    jq . "$file_path"
    return 0
  fi

  cat "$file_path"
}

require_cmd curl
require_cmd jq

TMP_DIR="$(mktemp -d)"
HEALTH_BODY_FILE="${TMP_DIR}/health.json"
EXTRACT_BODY_FILE="${TMP_DIR}/extract.json"
GENERATE_DEFINITIONS_BODY_FILE="${TMP_DIR}/generate_definitions.json"

cleanup() {
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT

log "Checking dq-llm at ${BASE_URL}"

log "[1/3] GET ${HEALTH_URL}"
HEALTH_CODE="$(curl -sS --connect-timeout 5 --max-time 10 --cacert "$CA_BUNDLE" -o "$HEALTH_BODY_FILE" -w "%{http_code}" "$HEALTH_URL")"
if [ "$HEALTH_CODE" != "200" ]; then
  log_err "FAIL: /health returned HTTP ${HEALTH_CODE}"
  print_body "$HEALTH_BODY_FILE"
  exit 1
fi

HEALTH_STATUS="$(jq -r '.status // empty' "$HEALTH_BODY_FILE")"
if [ "$HEALTH_STATUS" != "ok" ]; then
  log_err "FAIL: /health did not return status=ok"
  print_body "$HEALTH_BODY_FILE"
  exit 1
fi

log "PASS: /health returned ok"

log "[2/3] POST ${EXTRACT_URL}"
REQUEST_BODY="$(jq -nc --arg text 'The discount percentage must be lower than 10%.' '{text: $text}')"
EXTRACT_CODE="$(curl -sS --connect-timeout 5 --max-time 300 --cacert "$CA_BUNDLE" -o "$EXTRACT_BODY_FILE" -w "%{http_code}" \
  -X POST "$EXTRACT_URL" \
  -H 'content-type: application/json' \
  --data "$REQUEST_BODY")"
if [ "$EXTRACT_CODE" != "200" ]; then
  log_err "FAIL: /extract_rules returned HTTP ${EXTRACT_CODE}"
  print_body "$EXTRACT_BODY_FILE"
  exit 1
fi

if ! jq -e 'has("rules") and (.rules | if type == "string" or type == "array" then length > 0 else . != null end)' "$EXTRACT_BODY_FILE" >/dev/null; then
  log_err "FAIL: /extract_rules did not return a non-empty rules payload"
  print_body "$EXTRACT_BODY_FILE"
  exit 1
fi

log "PASS: /extract_rules returned a non-empty rules payload"
log "Requested: ${REQUEST_BODY}"
log "Response: $(cat "$EXTRACT_BODY_FILE")"

log "[3/3] POST ${GENERATE_DEFINITIONS_URL}"
GENERATE_REQUEST_BODY="$(jq -nc '{
  task_id: "dd-task-001",
  steward_name: "Jane Steward",
  board_name: "Data Definition Board",
  domain_name: "Retail Banking",
  source_system: "core_banking",
  user_input: "Draft a reviewable business definition for customer exposure amount.",
  policies: [
    "Support BCBS 239 traceability and controlled governance.",
    "Definitions must be reviewable by the Data Definition Board."
  ],
  targets: [
    {
      data_set_name: "credit_risk",
      data_object_name: "customer_exposure",
      attribute_name: "exposure_amount",
      data_type: "decimal(18,2)",
      nullable: false,
      sample_values: ["10500.00", "450000.25"],
      metadata: {
        regulatory_tags: ["bcbs239"],
        sensitivity: "confidential"
      }
    }
  ],
  context_documents: [
    {
      document_type: "logical_data_model",
      name: "Retail Banking LDM",
      content: "customer_exposure.exposure_amount stores the current reportable total exposure amount for the customer in EUR."
    },
    {
      document_type: "norms_and_forms",
      name: "Definition Standard",
      content: "Definitions must state business meaning, scope, and unit of measure."
    }
  ]
}')"
GENERATE_DEFINITIONS_CODE="$(curl -sS --connect-timeout 5 --max-time 300 --cacert "$CA_BUNDLE" -o "$GENERATE_DEFINITIONS_BODY_FILE" -w "%{http_code}" \
  -X POST "$GENERATE_DEFINITIONS_URL" \
  -H 'content-type: application/json' \
  --data "$GENERATE_REQUEST_BODY")"
if [ "$GENERATE_DEFINITIONS_CODE" != "200" ]; then
  log_err "FAIL: /generate_data_definitions returned HTTP ${GENERATE_DEFINITIONS_CODE}"
  print_body "$GENERATE_DEFINITIONS_BODY_FILE"
  exit 1
fi

if ! jq -e '
  .task_id == "dd-task-001" and
  (.registry_contract.definitions | type == "array" and length == 1) and
  (.openmetadata_import_contract.glossary_terms | type == "array" and length == 1) and
  (.board_review_packet.review_status | type == "string" and length > 0)
' "$GENERATE_DEFINITIONS_BODY_FILE" >/dev/null; then
  log_err "FAIL: /generate_data_definitions did not return the expected contract shape"
  print_body "$GENERATE_DEFINITIONS_BODY_FILE"
  exit 1
fi

log "PASS: /generate_data_definitions returned an importable contract payload"
log "Requested: ${GENERATE_REQUEST_BODY}"
log "Response: $(cat "$GENERATE_DEFINITIONS_BODY_FILE")"
log "PASS: dq-llm smoke test succeeded"