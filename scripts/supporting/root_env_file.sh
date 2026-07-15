#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/env/selection.sh"

if [ -z "${ROOT_DIR:-}" ]; then
	ROOT_DIR="$REPO_ROOT"
fi
