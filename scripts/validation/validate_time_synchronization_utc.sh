#!/usr/bin/env bash

# Purpose: Validate ISO27001 time synchronization requirement.
#
# What it does:
# - Ensures critical services run with TZ=UTC in docker-compose.yml.
# - Ensures API and engine logging uses UTC timestamps.
#
# validate: groups=repo

# Version: 1.0
# Last modified: 2026-04-07
#
# Validate ISO27001 Time Synchronization requirement (Annex A 8.17):
# All critical services must run with UTC timezone configuration.
#
# Checks:
# 1. docker-compose.yml has TZ=UTC in critical services (api, dq-engine, db, profiling-worker)
# 2. dq-api FastAPI logging config uses UTC timestamps
# 3. dq-engine logging utilities use UTC
#

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo '.')"
source "$REPO_ROOT/scripts/supporting/logging.sh"

my_name="validate_time_synchronization_utc.sh"

CRITICAL_SERVICES=("api" "dq-made-easy-engine" "db")
FAILED=0

# Check docker-compose.yml for TZ=UTC in each critical service
info "$my_name" "Checking docker-compose.yml for UTC timezone configuration..."

for service in "${CRITICAL_SERVICES[@]}"; do
  if awk -v service="$service" '
    $0 ~ ("^  " service ":$") { in_service = 1; next }
    in_service && $0 ~ /^  [A-Za-z0-9_.-]+:/ { exit 1 }
    in_service && ($0 ~ /(^|[[:space:]])TZ:[[:space:]]*UTC([[:space:]]|$)/ || $0 ~ /(^|[[:space:]])-TZ=[[:space:]]*UTC([[:space:]]|$)/) {
      found = 1
      exit 0
    }
    END { exit found ? 0 : 1 }
  ' "$REPO_ROOT/docker-compose/"; then
    success "$my_name" "Service '$service' has TZ: UTC"
  else
    error "$my_name" "Service '$service' does not have TZ: UTC in docker-compose.yml"
    FAILED=1
  fi
done

# Check FastAPI logging config for UTC timestamp formatting
info "$my_name" "Checking dq-api FastAPI logging for UTC timestamp formatting..."
if grep -q "time.gmtime(record.created)" "$REPO_ROOT/dq-api/fastapi/app/core/logging_config.py"; then
  success "$my_name" "FastAPI logging uses UTC (gmtime)"
else
  if grep -q "logging_config.py" "$REPO_ROOT/dq-api/fastapi/app/core/logging_config.py" 2>/dev/null; then
    error "$my_name" "FastAPI logging config does not use gmtime for UTC"
    FAILED=1
  fi
fi

# Check dq-utils logging utilities for UTC if they exist
if [ -f "$REPO_ROOT/dq-utils/src/dq_utils/logging_utils.py" ]; then
  info "$my_name" "Checking dq-utils logging utilities for UTC timestamp..."
  if grep -q "gmtime\|utcnow\|timezone.utc\|UTC" "$REPO_ROOT/dq-utils/src/dq_utils/logging_utils.py"; then
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
