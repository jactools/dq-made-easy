#!/usr/bin/env bash

# Purpose: Validate that dataset counts per workspace match between database and mock-data CSV.
#
# What it does:
# - Reads data-sets.csv mock-data file
# - Queries the database for actual dataset counts by workspace
# - Compares expected vs actual counts
# - Reports any mismatches with details
# - Exits 0 if all counts match, 1 if any mismatch found
#
# Version: 1.0
# Last modified: 2026-05-31
# Changelog:
# - 1.0 (2026-05-31): Initial implementation to validate datasets per workspace during seeding

# validate: groups=repo
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="validate_datasets_per_workspace.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

CSV_FILE="${1:-dq-db/mock-data/data-sets.csv}"
DB_HOST="${2:-${DQ_DB_HOST:-localhost}}"
DB_PORT="${3:-${DQ_DB_PORT:-5432}}"
DB_NAME="${4:-${DB_NAME:-dq}}"
DB_USER="${5:-${DB_USER:-postgres}}"
DB_PASSWORD="${6:-${POSTGRES_PASSWORD:-}}"

if [ ! -f "$CSV_FILE" ]; then
  error "$my_name" "Dataset CSV file not found: $CSV_FILE"
  exit 1
fi

info "$my_name" "Validating dataset counts per workspace"
info "$my_name" "  CSV: $CSV_FILE"
info "$my_name" "  Database: $DB_USER@$DB_HOST:$DB_PORT/$DB_NAME"

# Read expected counts from CSV
declare -A expected_counts
while IFS=',' read -r id product_id name description owner created_at workspace_id business_key; do
  # Skip header row
  if [[ "$id" == '"id"' ]]; then
    continue
  fi
  
  # Remove quotes from workspace_id
  ws="${workspace_id%\"}"
  ws="${ws#\"}"
  
  # Skip empty workspace_ids
  if [ -z "$ws" ]; then
    continue
  fi
  
  expected_counts["$ws"]=$((${expected_counts["$ws"]:-0} + 1))
done < "$CSV_FILE"

info "$my_name" "Expected dataset counts from CSV:"
for ws in $(printf '%s\n' "${!expected_counts[@]}" | sort); do
  info "$my_name" "  $ws: ${expected_counts[$ws]}"
done

# Query database for actual counts
declare -A actual_counts
if [ -n "$DB_PASSWORD" ]; then
  export PGPASSWORD="$DB_PASSWORD"
fi

query_result=$(psql \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  -t \
  -c "SELECT workspace_id, COUNT(*) as count FROM data_sets WHERE workspace_id IS NOT NULL AND workspace_id != '' GROUP BY workspace_id ORDER BY workspace_id;" 2>&1 || true)

if echo "$query_result" | grep -q "FATAL"; then
  error "$my_name" "Failed to connect to database: $query_result"
  exit 1
fi

# Parse query results into actual_counts
while IFS='|' read -r ws count; do
  ws="${ws// /}"  # Remove whitespace
  count="${count// /}"  # Remove whitespace
  if [ -n "$ws" ] && [ -n "$count" ]; then
    actual_counts["$ws"]="$count"
  fi
done <<< "$query_result"

info "$my_name" "Actual dataset counts from database:"
for ws in $(printf '%s\n' "${!actual_counts[@]}" | sort); do
  info "$my_name" "  $ws: ${actual_counts[$ws]}"
done

# Compare counts
mismatches=0
all_workspaces=$(printf '%s\n' "${!expected_counts[@]}" "${!actual_counts[@]}" | sort -u)

while IFS= read -r ws; do
  exp="${expected_counts[$ws]:-0}"
  act="${actual_counts[$ws]:-0}"
  
  if [ "$exp" -ne "$act" ]; then
    printf "${RED}✗ MISMATCH${NC} workspace_id='%s': expected %d, got %d\n" "$ws" "$exp" "$act" >&2
    mismatches=$((mismatches + 1))
  else
    printf "${GREEN}✓${NC} workspace_id='%s': %d datasets\n" "$ws" "$exp"
  fi
done <<< "$all_workspaces"

if [ "$mismatches" -gt 0 ]; then
  error "$my_name" "Found $mismatches workspace(s) with dataset count mismatches"
  exit 1
else
  success "$my_name" "All workspace dataset counts match"
  exit 0
fi
