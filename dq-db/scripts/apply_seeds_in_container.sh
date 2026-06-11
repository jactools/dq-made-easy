#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${DB_NAME:-dq}"
DB_USER="${DB_USER:-postgres}"
SEED_ROOT="${SEED_ROOT:-/opt/dq-db/init}"

echo "== Apply seed data in running container =="
echo "Database: ${DB_NAME}"

if [ ! -d "$SEED_ROOT" ]; then
  echo "ERROR: seed root not found: $SEED_ROOT"
  exit 1
fi

# Apply generated seed files from init/ (excluding temp + backup locations).
shopt -s nullglob
for file in "$SEED_ROOT"/generated_seed_*.sql; do
  base="$(basename "$file")"
  if [[ "$base" == *_temp.sql ]]; then
    echo "Skipping temp seed file: $base"
    continue
  fi
  echo "Applying generated seed: $base"
  psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" -f "$file"
done
shopt -u nullglob

rule_version_metadata_csv="$SEED_ROOT/rule_version_metadata.csv"
if [ ! -f "$rule_version_metadata_csv" ]; then
  echo "ERROR: Missing mandatory rule version metadata CSV: $rule_version_metadata_csv"
  exit 1
fi

rule_version_metadata_sql="$(mktemp /tmp/seed_rule_version_metadata.XXXXXX.sql)"
cat > "$rule_version_metadata_sql" <<SQL
CREATE TEMP TABLE tmp_rule_version_metadata_seed (
  rule_id TEXT,
  current_version_id TEXT,
  version_created_at TIMESTAMP,
  version_updated_at TIMESTAMP
);

\copy tmp_rule_version_metadata_seed FROM '$rule_version_metadata_csv' CSV HEADER;

INSERT INTO rule_current_versions (rule_id, version_id)
SELECT rule_id, current_version_id
FROM tmp_rule_version_metadata_seed
ON CONFLICT (rule_id) DO UPDATE SET
  version_id = EXCLUDED.version_id;

UPDATE rules r
SET total_versions = 1,
    versioning_enabled = true,
    version_created_at = t.version_created_at,
    version_updated_at = t.version_updated_at
FROM tmp_rule_version_metadata_seed t
WHERE r.id = t.rule_id;

UPDATE rules r
SET total_versions = 0,
    versioning_enabled = false,
    version_created_at = NULL,
    version_updated_at = NULL
WHERE NOT EXISTS (
  SELECT 1
  FROM tmp_rule_version_metadata_seed t
  WHERE t.rule_id = r.id
);
SQL

echo "Applying post-seed file: $(basename "$rule_version_metadata_sql")"
psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" -f "$rule_version_metadata_sql"
rm -f "$rule_version_metadata_sql"

echo "Seed data applied"

# Validate dataset counts per workspace match between database and mock-data CSV
echo ""
echo "== Validating dataset counts per workspace =="

# Get the mock-data directory - it's in SEED_ROOT parent or adjacent
MOCK_DATA_DIR="${SEED_ROOT%/*}/mock-data"
if [ ! -d "$MOCK_DATA_DIR" ]; then
  # Try alternate location
  MOCK_DATA_DIR="/opt/dq-db/mock-data"
fi

if [ ! -f "$MOCK_DATA_DIR/data-sets.csv" ]; then
  echo "WARNING: Could not find data-sets.csv in $MOCK_DATA_DIR; skipping dataset count validation"
  exit 0
fi

# Count expected datasets per workspace from CSV
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
done < "$MOCK_DATA_DIR/data-sets.csv"

echo "Expected dataset counts from CSV:"
for ws in $(printf '%s\n' "${!expected_counts[@]}" | sort); do
  echo "  $ws: ${expected_counts[$ws]}"
done

# Query database for actual counts
declare -A actual_counts
query_result=$(psql -v ON_ERROR_STOP=0 -t -U "$DB_USER" -d "$DB_NAME" \
  -c "SELECT COALESCE(workspace_id, 'default'), COUNT(*) FROM data_sets WHERE workspace_id IS NOT NULL AND workspace_id != '' GROUP BY workspace_id ORDER BY workspace_id;" 2>&1 || true)

while IFS='|' read -r ws count; do
  ws="${ws// /}"  # Remove whitespace
  count="${count// /}"  # Remove whitespace
  if [ -n "$ws" ] && [ -n "$count" ]; then
    actual_counts["$ws"]="$count"
  fi
done <<< "$query_result"

echo "Actual dataset counts from database:"
for ws in $(printf '%s\n' "${!actual_counts[@]}" | sort); do
  echo "  $ws: ${actual_counts[$ws]}"
done

# Compare and report
mismatches=0
all_workspaces=$(printf '%s\n' "${!expected_counts[@]}" "${!actual_counts[@]}" | sort -u)

while IFS= read -r ws; do
  exp="${expected_counts[$ws]:-0}"
  act="${actual_counts[$ws]:-0}"
  
  if [ "$exp" -ne "$act" ]; then
    echo "✗ MISMATCH workspace_id='$ws': expected $exp, got $act"
    mismatches=$((mismatches + 1))
  else
    echo "✓ workspace_id='$ws': $exp datasets"
  fi
done <<< "$all_workspaces"

if [ "$mismatches" -gt 0 ]; then
  echo "ERROR: Found $mismatches workspace(s) with dataset count mismatches"
  exit 1
fi

echo "✓ All workspace dataset counts match"
