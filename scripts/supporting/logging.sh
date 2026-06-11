# Purpose: Canonical entrypoint for shared shell logging helpers.
#
# What it does:
# - Loads the logging implementation module from scripts/supporting/logging/core.sh.
# - Keeps the public entrypoint stable for existing callers.
#
# Version: 1.0
# Last modified: 2026-05-08

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/logging/core.sh"

