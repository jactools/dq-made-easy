#!/usr/bin/env bash
# scripts/init-all.sh
# Purpose: Build, start, and seed all containers in the workspace.
#
# Version: 1.0
# Last modified: 2026-04-12
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/supporting/logging.sh"

my_name="init-all.sh"

info "$my_name" "Building, starting, and seeding all containers..."
./scripts/start-containers.sh --all --seed-all --remove-orphans --force-build --init-db || {
    error "$my_name" "Failed to build, start, or seed containers."
    exit 1
}
success "$my_name" "All containers built, started, and seeded successfully."
