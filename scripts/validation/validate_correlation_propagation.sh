#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate correlation-id propagation contract between API and the GX worker.
#
# What it does:
# - Confirms API middleware reads/writes X-Correlation-ID.
# - Confirms the GX worker forwards correlation headers to downstream API calls.
#
# validate: groups=repo,engine

# Version: 1.1
# Last modified: 2026-05-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_correlation_propagation.sh"
API_MW_FILE="${ROOT_DIR}/dq-api/fastapi/app/middleware/correlation_id.py"
ENGINE_FILE="${ROOT_DIR}/dq-engine/gx_dispatch_worker.py"

require_in_file() {
  local needle="$1"
  local file="$2"
  if ! grep -Fq "$needle" "$file"; then
    error "$my_name" "Missing '${needle}' in ${file}"
    exit 1
  fi
}

for required in "$API_MW_FILE" "$ENGINE_FILE"; do
  if [[ ! -f "$required" ]]; then
    error "$my_name" "Missing required file ${required}"
    exit 1
  fi
done

# API ingress/egress correlation contract.
require_in_file 'header_name = "X-Correlation-ID"' "$API_MW_FILE"
require_in_file 'correlation_id = request.headers.get(self.header_name' "$API_MW_FILE"
require_in_file 'response.headers[self.header_name] = correlation_id' "$API_MW_FILE"

# Worker propagation contract to downstream API calls.
require_in_file 'def _api_headers(config: GxWorkerConfig, token_provider: TokenProvider, *, correlation_id: str) -> dict[str, str]:' "$ENGINE_FILE"
require_in_file '"X-Correlation-ID": correlation_id,' "$ENGINE_FILE"
require_in_file 'headers=_api_headers(config, token_provider, correlation_id=correlation_id),' "$ENGINE_FILE"
require_in_file 'path=f"/rulebuilder/v1/gx/runs/{run_id}/report"' "$ENGINE_FILE"

success "$my_name" "correlation propagation checks passed (api -> gx worker)"
