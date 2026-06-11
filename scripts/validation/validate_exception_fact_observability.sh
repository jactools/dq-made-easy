#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate exception-fact observability assets.
# What it does:
# - Ensures Postgres exporter exposes exception-fact drift and freshness metrics.
# - Ensures Prometheus alerts and recording rules cover exception-fact drift and freshness.
# - Ensures the execution dashboard exposes exception-fact observability panels.
# validate: groups=repo,observability,api
# Version: 1.0
# Last modified: 2026-05-06

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_exception_fact_observability.sh"
QUERY_FILE="${ROOT_DIR}/observability/postgres-exporter/queries.yaml"
ALERT_FILE="${ROOT_DIR}/observability/prometheus/alerts.yml"
DASHBOARD_FILE="${ROOT_DIR}/observability/grafana/provisioning/dashboards/dq-execution-monitoring.json"

require_in_file() {
  local needle="$1"
  local file="$2"
  if ! grep -Fq "$needle" "$file"; then
    error "$my_name" "Missing '${needle}' in ${file}"
    exit 1
  fi
}

for file in "$QUERY_FILE" "$ALERT_FILE" "$DASHBOARD_FILE"; do
  if [[ ! -f "$file" ]]; then
    error "$my_name" "Missing ${file}"
    exit 1
  fi
done

require_in_file 'gx_exception_facts_noncanonical:' "$QUERY_FILE"
require_in_file 'gx_exception_facts_oldest_noncanonical_age:' "$QUERY_FILE"
require_in_file 'gx_exception_facts_latest_canonical_detected_age:' "$QUERY_FILE"

require_in_file 'alert: GXExceptionFactContractDrift' "$ALERT_FILE"
require_in_file 'alert: GXExceptionAnalyticsFreshnessLag' "$ALERT_FILE"
require_in_file 'record: dq_exception_noncanonical_facts' "$ALERT_FILE"
require_in_file 'record: dq_exception_oldest_noncanonical_age_seconds' "$ALERT_FILE"
require_in_file 'record: dq_exception_latest_canonical_detected_age_seconds' "$ALERT_FILE"

require_in_file '"title": "Non-Canonical Exception Facts"' "$DASHBOARD_FILE"
require_in_file '"title": "Oldest Non-Canonical Age (s)"' "$DASHBOARD_FILE"
require_in_file '"title": "Latest Canonical Fact Age (s)"' "$DASHBOARD_FILE"

success "$my_name" "exception-fact observability checks passed"