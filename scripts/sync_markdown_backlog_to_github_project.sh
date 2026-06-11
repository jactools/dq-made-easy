#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT_DIR/scripts/python_arm64.sh" "$ROOT_DIR/scripts/sync_markdown_backlog_to_github_project.py" "$@"