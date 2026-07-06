#!/usr/bin/env bash

# Purpose: Clean and reinstall local project dependencies.
#
# What it does:
# - Reinstalls npm dependencies for dq-ui, dq-api, and dq-profiling.
# - Recreates the dq-engine Python venv and reinstalls requirements.
#
# Version: 1.0
# Last modified: 2026-04-07
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/supporting/logging.sh"
my_name="clean_install.sh"

if [ ! -f "$ROOT_DIR/.npmrc" ]; then
	error "$my_name" "Missing required npm config: $ROOT_DIR/.npmrc"
	exit 1
fi
export NPM_CONFIG_USERCONFIG="$ROOT_DIR/.npmrc"

info "$my_name" "Cleaning and reinstalling npm dependencies for dq-ui..."
cd "$ROOT_DIR/dq-ui"
rm -f package-lock.json
rm -rf node_modules
npm install --include=dev --no-audit --no-fund

info "$my_name" "Cleaning and reinstalling npm dependencies for dq-api..."
cd "$ROOT_DIR/dq-api"
rm -f package-lock.json
rm -rf node_modules
npm install --include=dev --no-audit --no-fund

info "$my_name" "Cleaning and reinstalling npm dependencies for dq-profiling..."
cd "$ROOT_DIR/dq-profiling"
rm -f package-lock.json
rm -rf node_modules
npm install --include=dev --no-audit --no-fund

info "$my_name" "Cleaning and reinstalling Python dependencies for dq-engine..."
cd "$ROOT_DIR/dq-engine"
rm -rf venv
"$PYTHON_RUNNER" -m venv venv
source venv/bin/activate
pip install --no-cache-dir -r requirements.txt

success "$my_name" "All dependencies cleaned and reinstalled successfully."

