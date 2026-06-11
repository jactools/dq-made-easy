#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TARGET="$ROOT/scripts/seed_local_postgres.sh"

if [ ! -f "$TARGET" ]; then
  echo "ERROR: canonical seed script not found at $TARGET"
  exit 1
fi

echo "Delegating to canonical seed script: $TARGET"
exec bash "$TARGET" "$@"
