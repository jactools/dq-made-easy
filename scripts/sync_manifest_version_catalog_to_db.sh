#!/usr/bin/env bash
set -euo pipefail


# Purpose: Sync VERSION_MANIFEST.json versions into the database app_config table.
#
# What it does:
# - Parses apps/api/ui/component versions from a manifest JSON file.
# - Builds an upsert SQL statement.
# - Applies it inside the running db container with retries.
#
# Version: 1.0
# Last modified: 2026-04-07

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST_PATH="${1:-$ROOT_DIR/VERSION_MANIFEST.json}"

source "$ROOT_DIR/scripts/supporting/logging.sh"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/compose/invocation.sh"
init_root_env_file "$ROOT_DIR"

my_name="sync_manifest_version_catalog_to_db.sh"

if [ ! -f "$ROOT_ENV_FILE" ]; then
  error "$my_name" "Env file not found: $ROOT_ENV_FILE"
  exit 1
fi

validate_selected_root_env_file "$ROOT_DIR" full

if [ ! -f "$MANIFEST_PATH" ]; then
  error "$my_name" "VERSION_MANIFEST file not found: $MANIFEST_PATH"
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  error "$my_name" "jq is required to parse $MANIFEST_PATH"
  exit 1
fi

api_version="$(jq -r '.apps.api // empty' "$MANIFEST_PATH")"
ui_version="$(jq -r '.apps.ui // empty' "$MANIFEST_PATH")"
components_json="$(jq -c '.components // {}' "$MANIFEST_PATH")"

if [ -z "$api_version" ]; then
  error "$my_name" "manifest apps.api is missing in $MANIFEST_PATH"
  exit 1
fi

if [ -z "$ui_version" ]; then
  ui_version="$api_version"
fi

sql_escape() {
  printf "%s" "$1" | sed "s/'/''/g"
}

api_sql="$(sql_escape "$api_version")"
ui_sql="$(sql_escape "$ui_version")"
components_sql="$(sql_escape "$components_json")"

read -r -d '' UPSERT_SQL <<SQL || true
INSERT INTO app_config (config_key, config_value, value_type)
VALUES
  ('version_catalog_api', '$api_sql', 'string'),
  ('version_catalog_ui', '$ui_sql', 'string'),
  ('version_catalog_components', '$components_sql', 'json')
ON CONFLICT (config_key)
DO UPDATE SET
  config_value = EXCLUDED.config_value,
  value_type = EXCLUDED.value_type;
SQL

run_sql_in_db_container() {
  docker_compose exec -T db psql -U postgres -d dq -v ON_ERROR_STOP=1 -c "$UPSERT_SQL" >/dev/null
}

info "$my_name" "Syncing version catalog from $MANIFEST_PATH into app_config..."

attempts=30
for attempt in $(seq 1 "$attempts"); do
  if run_sql_in_db_container; then
    success "$my_name" "app_config version catalog synced (api=$api_version, ui=$ui_version)"
    exit 0
  fi
  sleep 2
done

error "$my_name" "unable to sync version catalog to DB after $attempts attempts"
exit 1
