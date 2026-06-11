from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock

from app.application.services.gx_run_plan_seed_resolver import GxRunPlanSeedResolutionService
from app.application.services.gx_run_plan_seed_resolver import ResolveGxRunPlanSeedCommand
from app.domain.entities import ValidationArtifactEngineArtifactEntity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact


@pytest.fixture
def gx_validation_artifact() -> object:
    return build_validation_artifact_envelope_from_gx_artifact(
        {
            "suiteId": "gx_suite_1",
            "suiteVersion": 1,
            "artifactVersion": "v1",
            "assignmentScope": {"dataObjectId": "do_1", "datasetId": None, "dataProductId": None},
            "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1"]},
            "gxSuite": {
                "expectation_suite_name": "dq_suite",
                "expectations": [
                    {
                        "expectation_type": "expect_column_values_to_not_be_null",
                        "kwargs": {"column": "order_id"},
                    }
                ],
                "meta": {},
            },
            "compiledFrom": {
                "ruleIds": ["rule_1"],
                "compilerVersion": "dq-compiler-7.3",
                "generatedAt": "2026-03-22T10:30:00Z",
            },
            "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": ["order_id"]},
            "executionContract": {
                "engineType": "gx",
                "engineTarget": "pyspark",
                "executionShape": "single_object",
                "traceability": {
                    "ruleId": "rule_1",
                    "ruleVersionId": "rule_version_1",
                    "gxSuiteId": "gx_suite_1",
                    "gxSuiteVersion": 1,
                    "dataObjectVersionId": "dov_1",
                },
            },
        }
    )


@pytest.fixture
def grouped_execution_planner() -> object:
    return SimpleNamespace(build_plan=AsyncMock(return_value={"suite_count": 1, "batch_count": 1}))


@pytest.fixture
def rules_repository() -> object:
    return SimpleNamespace(
        list_rule_records=AsyncMock(
            return_value=[
                SimpleNamespace(id="rule_1", tag_ids=["finance"]),
                SimpleNamespace(id="rule_2", tag_ids=["pii"]),
            ]
        )
    )


@pytest.mark.anyio
async def test_resolve_single_suite_seed_uses_validation_artifact_repository(
    gx_validation_artifact,
    grouped_execution_planner,
    rules_repository,
) -> None:
    repository = SimpleNamespace(get_artifact_by_id=AsyncMock(return_value=gx_validation_artifact))
    service = GxRunPlanSeedResolutionService(
        artifact_repository=repository,
        grouped_execution_planner=grouped_execution_planner,
        rules_repository=rules_repository,
    )

    seed = await service.resolve_seed(
        ResolveGxRunPlanSeedCommand(planning_mode="single_suite", suite_id="gx_suite_1", suite_version=1)
    )

    repository.get_artifact_by_id.assert_awaited_once_with(
        artifact_id="gx_suite_1",
        artifact_version=1,
        status="active",
    )
    assert seed.suiteId == "gx_suite_1"
    assert seed.suiteVersion == 1
    assert seed.gxSuiteSelection.selectionMode == "single_suite"
    assert seed.gxSuiteSelection.suiteRefs[0].engineType == "gx"


@pytest.mark.anyio
async def test_resolve_grouped_scope_seed_uses_validation_artifact_repository(
    gx_validation_artifact,
    grouped_execution_planner,
    rules_repository,
) -> None:
    repository = SimpleNamespace(list_artifacts=AsyncMock(return_value=[gx_validation_artifact]))
    service = GxRunPlanSeedResolutionService(
        artifact_repository=repository,
        grouped_execution_planner=grouped_execution_planner,
        rules_repository=rules_repository,
    )

    seed = await service.resolve_seed(
        ResolveGxRunPlanSeedCommand(planning_mode="grouped_scope", data_object_version_id="dov_1")
    )

    repository.list_artifacts.assert_awaited_once_with(
        data_object_id=None,
        data_object_version_id="dov_1",
        dataset_id=None,
        data_product_id=None,
        status="active",
        latest_only=True,
    )
    grouped_execution_planner.build_plan.assert_awaited_once()
    planner_arg = grouped_execution_planner.build_plan.await_args.args[0][0]
    assert isinstance(planner_arg, ValidationArtifactEnvelopeEntity)
    assert seed.gxSuiteSelection.selectionMode == "grouped_scope"
    assert seed.gxSuiteSelection.suiteRefs[0].suiteId == "gx_suite_1"
    assert seed.gxSuiteSelection.suiteRefs[0].engineType == "gx"
    assert seed.suiteSnapshot.groupedExecutionPlan.suiteCount == 1


@pytest.mark.anyio
async def test_resolve_single_suite_seed_fails_closed_for_non_gx_artifact(grouped_execution_planner) -> None:
    repository = SimpleNamespace(
        get_artifact_by_id=AsyncMock(
            return_value=ValidationArtifactEnvelopeEntity(
                validationArtifactId="artifact-1",
                validationArtifactVersion=1,
                artifactContractVersion="v1",
                engineType="soda",
                engineArtifact=ValidationArtifactEngineArtifactEntity(
                    engineType="soda",
                    artifactKind="rule_bundle",
                    artifactSchemaVersion="v1",
                    payload={"id": "artifact-1"},
                ),
            )
        )
    )
    service = GxRunPlanSeedResolutionService(
        artifact_repository=repository,
        grouped_execution_planner=grouped_execution_planner,
        rules_repository=SimpleNamespace(list_rule_records=AsyncMock(return_value=[])),
    )

    with pytest.raises(HTTPException) as error:
        await service.resolve_seed(
            ResolveGxRunPlanSeedCommand(planning_mode="single_suite", suite_id="artifact-1", suite_version=1)
        )

    assert error.value.status_code == 422
    assert error.value.detail["error"] == "unsupported_engine_type"


@pytest.mark.anyio
async def test_resolve_grouped_scope_seed_filters_by_tag_ids(gx_validation_artifact, grouped_execution_planner, rules_repository) -> None:
    second_artifact = build_validation_artifact_envelope_from_gx_artifact(
        {
            "suiteId": "gx_suite_2",
            "suiteVersion": 1,
            "artifactVersion": "v1",
            "assignmentScope": {"dataObjectId": "do_2", "datasetId": None, "dataProductId": None},
            "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_2"]},
            "gxSuite": {"expectation_suite_name": "dq_suite_2", "expectations": [], "meta": {}},
            "compiledFrom": {"ruleIds": ["rule_2"], "compilerVersion": "dq-compiler-7.3", "generatedAt": "2026-03-22T10:30:00Z"},
            "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": ["order_id"]},
            "executionContract": {
                "engineType": "gx",
                "engineTarget": "pyspark",
                "executionShape": "single_object",
                "traceability": {
                    "ruleId": "rule_2",
                    "ruleVersionId": "rule_version_2",
                    "gxSuiteId": "gx_suite_2",
                    "gxSuiteVersion": 1,
                    "dataObjectVersionId": "dov_2",
                },
            },
        }
    )
    repository = SimpleNamespace(list_artifacts=AsyncMock(return_value=[gx_validation_artifact, second_artifact]))
    service = GxRunPlanSeedResolutionService(
        artifact_repository=repository,
        grouped_execution_planner=grouped_execution_planner,
        rules_repository=rules_repository,
    )

    seed = await service.resolve_seed(
        ResolveGxRunPlanSeedCommand(planning_mode="grouped_scope", data_object_version_id="dov_1", tag_ids=["finance"])
    )

    assert [ref.suiteId for ref in seed.gxSuiteSelection.suiteRefs] == ["gx_suite_1"]