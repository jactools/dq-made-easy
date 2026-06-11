#!/usr/bin/env bash
set -euo pipefail

# Purpose: Verify the Git-first rule registry layout in dq-db/mock-data.
# What it does:
# - Ensures every rule row points at a tracked rules/<rule-id>/dsl.json payload.
# - Ensures every rule version row points at tracked rule_versions/<version-id>/dsl.json and tags.json payloads.
# - Ensures every GX suite registry row points at a tracked gx-suite-registry/<suite-id>/gx_suite.json payload.
# - Fails fast if any referenced artifact is missing or the registry contract is malformed.
#
# validate: groups=repo
# Version: 1.0.0
# Last modified: 2026-05-27

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MY_NAME="validate_rule_registry_layout.sh"

if [[ $# -gt 0 ]]; then
  case "$1" in
    -h|--help)
      cat <<'EOF'
Usage: scripts/validate_rule_registry_layout.sh

Validates that the tracked dq-db/mock-data rule registry uses the canonical
Git-first layout and that every registry row resolves to a committed JSON file.
EOF
      exit 0
      ;;
    *)
      echo "[$MY_NAME] Unknown argument: $1" >&2
      exit 2
      ;;
  esac
fi

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[$MY_NAME] Missing required Python executable: $PYTHON_BIN" >&2
  exit 2
fi

export DQ_RULEBUILDER_ROOT="$ROOT_DIR"

"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import csv
import os
from pathlib import Path


root = Path(os.environ["DQ_RULEBUILDER_ROOT"]).resolve()
mock_data = root / "dq-db" / "mock-data"

if not mock_data.is_dir():
    raise SystemExit(f"FAILED: mock-data directory not found: {mock_data}")


def load_rows(name: str) -> list[dict[str, str]]:
    path = mock_data / name
    if not path.is_file():
        raise SystemExit(f"FAILED: registry source file not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def normalize(value: object) -> str:
    return str(value or "").strip().replace("\\", "/")


def validate_path(row_kind: str, row_id: str, column_name: str, relative_path: str, expected_relative_path: str, errors: list[str]) -> None:
    if not relative_path:
        errors.append(f"{row_kind}:{row_id}:{column_name} is missing")
        return

    if relative_path != expected_relative_path:
        errors.append(
            f"{row_kind}:{row_id}:{column_name} expected {expected_relative_path!r} but found {relative_path!r}"
        )
        return

    absolute_path = mock_data / relative_path
    if not absolute_path.is_file():
        errors.append(f"{row_kind}:{row_id}:{column_name} points at missing file {absolute_path}")


rules = load_rows("rules.csv")
rule_versions = load_rows("rule_versions.csv")
gx_suites = load_rows("gx-suite-registry.csv")

errors: list[str] = []

for row in rules:
    rule_id = normalize(row.get("id"))
    validate_path("rules", rule_id, "dsl", normalize(row.get("dsl")), f"rules/{rule_id}/dsl.json", errors)

for row in rule_versions:
    version_id = normalize(row.get("id"))
    validate_path("rule_versions", version_id, "dsl", normalize(row.get("dsl")), f"rule_versions/{version_id}/dsl.json", errors)
    validate_path("rule_versions", version_id, "tags", normalize(row.get("tags")), f"rule_versions/{version_id}/tags.json", errors)

for row in gx_suites:
    suite_id = normalize(row.get("id"))
    validate_path(
        "gx-suite-registry",
        suite_id,
        "gx_suite_json",
        normalize(row.get("gx_suite_json")),
        f"gx-suite-registry/{suite_id}/gx_suite.json",
        errors,
    )

if errors:
    print("FAILED: canonical rule registry layout is incomplete or out of sync.")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print(
    "PASS: validated "
    f"{len(rules)} rule row(s), {len(rule_versions)} rule version row(s), and {len(gx_suites)} GX suite registry row(s)."
)
PY