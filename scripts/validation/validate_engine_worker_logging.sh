#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate structured logging contract in dq-engine worker.
#
# What it does:
# - Ensures engine logging utilities and key event names exist.
# - Validates correlation ID is included in emitted events.
#
# validate: groups=repo,governance,engine

# Version: 1.1
# Last modified: 2026-05-07

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="validate_engine_worker_logging.sh"
ENGINE_MAIN="${ROOT_DIR}/dq-engine/gx_dispatch_worker.py"

for required in "$ENGINE_MAIN"; do
  if [[ ! -f "$required" ]]; then
    error "$my_name" "Missing required file ${required}"
    exit 1
  fi
done

require_in_file() {
  local needle="$1"
  local file="$2"
  if ! grep -Fq -- "$needle" "$file"; then
    error "$my_name" "Missing '${needle}' in ${file}"
    exit 1
  fi
}

# Engine JSON logging baseline + execution/failure events with correlation.
require_in_file 'from dq_utils.logging_utils import configure_logging' "$ENGINE_MAIN"
require_in_file 'from dq_utils.logging_utils import log_event' "$ENGINE_MAIN"
require_in_file '"gx.worker.heartbeat.failed"' "$ENGINE_MAIN"
require_in_file 'reason="GX worker execution failed"' "$ENGINE_MAIN"
require_in_file 'correlation_id=correlation_id' "$ENGINE_MAIN"

success "$my_name" "engine/worker structured logging checks passed"