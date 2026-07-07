#!/usr/bin/env bash
set -euo pipefail

# Purpose: Run representative smoke checks for the migrated internal TLS paths.
# What it does:
# - Runs the HTTP auth smoke check through Kong.
# - Runs a cache/data smoke check against the OpenMetadata contract cache path.
# - Runs telemetry smoke checks for dq-api and OpenMetadata.
# - Keeps the smoke coverage focused on the secure paths called out in Workstream 5.
# validate: groups=repo,observability
# Version: 1.0
# Last modified: 2026-07-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_internal_tls_smoke.sh"

RUN_HTTP=false
RUN_DATA_CACHE=false
RUN_TELEMETRY=false
RUN_METADATA_TELEMETRY=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --all                Run every smoke check
  --http               Run the Kong auth smoke check
  --data-cache         Run the OpenMetadata cache/data smoke check
  --telemetry          Run the dq-api Grafana/Tempo smoke check
  --metadata-telemetry Run the OpenMetadata Grafana/Tempo smoke check
  --env dev|test|prod
  --env-file PATH
  -h, --help
EOF
}

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  usage
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}

if [ "$#" -eq 0 ]; then
  RUN_HTTP=true
  RUN_DATA_CACHE=true
  RUN_TELEMETRY=true
  RUN_METADATA_TELEMETRY=true
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      RUN_HTTP=true
      RUN_DATA_CACHE=true
      RUN_TELEMETRY=true
      RUN_METADATA_TELEMETRY=true
      shift
      ;;
    --http)
      RUN_HTTP=true
      shift
      ;;
    --data-cache)
      RUN_DATA_CACHE=true
      shift
      ;;
    --telemetry)
      RUN_TELEMETRY=true
      shift
      ;;
    --metadata-telemetry)
      RUN_METADATA_TELEMETRY=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "$my_name" "Unknown arg: $1"
      usage
      exit 1
      ;;
  esac
done

validate_selected_root_env_file "$ROOT_DIR" full
if ! source_selected_root_env_file; then
  exit 1
fi

info "$my_name" "Environment selection: $(describe_root_env_file_selection "$ROOT_DIR" "$ROOT_ENV_FILE") -> $ROOT_ENV_FILE"

if [ "$RUN_HTTP" = true ]; then
  info "$my_name" "Running Kong auth smoke checks"
  "$ROOT_DIR/scripts/validation/smoke_test_auth_kong.sh"
fi

if [ "$RUN_DATA_CACHE" = true ]; then
  info "$my_name" "Running OpenMetadata contract cache smoke checks"
  "$ROOT_DIR/scripts/validation/validate_openmetadata_contract_cache.sh"
fi

if [ "$RUN_TELEMETRY" = true ]; then
  info "$my_name" "Running dq-api Grafana/Tempo smoke checks"
  "$ROOT_DIR/scripts/validation/validate_dq_api_grafana_otel_smoke.sh"
fi

if [ "$RUN_METADATA_TELEMETRY" = true ]; then
  info "$my_name" "Running OpenMetadata Grafana/Tempo smoke checks"
  "$ROOT_DIR/scripts/validation/validate_openmetadata_otel_smoke.sh"
fi

success "$my_name" "Representative internal TLS smoke checks completed successfully"
