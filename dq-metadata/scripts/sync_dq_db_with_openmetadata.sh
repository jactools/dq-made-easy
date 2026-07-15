#!/usr/bin/env bash
set -euo pipefail

# Repeatable sync: ingest seeded dq-db metadata into OpenMetadata, then optionally
# run LDD column-tag mapping against discovered table/column entities.

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

OM_BASE_URL="${OM_BASE_URL:-https://openmetadata.jac.dot:8585}"
OM_API_BASE="${OM_API_BASE:-$OM_BASE_URL/api}"
OM_EMAIL="${OM_EMAIL:-${OPENMETADATA_OIDC_SEED_USERNAME:-}}"

if [[ -n "${OM_PASSWORD_B64:-}" ]]; then
  OM_PASSWORD_B64="$OM_PASSWORD_B64"
else
  raw_om_password="${OM_PASSWORD:-${OPENMETADATA_OIDC_SEED_PASSWORD:-${KEYCLOAK_SEEDED_USER_PASSWORD:-${KEYCLOAK_USER_PASSWORD:-}}}}"
  if [[ -n "$raw_om_password" ]]; then
    OM_PASSWORD_B64="$(printf '%s' "$raw_om_password" | base64 | tr -d '\n')"
  else
    OM_PASSWORD_B64=""
  fi
fi

DB_SERVICE_NAME="${DB_SERVICE_NAME:-dq-db}"
DB_COMPOSE_SERVICE="${DB_COMPOSE_SERVICE:-db}"
DB_HOST_PORT="${DB_HOST_PORT:-db:5432}"
DB_NAME="${DB_NAME:-${DQ_DB_NAME}}"
DB_USERNAME="${DB_USERNAME:-${DQ_DB_USER}}"
DB_PASSWORD="${DB_PASSWORD:-${DQ_DB_PASSWORD}}"
DB_SSL_MODE="${DB_SSL_MODE:-disable}"
HEARTBEAT_INTERVAL_SECONDS="${HEARTBEAT_INTERVAL_SECONDS:-5}"

# If true, run mapping stage after ingestion using existing LDD runner outputs.
RUN_LDD_MAPPING="${RUN_LDD_MAPPING:-true}"
LDD_OUTPUT_DIR="${LDD_OUTPUT_DIR:-$ROOT_DIR/dq-db/mock-data/openmetadata-ready}"
MAPPING_MIN_COVERAGE="${MAPPING_MIN_COVERAGE:-0.05}"
MAPPING_FAIL_ON_LOW_COVERAGE="${MAPPING_FAIL_ON_LOW_COVERAGE:-false}"

# If true, try to provision glossaryTerm custom property `assetId` before LDD import.
ENSURE_GLOSSARY_ASSET_ID="${ENSURE_GLOSSARY_ASSET_ID:-true}"

INGESTION_CONTAINER="${INGESTION_CONTAINER:-$(docker ps --format '{{.Names}}' | grep -E 'openmetadata-ingestion' | head -n 1 || true)}"
if [[ -z "$INGESTION_CONTAINER" ]]; then
  echo "No running OpenMetadata ingestion container found."
  echo "Start it first (example): docker compose --profile metadata-ingestion up -d"
  exit 1
fi

echo "Using ingestion container: $INGESTION_CONTAINER"

heartbeat_pid=""
heartbeat_printed="false"

start_heartbeat() {
  local interval="${1:-$HEARTBEAT_INTERVAL_SECONDS}"

  stop_heartbeat

  (
    while true; do
      sleep "$interval"
      printf '.' >&2
    done
  ) &
  heartbeat_pid=$!
}

stop_heartbeat() {
  if [[ -n "$heartbeat_pid" ]]; then
    kill "$heartbeat_pid" >/dev/null 2>&1 || true
    wait "$heartbeat_pid" 2>/dev/null || true
    heartbeat_pid=""
    heartbeat_printed="true"
  fi

  if [[ "$heartbeat_printed" == "true" ]]; then
    printf '\n' >&2
    heartbeat_printed="false"
  fi
}

trap stop_heartbeat EXIT

resolve_running_container_by_service() {
  local compose_service="$1"

  docker ps \
    --filter "label=com.docker.compose.service=${compose_service}" \
    --filter 'status=running' \
    --format '{{.Names}}' | head -n 1
}

ensure_pg_stat_statements_for_ingestion() {
  local superuser="${DB_SUPERUSER:-postgres}"
  local db_container

  db_container="$(resolve_running_container_by_service "$DB_COMPOSE_SERVICE")"
  if [[ -z "$db_container" ]]; then
    echo "dq-db service is not running; cannot ensure pg_stat_statements"
    return 1
  fi

  echo "Ensuring pg_stat_statements is enabled in database '$DB_NAME' for OpenMetadata ingestion..."

  if ! docker exec "$db_container" psql -U "$superuser" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
    -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;" >/dev/null; then
    echo "Failed to create/verify pg_stat_statements extension in '$DB_NAME'"
    return 1
  fi

  # Non-superuser ingest users need visibility into statistics objects.
  if [[ -n "$DB_USERNAME" ]] && [[ "$DB_USERNAME" != "$superuser" ]]; then
    docker exec "$db_container" psql -U "$superuser" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
      -c "GRANT pg_read_all_stats TO \"$DB_USERNAME\";" >/dev/null || {
        echo "Failed to grant pg_read_all_stats to '$DB_USERNAME'"
        return 1
      }
  fi

  return 0
}

wait_for_running_container() {
  local name="$1"
  local timeout_secs="${2:-180}"
  local waited=0

  while (( waited < timeout_secs )); do
    local state
    state="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || true)"
    if [[ "$state" == "running" ]]; then
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done

  return 1
}

if ! wait_for_running_container "$INGESTION_CONTAINER" 180; then
  echo "Ingestion container '$INGESTION_CONTAINER' did not reach running state within timeout."
  echo "Recent logs:"
  docker logs --tail=80 "$INGESTION_CONTAINER" || true
  exit 1
fi

ensure_pg_stat_statements_for_ingestion

auth_payload="{\"email\":\"$OM_EMAIL\",\"password\":\"$OM_PASSWORD_B64\"}"
TOKEN="${OM_TOKEN:-}"

if [[ -z "$TOKEN" ]]; then
  if [[ -z "$OM_EMAIL" || -z "$OM_PASSWORD_B64" ]]; then
    echo "OpenMetadata login credentials are not configured; provide OM_TOKEN or repo-owned OM_EMAIL/OM_PASSWORD_B64 credentials."
    exit 1
  fi
  TOKEN="$(curl -fsS -X POST "$OM_API_BASE/v1/users/login" -H 'Content-Type: application/json' -d "$auth_payload" \
    | sed -n 's/.*"accessToken":"\([^"]*\)".*/\1/p' || true)"
fi

if [[ -z "$TOKEN" ]]; then
  TOKEN="$(curl -fsS -X POST "$OM_API_BASE/v1/auth/login" -H 'Content-Type: application/json' -d "$auth_payload" \
    | sed -n 's/.*"accessToken":"\([^"]*\)".*/\1/p' || true)"
fi

if [[ -z "$TOKEN" ]]; then
  echo "Failed to obtain OpenMetadata access token from $OM_API_BASE"
  exit 1
fi

if [[ -n "${OM_TOKEN:-}" ]]; then
  echo "Using provided OpenMetadata bearer token"
else
  echo "OpenMetadata login succeeded for $OM_EMAIL"
fi

ensure_glossary_asset_id_property() {
  local type_url="$OM_API_BASE/v1/metadata/types/name/glossaryTerm"
  local headers=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
  local type_json
  local glossary_type_id
  local string_type_json
  local string_type_id
  local payload
  local code

  if ! type_json="$(curl -fsS "$type_url" -H "Authorization: Bearer $TOKEN")"; then
    echo "Warning: unable to read glossaryTerm metadata type; skipping custom property ensure"
    return 0
  fi

  glossary_type_id="$(echo "$type_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
  if [[ -z "$glossary_type_id" ]]; then
    echo "Warning: unable to resolve glossaryTerm type id; skipping custom property ensure"
    return 0
  fi

  if echo "$type_json" | grep -q '"name"[[:space:]]*:[[:space:]]*"assetId"'; then
    echo "Custom property glossaryTerm.assetId already exists"
    return 0
  fi

  string_type_json="$(curl -fsS "$OM_API_BASE/v1/metadata/types/name/string" -H "Authorization: Bearer $TOKEN" || true)"
  string_type_id="$(echo "$string_type_json" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
  if [[ -z "$string_type_id" ]]; then
    echo "Warning: unable to resolve metadata type id for 'string'; skipping custom property ensure"
    return 0
  fi

  echo "Custom property glossaryTerm.assetId not found; creating it via metadata type update"
  payload="{\"name\":\"assetId\",\"description\":\"Source asset identifier from LDD pipeline\",\"propertyType\":{\"id\":\"$string_type_id\",\"type\":\"type\"}}"
  code="$(curl -sS -o /tmp/om_assetid_create.json -w '%{http_code}' -X PUT "$OM_API_BASE/v1/metadata/types/$glossary_type_id" "${headers[@]}" -d "$payload" || true)"
  if [[ "$code" == "200" || "$code" == "201" ]]; then
    echo "Created glossaryTerm.assetId custom property"
    return 0
  fi

  echo "Warning: failed to provision glossaryTerm.assetId custom property automatically"
  echo "  Tried endpoint: $OM_API_BASE/v1/metadata/types/$glossary_type_id"
  echo "  Last response code: $code"
  echo "  LDD import will continue using runner fallback (extension stripped if unsupported)."
  return 0
}

print_catalog_summary() {
  local services_json="$1"
  local databases_json="$2"
  local python_runner="$ROOT_DIR/scripts/python_arm64.sh"

  "$python_runner" --python-bin python3 - "$services_json" "$databases_json" <<'PY'
import json
import sys

services = json.loads(sys.argv[1])
databases = json.loads(sys.argv[2])

service_names = [item.get("name") for item in services.get("data") or [] if item.get("name")]
database_names = [item.get("name") for item in databases.get("data") or [] if item.get("name")]

def preview(names, limit=5):
    if not names:
        return "none"
    head = names[:limit]
    suffix = "" if len(names) <= limit else f", ... (+{len(names) - limit} more)"
    return ", ".join(head) + suffix

print("Catalog summary:")
print(f"- Database services: {len(service_names)} [{preview(service_names)}]")
print(f"- Databases: {len(database_names)} [{preview(database_names)}]")
PY
}

if [[ "$ENSURE_GLOSSARY_ASSET_ID" == "true" ]]; then
  ensure_glossary_asset_id_property
fi

TMP_CONFIG_HOST="$ROOT_DIR/tmp/dq-db-openmetadata-ingest.yaml"
mkdir -p "$ROOT_DIR/tmp"

# Write YAML config without heredoc to avoid interactive/quoting issues.
printf '%s\n' \
  "source:" \
  "  type: postgres" \
  "  serviceName: $DB_SERVICE_NAME" \
  "  serviceConnection:" \
  "    config:" \
  "      type: Postgres" \
  "      hostPort: $DB_HOST_PORT" \
  "      username: $DB_USERNAME" \
  "      authType:" \
  "        password: $DB_PASSWORD" \
  "      database: $DB_NAME" \
  "      sslMode: $DB_SSL_MODE" \
  "  sourceConfig:" \
  "    config:" \
  "      type: DatabaseMetadata" \
  "      includeViews: true" \
  "      schemaFilterPattern:" \
  "        excludes:" \
  "          - information_schema" \
  "          - pg_catalog" \
  "sink:" \
  "  type: metadata-rest" \
  "  config: {}" \
  "workflowConfig:" \
  "  loggerLevel: INFO" \
  "  openMetadataServerConfig:" \
  "    hostPort: https://openmetadata-server:8585/api" \
  "    authProvider: openmetadata" \
  "    verifySSL: validate" \
  "    sslConfig:" \
  "      caCertificate: /etc/openmetadata/certs/mkcert-rootCA.pem" \
  "    securityConfig:" \
  "      jwtToken: $TOKEN" \
  >"$TMP_CONFIG_HOST"

docker cp "$TMP_CONFIG_HOST" "$INGESTION_CONTAINER:/tmp/dq-db-openmetadata-ingest.yaml"

echo "Running OpenMetadata ingestion for service '$DB_SERVICE_NAME'..."
start_heartbeat
set +e
docker exec "$INGESTION_CONTAINER" bash -lc "metadata ingest -c /tmp/dq-db-openmetadata-ingest.yaml"
ingest_exit_code=$?
set -e
stop_heartbeat

if [[ "$ingest_exit_code" -ne 0 ]]; then
  echo "OpenMetadata ingestion failed with exit code $ingest_exit_code"
  exit "$ingest_exit_code"
fi

echo "Ingestion completed. Verifying discovered databases..."
services_json="$(curl -fsS "$OM_API_BASE/v1/services/databaseServices?limit=100" -H "Authorization: Bearer $TOKEN")"
databases_json="$(curl -fsS "$OM_API_BASE/v1/databases?limit=100" -H "Authorization: Bearer $TOKEN")"
print_catalog_summary "$services_json" "$databases_json"

if [[ "$RUN_LDD_MAPPING" == "true" ]]; then
  echo
  echo "Running full LDD pipeline against discovered catalog entities..."
  python_runner="$ROOT_DIR/scripts/python_arm64.sh"
  # Ensure dq-metadata script dependencies are installed in the venv
  "$python_runner" --python-bin "$ROOT_DIR/venv/bin/python" -m pip install --quiet -r "$ROOT_DIR/dq-metadata/scripts/requirements.txt"
  if [[ "$MAPPING_FAIL_ON_LOW_COVERAGE" == "true" ]]; then
    coverage_gate_flag="--fail-on-low-coverage"
    echo "Mapping preflight gate: strict (min coverage ${MAPPING_MIN_COVERAGE})"
  else
    coverage_gate_flag="--no-fail-on-low-coverage"
    echo "Mapping preflight gate: warning-only (min coverage ${MAPPING_MIN_COVERAGE})"
  fi

  LDD_LOG_FILE="/tmp/ldd_pipeline_$(date +%s).log"
  echo "LDD pipeline output will stream to console and $LDD_LOG_FILE"

  start_heartbeat
  set +e
  "$python_runner" --python-bin "$ROOT_DIR/venv/bin/python" "$ROOT_DIR/dq-metadata/scripts/run_ldd_openmetadata_pipeline.py" \
    --stages transform,import-glossary,apply-mappings,report \
    --endpoint "$OM_API_BASE" \
    --token "$TOKEN" \
    --service-name "$DB_SERVICE_NAME" \
    --database-name "$DB_NAME" \
    --min-mapping-coverage "$MAPPING_MIN_COVERAGE" \
    --output-dir "$LDD_OUTPUT_DIR" \
    "$coverage_gate_flag" 2>&1 | tee "$LDD_LOG_FILE"
  ldd_exit_code=$?
  set -e
  stop_heartbeat

  grep -E "(stage|completed|LDD|error|warning|Report JSON|Report Markdown|Rows:|Glossary import:|Mapping preflight:|Column mapping:)" "$LDD_LOG_FILE" || true

  if [[ "$ldd_exit_code" -ne 0 ]]; then
    echo "LDD pipeline failed. Full log: $LDD_LOG_FILE"
    exit "$ldd_exit_code"
  fi

  echo "LDD pipeline stage finished."
fi

echo "Repeatable sync complete."
