import asyncio
from typing import Any

import pytest

from app.domain.entities import ValidationArtifactAssignmentScopeEntity
from app.domain.entities import ValidationArtifactCompiledFromEntity
from app.domain.entities import ValidationArtifactEngineArtifactEntity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import ValidationArtifactExecutionHintsEntity
from app.domain.entities import ValidationArtifactResolvedExecutionScopeEntity
from app.domain.entities import ValidationArtifactRunPlanningEntity
from app.domain.entities import ValidationArtifactRunPlanningTraceabilityEntity

from app.application.services.grouped_execution_planner import GroupedExecutionPlanError
from app.application.services.grouped_execution_planner import GroupedExecutionPlanner
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact


def _suite_envelope(*, suite_id: str, suite_version: int, target_ids: list[str], marker: str) -> dict:
    return {
        "suiteId": suite_id,
        "suiteVersion": suite_version,
        "artifactVersion": "v1",
        "assignmentScope": {
            "dataObjectId": "do-1",
            "datasetId": "ds-1",
            "dataProductId": "odcs.dp.sales-001",
        },
        "resolvedExecutionScope": {"dataObjectVersionIds": target_ids},
        "gxSuite": {"expectation_suite_name": f"{suite_id}_v{suite_version}", "expectations": [], "meta": {"marker": marker}},
        "compiledFrom": {"ruleIds": [f"rule-{suite_id}"], "compilerVersion": "dq-compiler-7.3", "generatedAt": "2026-04-06T00:00:00Z"},
        "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": ["id"]},
    }


def _incremental_suite_envelope(
    *,
    suite_id: str,
    suite_version: int,
    target_ids: list[str],
    marker: str,
    selection_mode: str,
    selected_target_ids: list[str],
) -> dict:
    envelope = _suite_envelope(suite_id=suite_id, suite_version=suite_version, target_ids=target_ids, marker=marker)
    envelope["executionHints"]["incrementalSelection"] = {
        "selectionMode": selection_mode,
        "selectedDataObjectVersionIds": selected_target_ids,
    }
    return envelope


@pytest.fixture()
def planner() -> GroupedExecutionPlanner:
    return GroupedExecutionPlanner()


def test_build_plan_groups_suites_by_shared_target(planner: GroupedExecutionPlanner) -> None:
    plan = asyncio.run(
        planner.build_plan(
            [
                _suite_envelope(suite_id="suite-a", suite_version=1, target_ids=["dov-1", "dov-2"], marker="a"),
                _suite_envelope(suite_id="suite-b", suite_version=1, target_ids=["dov-1"], marker="b"),
                _suite_envelope(suite_id="suite-c", suite_version=2, target_ids=["dov-2"], marker="c"),
            ]
        )
    )

    assert plan["suiteCount"] == 3
    assert plan["batchCount"] == 2
    assert [batch["dataObjectVersionId"] for batch in plan["batches"]] == ["dov-1", "dov-2"]

    first_batch = plan["batches"][0]
    assert first_batch["suiteIds"] == ["suite-a", "suite-b"]
    assert first_batch["suites"][0]["gxSuite"]["meta"]["marker"] == "a"

    second_batch = plan["batches"][1]
    assert second_batch["suiteIds"] == ["suite-a", "suite-c"]


def test_build_plan_deduplicates_target_ids_within_suite(planner: GroupedExecutionPlanner) -> None:
    plan = asyncio.run(
        planner.build_plan(
            [_suite_envelope(suite_id="suite-d", suite_version=3, target_ids=["dov-9", "dov-9", "dov-8"], marker="d")]
        )
    )

    assert plan["batchCount"] == 2
    assert plan["batches"][0]["suiteIds"] == ["suite-d"]
    assert plan["batches"][1]["suiteIds"] == ["suite-d"]
    assert plan["batches"][0]["suites"][0]["resolvedExecutionScope"]["dataObjectVersionIds"] == ["dov-9", "dov-8"]


def test_build_plan_accepts_suite_model_input(planner: GroupedExecutionPlanner) -> None:
    from app.domain.entities import GxArtifactAssignmentScopeEntity
    from app.domain.entities import GxArtifactCompiledFromEntity
    from app.domain.entities import GxArtifactEnvelopeEntity
    from app.domain.entities import GxArtifactExecutionHintsEntity
    from app.domain.entities import GxArtifactResolvedExecutionScopeEntity

    envelope = GxArtifactEnvelopeEntity(
        suiteId="suite-e",
        suiteVersion=1,
        artifactVersion="v1",
        assignmentScope=GxArtifactAssignmentScopeEntity(dataObjectId="do-1"),
        resolvedExecutionScope=GxArtifactResolvedExecutionScopeEntity(dataObjectVersionIds=["dov-7"]),
        gxSuite={"expectation_suite_name": "suite_e_v1", "expectations": [], "meta": {}},
        compiledFrom=GxArtifactCompiledFromEntity(ruleIds=["rule-e"], compilerVersion="dq-compiler-7.3", generatedAt="2026-04-06T00:00:00Z"),
        executionHints=GxArtifactExecutionHintsEntity(recommendedEngine="pyspark", primaryKeyFields=[]),
    )

    plan = asyncio.run(planner.build_plan([envelope]))

    assert plan["suiteCount"] == 1
    assert plan["batches"][0]["dataObjectVersionId"] == "dov-7"


def test_build_plan_accepts_validation_artifact_model_input(planner: GroupedExecutionPlanner) -> None:
    envelope = build_validation_artifact_envelope_from_gx_artifact(
        _suite_envelope(suite_id="suite-j", suite_version=1, target_ids=["dov-11"], marker="j")
    )

    plan = asyncio.run(planner.build_plan([envelope]))

    assert plan["suiteCount"] == 1
    assert plan["batches"][0]["dataObjectVersionId"] == "dov-11"
    assert plan["batches"][0]["suites"][0]["validationArtifactId"] == "suite-j"
    assert plan["batches"][0]["suites"][0]["engineType"] == "gx"


def test_build_plan_accepts_validation_artifact_dict_input(planner: GroupedExecutionPlanner) -> None:
    envelope = build_validation_artifact_envelope_from_gx_artifact(
        _suite_envelope(suite_id="suite-k", suite_version=2, target_ids=["dov-12"], marker="k")
    ).model_dump(mode="python", by_alias=False, exclude_none=False)

    plan = asyncio.run(planner.build_plan([envelope]))

    assert plan["suiteCount"] == 1
    assert plan["batches"][0]["dataObjectVersionId"] == "dov-12"
    assert plan["batches"][0]["suites"][0]["validationArtifactId"] == "suite-k"
    assert plan["batches"][0]["suites"][0]["engineType"] == "gx"


def test_build_plan_marks_sql_pushdown_execution_path_for_pyspark_native_suites(
    planner: GroupedExecutionPlanner,
) -> None:
    envelope = _suite_envelope(suite_id="suite-pushdown", suite_version=1, target_ids=["dov-22"], marker="pushdown")
    envelope["executionHints"]["recommendedEngine"] = "pyspark_native"
    envelope["executionHints"]["evidence"] = {"emitGeneratedSql": True}

    plan = asyncio.run(planner.build_plan([envelope]))

    assert plan["suiteCount"] == 1
    assert plan["batchCount"] == 1
    assert plan["plannerChoice"] == "full_scope"
    assert plan["executionPath"] == "sql_pushdown_grouped_execution"
    assert plan["batches"][0]["executionPath"] == "sql_pushdown_grouped_execution"


def _validation_pyspark_native_envelope(*, suite_id: str, suite_version: int, target_ids: list[str]) -> ValidationArtifactEnvelopeEntity:
    target_id = target_ids[0]
    return ValidationArtifactEnvelopeEntity(
        validationArtifactId=suite_id,
        validationArtifactVersion=suite_version,
        artifactContractVersion="v1",
        engineType="pyspark_native",
        assignmentScope=ValidationArtifactAssignmentScopeEntity(
            dataObjectId="do-1",
            datasetId="ds-1",
            dataProductId="odcs.dp.sales-001",
        ),
        resolvedExecutionScope=ValidationArtifactResolvedExecutionScopeEntity(
            dataObjectVersionIds=target_ids,
        ),
        compiledFrom=ValidationArtifactCompiledFromEntity(
            ruleIds=[f"rule-{suite_id}"],
            compilerVersion="dq-compiler-7.3",
            generatedAt="2026-04-06T00:00:00Z",
        ),
        executionHints=ValidationArtifactExecutionHintsEntity(
            recommendedEngineTarget="pyspark",
            primaryKeyFields=["id"],
            supportedExecutionShapes=["single_object"],
            evidence={"emitGeneratedSql": True},
        ),
        runPlanning=ValidationArtifactRunPlanningEntity(
            engineTarget="pyspark",
            executionShape="single_object",
            groupingKey="data_object_version_id",
            groupingValues=target_ids,
            traceability=ValidationArtifactRunPlanningTraceabilityEntity(
                ruleId=f"rule-{suite_id}",
                ruleVersionId=f"rv-{suite_id}",
                validationArtifactId=suite_id,
                validationArtifactVersion=suite_version,
                dataObjectVersionId=target_id,
            ),
        ),
        engineArtifact=ValidationArtifactEngineArtifactEntity(
            engineType="pyspark_native",
            artifactKind="pyspark_native_plan",
            artifactSchemaVersion="pyspark-native-artifact-envelope/v1",
            payload={
                "artifact_id": suite_id,
                "artifact_revision": suite_version,
                "artifact_version": "v1",
                "engine_type": "pyspark_native",
                "engine_target": "pyspark",
                "assignment_scope": {
                    "data_object_id": "do-1",
                    "dataset_id": "ds-1",
                    "data_product_id": "odcs.dp.sales-001",
                },
                "resolved_execution_scope": {"data_object_version_ids": target_ids},
                "compiled_from": {
                    "rule_ids": [f"rule-{suite_id}"],
                    "compiler_version": "dq-compiler-7.3",
                    "generated_at": "2026-04-06T00:00:00Z",
                },
                "execution_hints": {
                    "primary_key_fields": ["id"],
                    "business_key_fields": [],
                    "supported_execution_shapes": ["single_object"],
                    "evidence": {"emit_generated_sql": True},
                },
                "traceability": {
                    "rule_id": f"rule-{suite_id}",
                    "rule_version_id": f"rv-{suite_id}",
                    "artifact_id": suite_id,
                    "artifact_revision": suite_version,
                    "data_object_version_id": target_id,
                },
                "pyspark_plan": {
                    "execution_shape": "single_object",
                    "input_mode": "spark_dataframe",
                    "checks": [
                        {
                            "check_id": f"check-{suite_id}",
                            "check_kind": "not_null",
                            "column_refs": ["id"],
                            "assertion": {"predicate_sql": "id IS NOT NULL"},
                            "severity": "error",
                        }
                    ],
                },
            },
        ),
    )


def test_build_plan_marks_sql_pushdown_execution_path_for_pyspark_native_validation_artifacts(
    planner: GroupedExecutionPlanner,
) -> None:
    envelope = _validation_pyspark_native_envelope(
        suite_id="suite-pushdown-native",
        suite_version=1,
        target_ids=["dov-22"],
    )

    plan = asyncio.run(planner.build_plan([envelope]))

    assert plan["suiteCount"] == 1
    assert plan["batchCount"] == 1
    assert plan["plannerChoice"] == "full_scope"
    assert plan["executionPath"] == "sql_pushdown_grouped_execution"
    assert plan["batches"][0]["executionPath"] == "sql_pushdown_grouped_execution"


def test_build_plan_filters_incremental_targets(planner: GroupedExecutionPlanner) -> None:
    plan = asyncio.run(
        planner.build_plan(
            [
                _incremental_suite_envelope(
                    suite_id="suite-inc",
                    suite_version=1,
                    target_ids=["dov-1", "dov-2", "dov-3"],
                    marker="inc",
                    selection_mode="changed_slices",
                    selected_target_ids=["dov-2", "dov-3"],
                )
            ]
        )
    )

    assert plan["suiteCount"] == 1
    assert plan["batchCount"] == 2
    assert [batch["dataObjectVersionId"] for batch in plan["batches"]] == ["dov-2", "dov-3"]
    assert plan["batches"][0]["incrementalSelection"] == {
        "selectionMode": "changed_slices",
        "selectedDataObjectVersionIds": ["dov-2", "dov-3"],
    }


def test_build_plan_rejects_incremental_targets_outside_scope(planner: GroupedExecutionPlanner) -> None:
    with pytest.raises(GroupedExecutionPlanError) as error:
        asyncio.run(
            planner.build_plan(
                [
                    _incremental_suite_envelope(
                        suite_id="suite-inc-missing",
                        suite_version=1,
                        target_ids=["dov-1"],
                        marker="inc-missing",
                        selection_mode="new_partitions",
                        selected_target_ids=["dov-9"],
                    )
                ]
            )
        )

    assert "outside its resolved execution scope" in str(error.value)


def test_build_plan_rejects_empty_target_list(planner: GroupedExecutionPlanner) -> None:
    with pytest.raises(GroupedExecutionPlanError) as error:
        asyncio.run(planner.build_plan([_suite_envelope(suite_id="suite-f", suite_version=1, target_ids=[], marker="f")]))

    assert "does not define any dataObjectVersionId targets" in str(error.value)


def test_build_plan_returns_empty_plan_for_empty_input(planner: GroupedExecutionPlanner) -> None:
    plan = asyncio.run(planner.build_plan([]))

    assert plan == {"suiteCount": 0, "batchCount": 0, "batches": []}


def test_build_plan_rejects_schema_level_empty_target_list(planner: GroupedExecutionPlanner) -> None:
    envelope = _suite_envelope(suite_id="suite-g", suite_version=1, target_ids=["dov-1"], marker="g")
    envelope["resolvedExecutionScope"] = {"dataObjectVersionIds": []}

    with pytest.raises(GroupedExecutionPlanError) as error:
        asyncio.run(planner.build_plan([envelope]))

    assert str(error.value) == "GROUPED_EXECUTION suite does not define any dataObjectVersionId targets"
    assert error.value.status_code == 400


def test_build_plan_rejects_other_invalid_suite_envelopes(planner: GroupedExecutionPlanner) -> None:
    envelope = _suite_envelope(suite_id="suite-h", suite_version=1, target_ids=["dov-1"], marker="h")
    envelope["suiteVersion"] = 0

    with pytest.raises(GroupedExecutionPlanError) as error:
        asyncio.run(planner.build_plan([envelope]))

    assert str(error.value) == "GROUPED_EXECUTION suite envelope is invalid"
    assert error.value.status_code == 400


def test_build_plan_rejects_blank_target_ids_after_normalization(planner: GroupedExecutionPlanner) -> None:
    with pytest.raises(GroupedExecutionPlanError) as error:
        asyncio.run(
            planner.build_plan(
                [_suite_envelope(suite_id="suite-i", suite_version=1, target_ids=["", "   "], marker="i")]
            )
        )

    assert str(error.value) == "GROUPED_EXECUTION suite 'suite-i' does not define any dataObjectVersionId targets"
    assert error.value.status_code == 400