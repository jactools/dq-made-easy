#!/usr/bin/env bash
set -euo pipefail

# Purpose: Verify that every seeded GX run plan has a matching neutral validation run plan.
# What it does:
# - Reads the root mock-data CSVs for GX run plans, GX run-plan versions, validation run plans, and validation run-plan versions.
# - Fails fast if any GX run plan id is missing from validation-run-plans.csv.
# - Fails fast if any GX run-plan version id is missing from validation-run-plan-versions.csv.
# - Allows extra neutral-only validation plans for mixed-engine showcase data.
#
# validate: groups=repo
# Version: 1.0.0
# Last modified: 2026-05-19

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MY_NAME="validate_gx_run_plan_mirroring.sh"

if [[ $# -gt 0 ]]; then
  case "$1" in
    -h|--help)
      cat <<'EOF'
Usage: scripts/validate_gx_run_plan_mirroring.sh

Validates that every GX run plan and GX run-plan version in dq-db/mock-data
has a canonical neutral validation-plan counterpart.
EOF
      exit 0
      ;;
    *)
      echo "[$MY_NAME] Unknown argument: $1" >&2
      exit 2
      ;;
  esac
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[$MY_NAME] Missing required command: python3" >&2
  exit 2
fi

export DQ_RULEBUILDER_ROOT="$ROOT_DIR"

python3 - <<'PY'
from __future__ import annotations

import csv
import os
from pathlib import Path

root = Path(os.environ["DQ_RULEBUILDER_ROOT"]).resolve()
mock_data = root / "dq-db" / "mock-data"

def load_rows(name: str) -> list[dict[str, str]]:
    path = mock_data / name
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

gx_plans = load_rows("gx-run-plans.csv")
gx_versions = load_rows("gx-run-plan-versions.csv")
validation_plans = load_rows("validation-run-plans.csv")
validation_versions = load_rows("validation-run-plan-versions.csv")

validation_plans_by_id = {row["id"]: row for row in validation_plans}
validation_versions_by_id = {row["id"]: row for row in validation_versions}

missing_plans: list[str] = []
plan_mismatches: list[str] = []
missing_versions: list[str] = []
version_mismatches: list[str] = []

for gx_plan in gx_plans:
    plan_id = gx_plan["id"].strip()
    validation_plan = validation_plans_by_id.get(plan_id)
    if validation_plan is None:
        missing_plans.append(plan_id)
        continue

    for column in ("business_key", "workspace_id", "planning_mode", "current_active_version_id"):
        gx_value = gx_plan.get(column, "").strip()
        validation_value = validation_plan.get(column, "").strip()
        if gx_value != validation_value:
            plan_mismatches.append(
                f"{plan_id}:{column} gx={gx_value!r} validation={validation_value!r}"
            )

for gx_version in gx_versions:
    version_id = gx_version["id"].strip()
    validation_version = validation_versions_by_id.get(version_id)
    if validation_version is None:
        missing_versions.append(version_id)
        continue

    for column in (
        "run_plan_id",
        "governance_state",
        "validation_status",
        "review_status",
        "effective_from",
        "supersedes_version_id",
        "created_by",
        "created_at",
    ):
        gx_value = gx_version.get(column, "").strip()
        validation_value = validation_version.get(column, "").strip()
        if gx_value != validation_value:
            version_mismatches.append(
                f"{version_id}:{column} gx={gx_value!r} validation={validation_value!r}"
            )

if missing_plans or plan_mismatches or missing_versions or version_mismatches:
    print("FAILED: GX mock-data is missing canonical validation-plan coverage.")
    if missing_plans:
      print("- Missing validation-run-plans ids:")
      for plan_id in missing_plans:
          print(f"  - {plan_id}")
    if plan_mismatches:
        print("- Validation-plan field mismatches:")
        for item in plan_mismatches:
            print(f"  - {item}")
    if missing_versions:
        print("- Missing validation-run-plan-version ids:")
        for version_id in missing_versions:
            print(f"  - {version_id}")
    if version_mismatches:
        print("- Validation-run-plan-version field mismatches:")
        for item in version_mismatches:
            print(f"  - {item}")
    raise SystemExit(1)

print(
    f"PASS: mirrored {len(gx_plans)} GX run plan(s) and {len(gx_versions)} GX run-plan version(s) into canonical validation CSVs."
)
extra_validation_plans = sorted(set(validation_plans_by_id) - {row["id"].strip() for row in gx_plans})
if extra_validation_plans:
    print(f"INFO: validation-only plan ids: {', '.join(extra_validation_plans)}")
PY
