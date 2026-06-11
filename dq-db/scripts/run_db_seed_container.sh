#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/workspace"
FASTAPI_DIR="$ROOT_DIR/dq-api/fastapi"
MOCK_SOURCE_DIR="$ROOT_DIR/dq-db/mock-data"
WORK_DIR="${DB_SEED_WORK_DIR:-/tmp/db-seed-work}"
MOCK_DIR="$WORK_DIR/mock-data"
INIT_DIR="$WORK_DIR/init"
PATCH_DIR="$WORK_DIR/patches"
PATCH_FILE="$PATCH_DIR/ensure_external_ids.sql"
UNMATCHED_FILE="$PATCH_DIR/unmatched_emails.txt"
RULE_VERSION_METADATA_SOURCE="$MOCK_SOURCE_DIR/versioning/rule_version_metadata.csv"
RULE_VERSION_METADATA_TARGET="$INIT_DIR/rule_version_metadata.csv"
RULE_VERSION_DIFFS_SOURCE="$MOCK_SOURCE_DIR/versioning/rule_version_diffs.csv"
RULE_ROLLBACKS_SOURCE="$MOCK_SOURCE_DIR/versioning/rule_rollbacks.csv"
RULE_VERSION_REL_SOURCE="$MOCK_SOURCE_DIR/versioning/rule_version_relationships.csv"
VERSION_SQL="$WORK_DIR/version_catalog.sql"

DQ_DB_INTERNAL_URL="${DQ_DB_INTERNAL_URL:?DQ_DB_INTERNAL_URL is required}"
PGHOST="${PGHOST:-db}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-postgres}"
PGDATABASE="${PGDATABASE:-dq}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:?KEYCLOAK_REALM is required}"
KEYCLOAK_HTTP_RELATIVE_PATH="${KEYCLOAK_HTTP_RELATIVE_PATH:-/}"
KEYCLOAK_INTERNAL_URL="${KEYCLOAK_INTERNAL_URL:-http://keycloak:8080${KEYCLOAK_HTTP_RELATIVE_PATH}}"
KEYCLOAK_PUBLIC_URL="${KEYCLOAK_PUBLIC_URL:-${KEYCLOAK_INTERNAL_URL}}"
KEYCLOAK_READY_URL="${KEYCLOAK_READY_URL:-${KEYCLOAK_INTERNAL_URL%/}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration}"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/keycloak_readiness.sh"

my_name="run_db_seed_container.sh"

export DQ_DB_INTERNAL_URL PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE

wait_for_db() {
  local attempt
  for attempt in $(seq 1 90); do
    if pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  error "$my_name" "database did not become ready at ${PGHOST}:${PGPORT}/${PGDATABASE}"
  exit 1
}

sync_version_manifest() {
  python - "$ROOT_DIR/VERSION_MANIFEST.json" > "$VERSION_SQL" <<'PY'
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
data = json.loads(manifest_path.read_text())
apps = data.get("apps") or {}
api_version = str(apps.get("api") or "").strip()
if not api_version:
    raise SystemExit("manifest apps.api is missing")
ui_version = str(apps.get("ui") or api_version)
components_json = json.dumps(data.get("components") or {}, separators=(",", ":"))

def esc(value: str) -> str:
    return value.replace("'", "''")

print(
    "INSERT INTO app_config (config_key, config_value, value_type) VALUES "
    f"('version_catalog_api', '{esc(api_version)}', 'string'),"
    f"('version_catalog_ui', '{esc(ui_version)}', 'string'),"
    f"('version_catalog_components', '{esc(components_json)}', 'json') "
    "ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value, value_type = EXCLUDED.value_type;"
)
PY

  psql -v ON_ERROR_STOP=1 -f "$VERSION_SQL"
}

validate_all_tables_have_rows() {
  local table_name row_count exists failed=0
  local required_tables=(
    rules
    approvals
    users
    roles
    rule_attributes
    data_objects
    workspaces
    audit
    data_products
    data_sets
    data_objects_catalog
    data_object_versions
    attributes_catalog
    data_deliveries
    app_config
    data_source_metadata
    data_source_profiling_requests
    suggestions
    suggestion_interactions
    system_info
    rule_versions
    rule_version_diffs
    rule_rollbacks
    rule_version_relationships
  )

  for table_name in "${required_tables[@]}"; do
    exists="$(psql -At -c "SELECT to_regclass('$table_name') IS NOT NULL;")"
    exists="$(printf '%s' "$exists" | tr -d '[:space:]')"
    if [ "$exists" != "t" ]; then
      error "$my_name" "required table '$table_name' does not exist after seed"
      failed=1
      continue
    fi

    row_count="$(psql -At -c "SELECT COUNT(*) FROM \"$table_name\";")"
    row_count="$(printf '%s' "$row_count" | tr -d '[:space:]')"
    if [ -z "$row_count" ] || [ "$row_count" -lt 1 ]; then
      error "$my_name" "required table '$table_name' has 0 rows after seed"
      failed=1
    fi
  done

  if [ "$failed" -ne 0 ]; then
    exit 1
  fi
}

apply_versioning_operational_seeds() {
  local versioning_sql

  for required_file in "$RULE_VERSION_DIFFS_SOURCE" "$RULE_ROLLBACKS_SOURCE" "$RULE_VERSION_REL_SOURCE"; do
    if [ ! -f "$required_file" ]; then
      error "$my_name" "missing mandatory versioning seed CSV: $required_file"
      exit 1
    fi
  done

  cp "$RULE_VERSION_DIFFS_SOURCE" "$WORK_DIR/rule_version_diffs_seed.csv"
  cp "$RULE_ROLLBACKS_SOURCE" "$WORK_DIR/rule_rollbacks_seed.csv"
  cp "$RULE_VERSION_REL_SOURCE" "$WORK_DIR/rule_version_relationships_seed.csv"

  versioning_sql="$WORK_DIR/seed_rule_version_operational.sql"
  cat > "$versioning_sql" <<SQL
CREATE TEMP TABLE tmp_rule_version_diffs_seed (
  id TEXT,
  rule_id TEXT,
  from_version_number INT,
  to_version_number INT,
  field_name TEXT,
  old_value TEXT,
  new_value TEXT,
  created_at TIMESTAMP
);

\copy tmp_rule_version_diffs_seed FROM '$WORK_DIR/rule_version_diffs_seed.csv' CSV HEADER;

INSERT INTO rule_version_diffs (
  id, from_version_id, to_version_id, field_name, old_value, new_value, created_at
)
SELECT
  t.id,
  rv_from.id,
  rv_to.id,
  t.field_name,
  t.old_value,
  t.new_value,
  COALESCE(t.created_at, CURRENT_TIMESTAMP)
FROM tmp_rule_version_diffs_seed t
JOIN rule_versions rv_from
  ON rv_from.rule_id = t.rule_id
 AND rv_from.version_number = t.from_version_number
JOIN rule_versions rv_to
  ON rv_to.rule_id = t.rule_id
 AND rv_to.version_number = t.to_version_number
ON CONFLICT (id) DO UPDATE SET
  from_version_id = EXCLUDED.from_version_id,
  to_version_id = EXCLUDED.to_version_id,
  field_name = EXCLUDED.field_name,
  old_value = EXCLUDED.old_value,
  new_value = EXCLUDED.new_value,
  created_at = EXCLUDED.created_at;

CREATE TEMP TABLE tmp_rule_rollbacks_seed (
  id TEXT,
  rule_id TEXT,
  from_version_number INT,
  to_version_number INT,
  rolled_back_by TEXT,
  rolled_back_at TIMESTAMP,
  reason TEXT,
  new_version_number INT
);

\copy tmp_rule_rollbacks_seed FROM '$WORK_DIR/rule_rollbacks_seed.csv' CSV HEADER;

INSERT INTO rule_rollbacks (
  id,
  rule_id,
  from_version_id,
  to_version_id,
  rolled_back_by,
  rolled_back_at,
  reason,
  new_version_created_id
)
SELECT
  t.id,
  t.rule_id,
  rv_from.id,
  rv_to.id,
  t.rolled_back_by,
  COALESCE(t.rolled_back_at, CURRENT_TIMESTAMP),
  t.reason,
  rv_new.id
FROM tmp_rule_rollbacks_seed t
JOIN rule_versions rv_from
  ON rv_from.rule_id = t.rule_id
 AND rv_from.version_number = t.from_version_number
JOIN rule_versions rv_to
  ON rv_to.rule_id = t.rule_id
 AND rv_to.version_number = t.to_version_number
LEFT JOIN rule_versions rv_new
  ON rv_new.rule_id = t.rule_id
 AND rv_new.version_number = t.new_version_number
ON CONFLICT (id) DO UPDATE SET
  from_version_id = EXCLUDED.from_version_id,
  to_version_id = EXCLUDED.to_version_id,
  rolled_back_by = EXCLUDED.rolled_back_by,
  rolled_back_at = EXCLUDED.rolled_back_at,
  reason = EXCLUDED.reason,
  new_version_created_id = EXCLUDED.new_version_created_id;

CREATE TEMP TABLE tmp_rule_version_relationships_seed (
  id TEXT,
  rule_id TEXT,
  version_number INT,
  approval_id TEXT,
  test_proof_id TEXT,
  deployment_id TEXT,
  created_at TIMESTAMP
);

\copy tmp_rule_version_relationships_seed FROM '$WORK_DIR/rule_version_relationships_seed.csv' CSV HEADER;

INSERT INTO rule_version_relationships (
  id,
  version_id,
  approval_id,
  test_proof_id,
  deployment_id,
  created_at
)
SELECT
  t.id,
  rv.id,
  t.approval_id,
  t.test_proof_id,
  t.deployment_id,
  COALESCE(t.created_at, CURRENT_TIMESTAMP)
FROM tmp_rule_version_relationships_seed t
JOIN rule_versions rv
  ON rv.rule_id = t.rule_id
 AND rv.version_number = t.version_number
ON CONFLICT (id) DO UPDATE SET
  version_id = EXCLUDED.version_id,
  approval_id = EXCLUDED.approval_id,
  test_proof_id = EXCLUDED.test_proof_id,
  deployment_id = EXCLUDED.deployment_id,
  created_at = EXCLUDED.created_at;
SQL

  psql -v ON_ERROR_STOP=1 -f "$versioning_sql"
}

info "$my_name" "Containerized DB seed starting"
info "$my_name" "Waiting for database..."
wait_for_db
info "$my_name" "Waiting for Keycloak..."
if ! wait_for_keycloak_ready "$KEYCLOAK_READY_URL" "Keycloak"; then
  error "$my_name" "Keycloak did not become ready at ${KEYCLOAK_READY_URL}"
  exit 1
fi

rm -rf "$WORK_DIR"
mkdir -p "$MOCK_DIR" "$INIT_DIR" "$PATCH_DIR"
cp -R "$MOCK_SOURCE_DIR/." "$MOCK_DIR/"

info "$my_name" "Sanitizing mock-data CSV files..."
python "$ROOT_DIR/dq-api/scripts/quote_mock_data.py" "$MOCK_DIR"

info "$my_name" "Generating SQL seed files from sanitized CSVs..."
python "$ROOT_DIR/dq-api/scripts/generate_sql_seeds.py" --input-dir "$MOCK_DIR" --output-dir "$INIT_DIR"

if [ ! -f "$RULE_VERSION_METADATA_SOURCE" ]; then
  error "$my_name" "missing rule version metadata CSV at $RULE_VERSION_METADATA_SOURCE"
  exit 1
fi
cp "$RULE_VERSION_METADATA_SOURCE" "$RULE_VERSION_METADATA_TARGET"

info "$my_name" "Generating external_id patch from Keycloak..."
python "$ROOT_DIR/scripts/generate_external_id_patch.py" --output-file "$PATCH_FILE" --unmatched-file "$UNMATCHED_FILE"

info "$my_name" "Resetting schema..."
SEED_ROOT="$INIT_DIR" DB_NAME="$PGDATABASE" DB_USER="$PGUSER" bash "$ROOT_DIR/dq-db/scripts/reseed_in_container.sh"

info "$my_name" "Applying Alembic migrations..."
(
  cd "$FASTAPI_DIR"
  python -m alembic -c "$FASTAPI_DIR/alembic.ini" upgrade head
)

info "$my_name" "Applying generated seed SQL files..."
SEED_ROOT="$INIT_DIR" DB_NAME="$PGDATABASE" DB_USER="$PGUSER" bash "$ROOT_DIR/dq-db/scripts/apply_seeds_in_container.sh"

info "$my_name" "Applying versioning operational seed SQL..."
apply_versioning_operational_seeds

if [ -s "$PATCH_FILE" ]; then
  info "$my_name" "Applying external_id patch..."
  psql -v ON_ERROR_STOP=1 -f "$PATCH_FILE"
else
  error "$my_name" "external_id patch file missing or empty: $PATCH_FILE"
  exit 1
fi

info "$my_name" "Syncing version manifest into app_config..."
sync_version_manifest

info "$my_name" "Validating seeded table row counts..."
validate_all_tables_have_rows

success "$my_name" "containerized DB seed completed successfully"