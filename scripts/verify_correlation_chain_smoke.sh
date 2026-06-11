#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec "$SCRIPT_DIR/python_arm64.sh" "$SCRIPT_DIR/validation/verify_correlation_chain_smoke.py" "$@"