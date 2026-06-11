#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Stopping docker-compose stack and removing containers..."
docker compose down --volumes --remove-orphans

echo "Stopped. You can remove images manually if needed."

exit 0
