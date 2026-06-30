#!/usr/bin/env bash
set -euo pipefail

# Purpose: Validate the mixed GX/Soda execution plan from the live validation stack.
# What it does:
# - Reads the seeded GX run plan and Soda-capable rule version from the live database.
# - Rebuilds the mixed execution-plan catalog view from those DB rows.
# - Fails fast if the mixed plan cannot be reconstructed or the unified summary is wrong.
#
# validate: groups=repo,api
#
# Version: 2.1
# Last modified: 2026-05-14

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/logging.sh"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/supporting/root_env_file.sh"

my_name="validate_mixed_engine_execution_plan.sh"
PYTHON_BIN="$ROOT_DIR/venv/bin/python"
PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"
WORKSPACE_ID="${DQ_VALIDATION_MIXED_ENGINE_WORKSPACE_ID:-retail-banking}"
GX_PLAN_ID="019e0488-9a54-7c1c-bcfb-2dc4d0b6b4c2"
GX_PLAN_VERSION_ID="019e0488-9a54-7621-b273-c73ac5bbfe5e"
SODA_RULE_VERSION_ID="019e0488-9a55-798c-88e8-122cfe8b0f82"

print_usage() {
  cat <<'EOF'
Usage: scripts/validate_mixed_engine_execution_plan.sh

Runs the mixed-engine execution-plan regression against the live database.
EOF
}

if [[ $# -gt 0 ]]; then
  case "$1" in
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      error "$my_name" "Unknown argument: $1"
      print_usage
      exit 2
      ;;
  esac
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
    error "$my_name" "Missing required Python interpreter: $PYTHON_BIN"
    exit 2
fi

if [[ ! -x "$PYTHON_RUNNER" ]]; then
    error "$my_name" "Missing required Python launcher: $PYTHON_RUNNER"
    exit 2
fi

init_root_env_file "$ROOT_DIR"
if ! consume_root_env_selection_args "$ROOT_DIR" "$@"; then
  exit 1
fi

set -- ${ROOT_ENV_SELECTION_REMAINING_ARGS[@]+"${ROOT_ENV_SELECTION_REMAINING_ARGS[@]}"}
validate_selected_root_env_file "$ROOT_DIR" full

if ! source_selected_root_env_file; then
  exit 1
fi

if [[ $# -gt 0 ]]; then
  error "$my_name" "Unknown argument: $1"
  print_usage
  exit 2
fi

info "$my_name" "Running mixed GX/Soda execution plan regression against the host-local live database"

export DQ_RULEBUILDER_ROOT="$ROOT_DIR"

"$PYTHON_RUNNER" --python-bin "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import asyncio
import json
import os
import sys

from sqlalchemy import select

repo_root = os.environ.get("DQ_RULEBUILDER_ROOT", "").strip()
if not repo_root:
    raise SystemExit("Missing required environment variable: DQ_RULEBUILDER_ROOT")

sys.path.insert(0, os.path.join(repo_root, "dq-api", "fastapi"))

from app.application.services.rule_dsl_sodacl_lowerer import build_sodacl_artifact_envelope_from_rule_dsl_v2
from app.domain.entities import build_validation_run_plan_entity
from app.domain.entities.rule_dsl_ir import build_rule_dsl_v2_semantic_ir
from app.domain.entities.rule_dsl_v2 import RuleDslV2Document
from app.infrastructure.orm.models import RuleVersionRow
from app.infrastructure.orm.session import session_scope
from app.infrastructure.repositories.postgres_validation_run_plan_repository import PostgresValidationRunPlanRepository

WORKSPACE_ID = "retail-banking"
GX_PLAN_ID = "019e0488-9a54-7c1c-bcfb-2dc4d0b6b4c2"
GX_PLAN_VERSION_ID = "019e0488-9a54-7621-b273-c73ac5bbfe5e"
SODA_RULE_VERSION_ID = "019e0488-9a55-798c-88e8-122cfe8b0f82"


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _load_rule_version(database_url: str, version_id: str) -> dict[str, object]:
    with session_scope(database_url) as session:
        row = session.execute(
            select(RuleVersionRow).where(RuleVersionRow.id == version_id).limit(1)
        ).scalar_one_or_none()
    if row is None:
        raise SystemExit(f"Rule version '{version_id}' was not found in the live database")
    return {
        "id": str(row.id),
        "rule_id": str(row.rule_id),
        "created_by": str(row.created_by or ""),
        "dsl": str(row.dsl or ""),
    }


def _coerce_mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _extract_engine_type(version: object) -> str | None:
    artifact_snapshot = _coerce_mapping(getattr(version, "artifactSnapshot", None))
    engine_type = artifact_snapshot.get("engineType")
    if engine_type is not None:
        return str(engine_type)

    engine_artifact = _coerce_mapping(artifact_snapshot.get("engineArtifact"))
    engine_type = engine_artifact.get("engineType")
    if engine_type is not None:
        return str(engine_type)

    validation_artifact_selection = _coerce_mapping(getattr(version, "validationArtifactSelection", None))
    artifact_refs = validation_artifact_selection.get("artifactRefs")
    if isinstance(artifact_refs, list) and artifact_refs:
        first_ref = _coerce_mapping(artifact_refs[0])
        engine_type = first_ref.get("engineType")
        if engine_type is not None:
            return str(engine_type)

    if artifact_snapshot:
        if "gxSuite" in artifact_snapshot:
            return "gx"
        if "engineArtifact" in artifact_snapshot:
            return str(_coerce_mapping(artifact_snapshot.get("engineArtifact")).get("engineType") or "") or None

    return None


async def _build_mixed_plan(database_url: str) -> object:
    plan_repository = PostgresValidationRunPlanRepository(database_url)
    gx_plan = await plan_repository.get_plan(GX_PLAN_ID)
    if gx_plan is None:
        raise SystemExit(f"Validation run plan '{GX_PLAN_ID}' was not found in the live database")
    if str(gx_plan.workspaceId or "") != WORKSPACE_ID:
        raise SystemExit(
            f"Validation run plan '{GX_PLAN_ID}' is scoped to {gx_plan.workspaceId!r}, expected {WORKSPACE_ID!r}"
        )
    if len(gx_plan.versions) != 1:
        raise SystemExit(
            f"Validation run plan '{GX_PLAN_ID}' must have exactly one GX version for this regression, found {len(gx_plan.versions)}"
        )

    gx_version = gx_plan.versions[0]
    if str(gx_version.runPlanVersionId or "") != GX_PLAN_VERSION_ID:
        raise SystemExit(
            f"Validation run plan '{GX_PLAN_ID}' has version '{gx_version.runPlanVersionId}', expected '{GX_PLAN_VERSION_ID}'"
        )

    soda_rule_version = _load_rule_version(database_url, SODA_RULE_VERSION_ID)
    soda_semantic_model = RuleDslV2Document.model_validate(json.loads(str(soda_rule_version["dsl"])))
    soda_semantic_ir = build_rule_dsl_v2_semantic_ir(semantic_model=soda_semantic_model)
    soda_artifact = build_sodacl_artifact_envelope_from_rule_dsl_v2(
        semantic_ir=soda_semantic_ir,
        validation_artifact_id="soda_cardholder_name_not_null",
        validation_artifact_version=1,
        resolved_data_object_version_ids=["dov-card-1"],
        rule_id=str(soda_rule_version["rule_id"]),
        artifact_key=str(soda_rule_version["id"]),
        saved_by=str(soda_rule_version["created_by"] or "system"),
    )

    mixed_plan_payload = gx_plan.model_dump(mode="python", by_alias=False, exclude_none=True)
    mixed_plan_payload["pendingVersionId"] = None
    mixed_plan_payload["pendingVersionGovernanceState"] = None
    mixed_plan_payload["transitionEvents"] = []
    mixed_plan_payload["versions"] = [
        gx_version.model_dump(mode="python", by_alias=False, exclude_none=True),
        {
            "runPlanVersionId": "csv-soda-version-1",
            "runPlanId": GX_PLAN_ID,
            "governanceState": "active",
            "validationArtifactSelection": {
                "selectionMode": "explicit_refs",
                "artifactRefs": [
                    {
                        "artifactId": soda_artifact.validationArtifactId,
                        "artifactVersion": soda_artifact.validationArtifactVersion,
                        "engineType": "soda",
                    }
                ],
            },
            "artifactId": soda_artifact.validationArtifactId,
            "artifactVersion": soda_artifact.validationArtifactVersion,
            "artifactSnapshot": soda_artifact.model_dump(mode="python", by_alias=False, exclude_none=True),
            "scheduleDefinition": {"scheduledAt": "2026-04-12T09:45:00Z"},
            "createdAt": "2026-04-12T09:45:00Z",
        },
    ]

    mixed_plan = build_validation_run_plan_entity(mixed_plan_payload)
    suite_engine_types = [_extract_engine_type(version) for version in mixed_plan.versions]
    engine_types = sorted({str(engine_type) for engine_type in suite_engine_types if engine_type})

    if len(mixed_plan.versions) != 2:
        raise SystemExit(f"Expected 2 validation suites, got {len(mixed_plan.versions)}")
    if engine_types != ["gx", "soda"]:
        raise SystemExit(f"Expected engine types ['gx', 'soda'], got {engine_types}")
    if suite_engine_types != ["gx", "soda"]:
        raise SystemExit(f"Expected suite engine order ['gx', 'soda'], got {suite_engine_types}")

    if mixed_plan.runPlanId != GX_PLAN_ID:
        raise SystemExit(
            f"Expected run plan id '{GX_PLAN_ID}', got '{mixed_plan.runPlanId}'"
        )

    print(
        json.dumps(
            {
                "run_plan_id": GX_PLAN_ID,
                "run_plan_version_id": GX_PLAN_VERSION_ID,
                "soda_rule_version_id": SODA_RULE_VERSION_ID,
                "summary": {
                    "runPlanCount": 1,
                    "suiteCount": 2,
                    "engineTypes": engine_types,
                },
            },
            sort_keys=True,
        )
    )


asyncio.run(_build_mixed_plan(_require_env("DQ_DB_LOCAL_URL")))
PY

success "$my_name" "mixed GX/Soda execution plan regression passed"