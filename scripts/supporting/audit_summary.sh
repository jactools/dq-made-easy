#!/usr/bin/env bash

# Purpose: Shared JSON audit summary writer for shell startup and seed flows.
#
# What it does:
# - Writes a JSON audit record to the requested path.
# - Accepts arbitrary key/value fields from callers so multiple scripts can reuse it.
# - Creates the parent audit directory automatically.

write_audit_summary_json() {
  local summary_path="$1"
  shift

  local summary_dir
  summary_dir="$(dirname "$summary_path")"
  mkdir -p "$summary_dir"

  "$PYTHON_BIN" - "$summary_path" "$@" <<'PY'
import json
import sys

summary_path = sys.argv[1]
raw_pairs = sys.argv[2:]

if len(raw_pairs) % 2 != 0:
    raise SystemExit("audit summary writer expected key/value pairs")

payload = {}
for index in range(0, len(raw_pairs), 2):
    payload[raw_pairs[index]] = raw_pairs[index + 1]

with open(summary_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}