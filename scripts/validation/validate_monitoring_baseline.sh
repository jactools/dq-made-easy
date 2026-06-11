#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate monitoring configuration baseline (Prometheus + alerts).
#
# What it does:
# - Ensures Prometheus scrape jobs baseline exists.
# - Ensures alerting rules baseline exists.
#
# validate: groups=repo,governance,observability

# Version: 1.2
# Last modified: 2026-04-20

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_monitoring_baseline.sh"
PROM_FILE="${ROOT_DIR}/observability/prometheus/prometheus.yml"
ALERT_FILE="${ROOT_DIR}/observability/prometheus/alerts.yml"

if [[ ! -f "${PROM_FILE}" ]]; then
  error "$my_name" "Missing ${PROM_FILE}"
  exit 1
fi

if [[ ! -f "${ALERT_FILE}" ]]; then
  error "$my_name" "Missing ${ALERT_FILE}"
  exit 1
fi

require_in_file() {
  local needle="$1"
  local file="$2"
  if ! grep -Fq "$needle" "$file"; then
    error "$my_name" "Missing '${needle}' in ${file}"
    exit 1
  fi
}

# Prometheus scrape coverage baseline (core observability + app services)
require_in_file 'job_name: "prometheus"' "$PROM_FILE"
require_in_file 'job_name: "otel-collector"' "$PROM_FILE"
require_in_file 'job_name: "dq-engine"' "$PROM_FILE"
require_in_file 'job_name: "loki"' "$PROM_FILE"
require_in_file 'job_name: "tempo"' "$PROM_FILE"
require_in_file 'job_name: "grafana"' "$PROM_FILE"
require_in_file 'job_name: "pushgateway"' "$PROM_FILE"

# Alerting baseline (failure + latency + availability)
require_in_file 'alert: HighHTTPErrorRate' "$ALERT_FILE"
require_in_file 'alert: HighAuthFailureRate' "$ALERT_FILE"
require_in_file 'alert: RuleExecutionP95Latency' "$ALERT_FILE"
require_in_file 'alert: RuleExecutionP99Latency' "$ALERT_FILE"
require_in_file 'alert: RuleExceptionStoreWriteFailure' "$ALERT_FILE"
require_in_file 'alert: GXExecutorWorkerHeartbeatMissing' "$ALERT_FILE"
require_in_file 'alert: ServiceDown' "$ALERT_FILE"
require_in_file 'alert: PrometheusDown' "$ALERT_FILE"
require_in_file 'alert: TempoDown' "$ALERT_FILE"
require_in_file 'alert: GrafanaDown' "$ALERT_FILE"

success "$my_name" "monitoring baseline checks passed"
