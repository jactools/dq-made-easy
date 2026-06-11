from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.api.v1.endpoints.validation_plan_catalog as validation_plan_catalog_endpoints
from app.application.services.rule_dsl_sodacl_lowerer import build_sodacl_artifact_envelope_from_rule_dsl_v2
from app.api.v1.validation_plan_catalog_api import list_plan_catalog
from app.api.presenters.validation_plan_catalog import build_validation_plan_catalog_view
from app.domain.entities import build_validation_run_plan_entity
from app.domain.entities.rule_dsl_ir import build_rule_dsl_v2_semantic_ir
from app.domain.entities.rule_dsl_v2 import RuleDslV2Document


MOCK_DATA_DIR = Path(__file__).resolve().parents[4] / "dq-db" / "mock-data"


def _load_mock_data_rows(filename: str) -> list[dict[str, str]]:
    csv_path = MOCK_DATA_DIR / filename
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _load_mock_data_row(filename: str, row_id: str) -> dict[str, str]:
    for row in _load_mock_data_rows(filename):
        if row.get("id") == row_id:
            return row
    raise AssertionError(f"Missing row {row_id} in {filename}")


class _Repo:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    async def list_plans(self, **kwargs):
        self.last_kwargs = kwargs
        return [
            build_validation_run_plan_entity(
                {
                    "runPlanId": "run-plan-1",
                    "businessKey": "run-plan-1",
                    "workspaceId": "retail-banking",
                    "scopeSelector": {"workspaceId": "retail-banking", "tagIds": ["gold", "regulatory"]},
                    "planningMode": "single_suite",
                    "currentActiveVersionId": "run-plan-version-2",
                    "status": "active",
                    "pendingVersionId": None,
                    "pendingVersionGovernanceState": None,
                    "createdBy": "user-admin",
                    "createdAt": "2026-04-10T07:00:00Z",
                    "updatedAt": "2026-04-10T08:00:00Z",
                    "activatedBy": "user-admin",
                    "activatedAt": "2026-04-10T08:00:00Z",
                    "lastDispatchedRunId": "run-1",
                    "versions": [
                        {
                            "runPlanVersionId": "run-plan-version-1",
                            "runPlanId": "run-plan-1",
                            "governanceState": "draft",
                            "validationArtifactSelection": {
                                "selectionMode": "explicit_refs",
                                "scopeSelector": {"tagIds": ["gold", "regulatory", "gold"]},
                                "artifactRefs": [{"artifactId": "suite-1", "artifactVersion": 1, "engineType": "gx"}],
                            },
                            "artifactId": "suite-1",
                            "artifactVersion": 1,
                            "artifactSnapshot": {
                                "validationArtifactId": "suite-1",
                                "validationArtifactVersion": 1,
                                "engineType": "gx",
                                "artifactContractVersion": "v1",
                                "assignmentScope": {"dataObjectId": "obj-1"},
                                "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-1"]},
                                "compiledFrom": {"ruleIds": ["r-1"], "compilerVersion": "v1", "generatedAt": "2026-04-10T07:10:00Z"},
                                "executionHints": {"recommendedEngineTarget": "pyspark"},
                                "runPlanning": {"engineTarget": "pyspark"},
                                "engineArtifact": {
                                    "engineType": "gx",
                                    "artifactKind": "gx_expectation_suite",
                                    "artifactSchemaVersion": "gx-artifact-envelope/v1",
                                    "payload": {"suiteId": "suite-1", "suiteVersion": 1},
                                },
                            },
                            "scheduleDefinition": {"scheduledAt": "2026-04-12T08:00:00Z"},
                            "createdAt": "2026-04-10T08:00:00Z",
                        },
                        {
                            "runPlanVersionId": "run-plan-version-2",
                            "runPlanId": "run-plan-1",
                            "governanceState": "active",
                            "validationArtifactSelection": {
                                "selectionMode": "explicit_refs",
                                "artifactRefs": [{"artifactId": "suite-2", "artifactVersion": 2, "engineType": "soda"}],
                            },
                            "artifactId": "suite-2",
                            "artifactVersion": 2,
                            "artifactSnapshot": {
                                "validationArtifactId": "suite-2",
                                "validationArtifactVersion": 2,
                                "engineType": "soda",
                                "artifactContractVersion": "v1",
                                "assignmentScope": {"dataObjectId": "obj-1"},
                                "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-2"]},
                                "compiledFrom": {"ruleIds": ["r-1"], "compilerVersion": "v1", "generatedAt": "2026-04-10T08:10:00Z"},
                                "executionHints": {"recommendedEngineTarget": "spark"},
                                "runPlanning": {"engineTarget": "spark"},
                                "engineArtifact": {
                                    "engineType": "soda",
                                    "artifactKind": "sodacl_suite",
                                    "artifactSchemaVersion": "validation-artifact/v1",
                                    "payload": {"suiteId": "suite-2", "suiteVersion": 2},
                                },
                            },
                            "scheduleDefinition": {"scheduledAt": "2026-04-13T08:00:00Z"},
                            "createdAt": "2026-04-10T09:00:00Z",
                        },
                    ],
                }
            )
        ]


class _CsvRepo:
    def __init__(self, plans: list[object]) -> None:
        self._plans = plans
        self.last_kwargs: dict | None = None

    async def list_plans(self, **kwargs):
        self.last_kwargs = kwargs
        return self._plans


@pytest.mark.anyio
async def test_list_plan_catalog_returns_plans_and_suite_summaries() -> None:
    repo = _Repo()

    result = await list_plan_catalog(
        workspace_id="retail-banking",
        business_key=None,
        suite_id=None,
        status=None,
        repository=repo,
    )

    assert repo.last_kwargs == {
        "workspace_id": "retail-banking",
        "business_key": None,
        "status": None,
        "artifact_id": None,
    }
    assert len(result.validationRunPlans) == 1
    assert result.validationRunPlans[0].runPlanId == "run-plan-1"
    assert len(result.validationSuites) == 2
    assert result.validationSuites[0].engineType == "gx"
    assert result.validationSuites[1].engineType == "soda"
    assert result.validationSuites[1].artifactId == "suite-2"
    assert result.validationSuites[1].scheduleDefinition.scheduledAt == "2026-04-13T08:00:00Z"
    assert result.validationSummary.runPlanCount == 1
    assert result.validationSummary.suiteCount == 2
    assert result.validationSummary.engineTypes == ["gx", "soda"]
    assert result.validationRunPlans[0].scopeSelector.tagIds == ["gold", "regulatory"]
    assert result.validationSuites[0].tagIds == ["gold", "regulatory"]


@pytest.mark.anyio
async def test_validation_plan_catalog_endpoint_forwards_to_catalog_api(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    async def _fake_list_plan_catalog(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(validationRunPlans=[], validationSuites=[], validationSummary=SimpleNamespace())

    monkeypatch.setattr(validation_plan_catalog_endpoints._validation_plan_catalog_api, "list_plan_catalog", _fake_list_plan_catalog)

    result = await validation_plan_catalog_endpoints.list_validation_plan_catalog(
        workspace_id="retail-banking",
        business_key="run-plan-1",
        suite_id="suite-1",
        status="active",
        repository=SimpleNamespace(),
    )

    assert calls == {
        "workspace_id": "retail-banking",
        "business_key": "run-plan-1",
        "suite_id": "suite-1",
        "status": "active",
        "repository": calls["repository"],
    }


def test_build_validation_plan_catalog_view_extracts_engine_type_from_gx_suite_snapshot() -> None:
    class _Version:
        runPlanVersionId = "v1"
        governanceState = "active"
        artifactId = "suite-1"
        artifactVersion = 1
        validationArtifactSelection = {"artifactRefs": []}
        artifactSnapshot = {"gxSuite": {"expectations": []}}
        scheduleDefinition = {"scheduledAt": "2026-04-12T08:00:00Z"}
        createdAt = "2026-04-10T08:00:00Z"

    class _Plan:
        runPlanId = "run-plan-1"
        businessKey = "run-plan-1"
        workspaceId = "retail-banking"
        scopeSelector = {"workspaceId": "retail-banking", "tagIds": ["gold", "regulatory"]}
        planningMode = "single_suite"
        status = "active"
        createdAt = "2026-04-10T07:00:00Z"
        updatedAt = "2026-04-10T08:00:00Z"
        versions = [_Version()]

    result = build_validation_plan_catalog_view([_Plan()])

    assert result.validationSuites[0].engineType == "gx"


def test_build_validation_plan_catalog_view_extracts_engine_type_from_engine_artifact_and_artifact_refs() -> None:
    class _VersionWithEngineArtifact:
        runPlanVersionId = "v2"
        governanceState = "active"
        artifactId = "suite-2"
        artifactVersion = 2
        validationArtifactSelection = {"artifactRefs": [{"engineType": "soda"}]}
        artifactSnapshot = {"engineArtifact": {"engineType": "soda"}}
        scheduleDefinition = {"scheduledAt": "2026-04-12T08:00:00Z"}
        createdAt = "2026-04-10T08:00:00Z"

    class _VersionWithoutEngine:
        runPlanVersionId = "v3"
        governanceState = "draft"
        artifactId = None
        artifactVersion = None
        validationArtifactSelection = {"artifactRefs": []}
        artifactSnapshot = {}
        scheduleDefinition = {"scheduledAt": "2026-04-12T09:00:00Z"}
        createdAt = "2026-04-10T09:00:00Z"

    class _Plan:
        runPlanId = "run-plan-2"
        businessKey = "run-plan-2"
        workspaceId = "retail-banking"
        scopeSelector = {"workspaceId": "retail-banking"}
        planningMode = "single_suite"
        status = "active"
        createdAt = "2026-04-10T07:00:00Z"
        updatedAt = "2026-04-10T08:00:00Z"
        versions = [_VersionWithEngineArtifact(), _VersionWithoutEngine()]

    result = build_validation_plan_catalog_view([_Plan()])

    assert [suite.engineType for suite in result.validationSuites] == ["soda", None]


@pytest.mark.anyio
async def test_list_plan_catalog_reads_mixed_engine_plan_from_mock_data_csvs() -> None:
    gx_plan_row = _load_mock_data_row("validation-run-plans.csv", "019e0488-9a54-7c1c-bcfb-2dc4d0b6b4c2")
    gx_version_row = _load_mock_data_row("validation-run-plan-versions.csv", "019e0488-9a54-7621-b273-c73ac5bbfe5e")
    soda_rule_version_row = _load_mock_data_row("rule_versions.csv", "019e0488-9a55-798c-88e8-122cfe8b0f82")

    dsl_path = MOCK_DATA_DIR / soda_rule_version_row["dsl"]
    soda_semantic_model = RuleDslV2Document.model_validate(json.loads(dsl_path.read_text(encoding="utf-8")))
    soda_semantic_ir = build_rule_dsl_v2_semantic_ir(semantic_model=soda_semantic_model)
    soda_artifact = build_sodacl_artifact_envelope_from_rule_dsl_v2(
        semantic_ir=soda_semantic_ir,
        validation_artifact_id="soda_cardholder_name_not_null",
        validation_artifact_version=1,
        resolved_data_object_version_ids=["dov-card-1"],
        rule_id=soda_rule_version_row["rule_id"],
        artifact_key=soda_rule_version_row["id"],
        saved_by=soda_rule_version_row["created_by"],
    )

    mixed_plan = build_validation_run_plan_entity(
        {
            "runPlanId": gx_plan_row["id"],
            "businessKey": gx_plan_row["business_key"],
            "workspaceId": gx_plan_row["workspace_id"],
            "scopeSelector": json.loads((MOCK_DATA_DIR / gx_plan_row["scope_selector_json"]).read_text(encoding="utf-8")),
            "planningMode": gx_plan_row["planning_mode"],
            "currentActiveVersionId": gx_plan_row["current_active_version_id"],
            "status": gx_plan_row["status"],
            "pendingVersionId": None,
            "pendingVersionGovernanceState": None,
            "createdBy": gx_plan_row["created_by"],
            "createdAt": gx_plan_row["created_at"],
            "updatedAt": gx_plan_row["updated_at"],
            "activatedBy": gx_plan_row["activated_by"] or None,
            "activatedAt": gx_plan_row["activated_at"] or None,
            "lastDispatchedRunId": gx_plan_row["last_dispatched_run_id"] or None,
            "versions": [
                {
                    "runPlanVersionId": gx_version_row["id"],
                    "runPlanId": gx_version_row["run_plan_id"],
                    "governanceState": gx_version_row["governance_state"],
                    "validationArtifactSelection": json.loads(
                        (MOCK_DATA_DIR / gx_version_row["validation_artifact_selection_json"]).read_text(encoding="utf-8")
                    ),
                    "artifactId": gx_version_row["artifact_id"],
                    "artifactVersion": int(gx_version_row["artifact_version"]),
                    "artifactSnapshot": json.loads((MOCK_DATA_DIR / gx_version_row["artifact_snapshot_json"]).read_text(encoding="utf-8")),
                    "scheduleDefinition": json.loads((MOCK_DATA_DIR / gx_version_row["schedule_definition_json"]).read_text(encoding="utf-8")),
                    "createdAt": gx_version_row["created_at"],
                },
                {
                    "runPlanVersionId": "csv-soda-version-1",
                    "runPlanId": gx_version_row["run_plan_id"],
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
            ],
            "transitionEvents": [],
        }
    )
    repo = _CsvRepo([mixed_plan])

    result = await list_plan_catalog(
        workspace_id="retail-banking",
        business_key=None,
        suite_id=None,
        status=None,
        repository=repo,
    )

    assert repo.last_kwargs == {
        "workspace_id": "retail-banking",
        "business_key": None,
        "status": None,
        "artifact_id": None,
    }
    assert len(result.validationRunPlans) == 1
    assert result.validationRunPlans[0].runPlanId == gx_plan_row["id"]
    assert len(result.validationSuites) == 2
    assert {suite.engineType for suite in result.validationSuites} == {"gx", "soda"}
    assert result.validationSummary.runPlanCount == 1
    assert result.validationSummary.suiteCount == 2
    assert result.validationSummary.engineTypes == ["gx", "soda"]
