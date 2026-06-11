#!/usr/bin/env bash
set -euo pipefail

# In-image entrypoint for reseeding a running dq database container.
# This script is baked into the dq-db image so it can run without repository files.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/reseed_in_container.sh" "$@"
