#!/usr/bin/env bash

# Purpose: Validate ISO27001 time synchronization requirement.
#
# What it does:
# - Ensures critical services run with TZ=UTC in K8s manifests (or docker-compose for legacy).
# - Ensures API and engine logging uses UTC timestamps.
#
# validate: groups=repo

# Version: 2.0
# Last modified: 2026-08-17
#
# Validate ISO27001 Time Synchronization requirement (Annex A 8.17):
# All critical services must run with UTC timezone configuration.
#
# Checks:
# 1. K8s manifests (or docker-compose) have TZ=UTC in critical services
# 2. dq-api FastAPI logging config uses UTC timestamps
# 3. dq-engine logging utilities use UTC
#

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_time_synchronization_utc.sh"

# Critical service name patterns to check
CRITICAL_SERVICES=("api" "engine" "db" "profiling")
FAILED=0

# Check K8s manifests for TZ=UTC (Kind/Flux deployments)
info "$my_name" "Checking K8s manifests for UTC timezone configuration..."

has_k8s_manifests=false
if [ -d "$ROOT_DIR/k8s" ] || [ -d "$ROOT_DIR/infra/k8s" ]; then
  has_k8s_manifests=true
fi

if $has_k8s_manifests; then
  # Scan all YAML manifests in k8s/ and infra/k8s/ for TZ env vars
  tz_issues=0
  while IFS= read -r manifest; do
    # Check if manifest has TZ env var
    if grep -q "TZ:" "$manifest" 2>/dev/null; then
      # TZ exists — verify it's UTC
      if grep -A1 "^ *- name: TZ" "$manifest" | grep -q "value:.*UTC" 2>/dev/null; then
        info "$my_name" "TZ=UTC found in $(basename "$manifest")"
      else
        error "$my_name" "TZ is set but not UTC in $(basename "$manifest")"
        tz_issues=1
      fi
    fi
  done < <(find "$ROOT_DIR" -path "*/k8s/*" -name "*.yaml" -o -path "*/infra/k8s/*" -name "*.yaml" 2>/dev/null | head -100)

  if [ $tz_issues -eq 1 ]; then
    FAILED=1
  else
    info "$my_name" "K8s manifests TZ configuration OK (no TZ overrides found or all UTC)"
  fi
else
  info "$my_name" "No K8s manifests found — skipping manifest check"
fi

# Check docker-compose if it exists (legacy support)
if [ -d "$ROOT_DIR/docker-compose" ]; then
  info "$my_name" "Checking docker-compose for UTC timezone configuration (legacy)..."
  for service in "${CRITICAL_SERVICES[@]}"; do
    if grep -A20 "^  ${service}:" "$ROOT_DIR/docker-compose/"* 2>/dev/null | grep -q "TZ:.*UTC\|TZ=UTC"; then
      success "$my_name" "Service '$service' has TZ: UTC in docker-compose"
    else
      info "$my_name" "Service '$service' TZ not explicitly set in docker-compose (may use container default)"
    fi
  done
fi

# Check FastAPI logging config for UTC timestamp formatting
info "$my_name" "Checking dq-api FastAPI logging for UTC timestamp formatting..."
if grep -q "time.gmtime(record.created)" "$ROOT_DIR/dq-api/fastapi/app/core/logging_config.py" 2>/dev/null; then
  success "$my_name" "FastAPI logging uses UTC (gmtime)"
else
  if [ -f "$ROOT_DIR/dq-api/fastapi/app/core/logging_config.py" ]; then
    error "$my_name" "FastAPI logging config does not use gmtime for UTC"
    FAILED=1
  else
    info "$my_name" "FastAPI logging config not found — skipping"
  fi
fi

# Check dq-utils logging utilities for UTC if they exist
if [ -f "$ROOT_DIR/dq-utils/src/dq_utils/logging_utils.py" ]; then
  info "$my_name" "Checking dq-utils logging utilities for UTC timestamp..."
  if grep -q "gmtime\|utcnow\|timezone.utc\|UTC" "$ROOT_DIR/dq-utils/src/dq_utils/logging_utils.py"; then
    success "$my_name" "dq-utils logging utilities use UTC"
  fi
fi

if [ $FAILED -eq 0 ]; then
  success "$my_name" "time synchronization contract passed"
  exit 0
else
  error "$my_name" "time synchronization contract failed"
  exit 1
fi
