import asyncio
from typing import Any

import pytest

from app.application.services.pyspark_executor import PysparkExecutionDependencyError
from app.application.services.pyspark_executor import PysparkExecutionExecutor
from app.domain.entities import ValidationArtifactAssignmentScopeEntity
from app.domain.entities import ValidationArtifactCompiledFromEntity
from app.domain.entities import ValidationArtifactEngineArtifactEntity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import ValidationArtifactExecutionHintsEntity
from app.domain.entities import ValidationArtifactResolvedExecutionScopeEntity
from app.domain.entities import ValidationArtifactRunPlanningEntity
from app.domain.entities import ValidationArtifactRunPlanningTraceabilityEntity
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact


class _FakeSparkSession:
    def __init__(self, app_name: str) -> None:
        self.app_name = app_name
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


class _FakeSourceAdapter:
    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self._calls = calls

    def supports_execution_shape(self, execution_shape: str) -> bool:
        self._calls.append({"method": "supports_execution_shape", "executionShape": execution_shape})
        return execution_shape in {"single_object", "join_pair"}

    def resolve_asset(
        self,
        *,
        spark_session: Any,
        suite: Any,
        data_object_version_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        self._calls.append(
            {
                "method": "resolve_asset",
                "suiteId": suite.suiteId,
                "dataObjectVersionId": data_object_version_id,
                "correlationId": correlation_id,
                "sparkSessionAppName": getattr(spark_session, "app_name", None),
            }
        )
        return {
            "suite_id": suite.suiteId,
            "suite_version": suite.suiteVersion,
            "execution_shape": str(suite.executionContract.executionShape),
            "data_object_version_id": data_object_version_id,
            "source_ref": f"resolved-{data_object_version_id}",
            "correlation_id": correlation_id,
        }

    def load_dataframe(self, *, spark_session: Any, asset_ref: Any) -> dict[str, Any]:
        self._calls.append(
            {
                "method": "load_dataframe",
                "sourceRef": asset_ref["source_ref"],
                "sparkSessionAppName": getattr(spark_session, "app_name", None),
            }
        )
        return {"source_ref": asset_ref["source_ref"], "asset_ref": dict(asset_ref)}

    def materialize_primary_key(self, dataframe: Any, primary_key_config: list[str]) -> Any:
        self._calls.append({"method": "materialize_primary_key", "primaryKeyFields": list(primary_key_config)})
        return dataframe

    def emit_validation_target(self, dataframe: Any, gx_context: dict[str, Any]) -> Any:
        self._calls.append({"method": "emit_validation_target", "gxContext": dict(gx_context)})
        return dataframe


@pytest.fixture()
def spark_session() -> _FakeSparkSession:
    return _FakeSparkSession(app_name="dq-made-easy")


@pytest.fixture()
def source_loader_calls() -> list[str]:
    return []


@pytest.fixture()
def materialized_source_loader_calls() -> list[str]:
    return []


@pytest.fixture()
def validation_runner_calls() -> list[dict[str, Any]]:
    return []


@pytest.fixture()
def validation_runner(validation_runner_calls: list[dict[str, Any]]):
    def _runner(spark_session: Any, source_handle: Any, suite: Any, correlation_id: str) -> dict[str, Any]:
        validation_runner_calls.append(
            {
                "sparkSessionAppName": getattr(spark_session, "app_name", None),
                "sourceRef": source_handle["source_ref"],
                "suiteId": suite.suiteId,
                "correlationId": correlation_id,
            }
        )
        return {
            "status": "succeeded",
            "passed": True,
            "result": {
                "sourceRef": source_handle["source_ref"],
                "suiteId": suite.suiteId,
                "suiteVersion": suite.suiteVersion,
            },
            "diagnostics": [],
        }

    return _runner


def _suite(
    *,
    suite_id: str,
    suite_version: int,
    target_id: str,
    execution_shape: str = "single_object",
    output_location: str | None = None,
    target_ids: list[str] | None = None,
    incremental_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_target_ids = list(target_ids or [target_id])
    execution_contract: dict[str, Any] = {
        "engineTarget": "pyspark",
        "executionShape": execution_shape,
        "traceability": {
            "ruleId": f"rule-{suite_id}",
            "ruleVersionId": f"rv-{suite_id}",
            "gxSuiteId": suite_id,
            "gxSuiteVersion": suite_version,
            "dataObjectVersionId": resolved_target_ids[0],
        },
    }
    if execution_shape == "join_pair":
        execution_contract["sourceMaterialization"] = {
            "landingZoneArtifactId": f"lz-{suite_id}",
            "landingZoneVersionId": target_id,
            "outputLocation": output_location or f"s3://dq-landing-zone/{suite_id}",
            "joinType": "inner",
            "joinKeys": ["customer_id"],
            "leftSource": {
                "dataObjectId": "do-left",
                "dataObjectVersionId": "dov-left",
                "datasetId": "ds-left",
                "dataProductId": "odcs.dp.left-001",
            },
            "rightSource": {
                "dataObjectId": "do-right",
                "dataObjectVersionId": "dov-right",
                "datasetId": "ds-right",
                "dataProductId": "odcs.dp.right-001",
            },
        }

    return {
        "suiteId": suite_id,
        "suiteVersion": suite_version,
        "artifactVersion": "v1",
        "assignmentScope": {"dataObjectId": "do-1", "datasetId": "ds-1", "dataProductId": "odcs.dp.sales-001"},
        "resolvedExecutionScope": {"dataObjectVersionIds": resolved_target_ids},
        "gxSuite": {"expectation_suite_name": suite_id, "expectations": [], "meta": {"source": "dq-made-easy"}},
        "compiledFrom": {"ruleIds": [f"rule-{suite_id}"], "compilerVersion": "dq-compiler-7.3", "generatedAt": "2026-04-06T00:00:00Z"},
        "executionHints": {
            "recommendedEngine": "pyspark",
            "primaryKeyFields": ["id"],
            "incrementalSelection": incremental_selection,
        },
        "executionContract": execution_contract,
    }


def _pyspark_native_suite(
    *,
    suite_id: str,
    suite_version: int,
    target_id: str,
) -> ValidationArtifactEnvelopeEntity:
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
        resolvedExecutionScope=ValidationArtifactResolvedExecutionScopeEntity(dataObjectVersionIds=[target_id]),
        compiledFrom=ValidationArtifactCompiledFromEntity(
            ruleIds=[f"rule-{suite_id}"],
            compilerVersion="dq-compiler-7.3",
            generatedAt="2026-04-26T00:00:00Z",
        ),
        executionHints=ValidationArtifactExecutionHintsEntity(
            recommendedEngineTarget="pyspark",
            primaryKeyFields=["id"],
            businessKeyFields=["business_id"],
            supportedExecutionShapes=["single_object"],
        ),
        runPlanning=ValidationArtifactRunPlanningEntity(
            engineTarget="pyspark",
            executionShape="single_object",
            groupingKey="data_object_version_id",
            groupingValues=[target_id],
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
                "assignment_scope": {"data_object_id": "do-1", "dataset_id": "ds-1", "data_product_id": "odcs.dp.sales-001"},
                "resolved_execution_scope": {"data_object_version_ids": [target_id]},
                "compiled_from": {
                    "rule_ids": [f"rule-{suite_id}"],
                    "compiler_version": "dq-compiler-7.3",
                    "generated_at": "2026-04-26T00:00:00Z",
                },
                "execution_hints": {
                    "primary_key_fields": ["id"],
                    "business_key_fields": ["business_id"],
                    "supported_execution_shapes": ["single_object"],
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


def test_execute_suites_groups_single_object_batches_and_reuses_one_source_load(
    spark_session: _FakeSparkSession,
    source_loader_calls: list[str],
    validation_runner_calls: list[dict[str, Any]],
    validation_runner,
) -> None:
    def source_loader(_spark_session: Any, source_ref: str) -> dict[str, Any]:
        source_loader_calls.append(source_ref)
        return {"source_ref": source_ref}

    executor = PysparkExecutionExecutor(
        source_loader=source_loader,
        validation_runner=validation_runner,
        spark_session_factory=lambda: spark_session,
        manage_spark_session=True,
    )

    result = asyncio.run(
        executor.execute_suites(
            [
                _suite(suite_id="suite-a", suite_version=1, target_id="dov-1"),
                _suite(suite_id="suite-b", suite_version=2, target_id="dov-1"),
            ],
            correlation_id="corr-123",
        )
    )

    assert result.correlationId == "corr-123"
    assert result.engineTarget == "pyspark"
    assert result.status == "succeeded"
    assert result.batchCount == 1
    assert result.suiteCount == 2
    assert source_loader_calls == ["dov-1"]
    assert len(validation_runner_calls) == 2
    assert validation_runner_calls[0]["sparkSessionAppName"] == "dq-made-easy"
    assert result.batchResults[0].dataObjectVersionId == "dov-1"
    assert result.batchResults[0].suiteResults[0].result["sourceRef"] == "dov-1"
    assert spark_session.stop_calls == 1


def test_execute_suites_uses_materialized_source_loader_for_join_pair(
    spark_session: _FakeSparkSession,
    materialized_source_loader_calls: list[str],
    validation_runner,
) -> None:
    def source_loader(_spark_session: Any, source_ref: str) -> dict[str, Any]:
        raise AssertionError(f"unexpected single-object source load: {source_ref}")

    def materialized_source_loader(_spark_session: Any, output_location: str) -> dict[str, Any]:
        materialized_source_loader_calls.append(output_location)
        return {"source_ref": output_location}

    executor = PysparkExecutionExecutor(
        source_loader=source_loader,
        materialized_source_loader=materialized_source_loader,
        validation_runner=validation_runner,
        spark_session_factory=lambda: spark_session,
        manage_spark_session=True,
    )

    result = asyncio.run(
        executor.execute_suites([
            _suite(
                suite_id="suite-join",
                suite_version=1,
                target_id="lzv-join-1",
                execution_shape="join_pair",
                output_location="s3://dq-landing-zone/joined/1",
            )
        ])
    )

    assert result.status == "succeeded"
    assert materialized_source_loader_calls == ["s3://dq-landing-zone/joined/1"]
    assert result.batchResults[0].suiteResults[0].result["sourceRef"] == "s3://dq-landing-zone/joined/1"
    assert spark_session.stop_calls == 1


def test_execute_suites_uses_source_loader_for_streaming_shape(
    spark_session: _FakeSparkSession,
    source_loader_calls: list[str],
    validation_runner_calls: list[dict[str, Any]],
    validation_runner,
) -> None:
    def source_loader(_spark_session: Any, source_ref: str) -> dict[str, Any]:
        source_loader_calls.append(source_ref)
        return {"source_ref": source_ref}

    executor = PysparkExecutionExecutor(
        source_loader=source_loader,
        validation_runner=validation_runner,
        spark_session_factory=lambda: spark_session,
        manage_spark_session=True,
    )

    result = asyncio.run(
        executor.execute_suites([
            _suite(
                suite_id="suite-streaming",
                suite_version=1,
                target_id="dov-stream",
                execution_shape="streaming",
            )
        ])
    )

    assert result.status == "succeeded"
    assert source_loader_calls == ["dov-stream"]
    assert validation_runner_calls[0]["suiteId"] == "suite-streaming"
    assert result.batchResults[0].suiteResults[0].result["sourceRef"] == "dov-stream"
    assert spark_session.stop_calls == 1


def test_execute_suites_uses_source_loader_for_micro_batch_shape(
    spark_session: _FakeSparkSession,
    source_loader_calls: list[str],
    validation_runner_calls: list[dict[str, Any]],
    validation_runner,
) -> None:
    def source_loader(_spark_session: Any, source_ref: str) -> dict[str, Any]:
        source_loader_calls.append(source_ref)
        return {"source_ref": source_ref}

    executor = PysparkExecutionExecutor(
        source_loader=source_loader,
        validation_runner=validation_runner,
        spark_session_factory=lambda: spark_session,
        manage_spark_session=True,
    )

    result = asyncio.run(
        executor.execute_suites([
            _suite(
                suite_id="suite-micro-batch",
                suite_version=1,
                target_id="dov-micro",
                execution_shape="micro_batch",
            )
        ])
    )

    assert result.status == "succeeded"
    assert source_loader_calls == ["dov-micro"]
    assert validation_runner_calls[0]["suiteId"] == "suite-micro-batch"
    assert result.batchResults[0].suiteResults[0].result["sourceRef"] == "dov-micro"
    assert spark_session.stop_calls == 1


def test_execute_suites_uses_source_adapter_when_configured(
    spark_session: _FakeSparkSession,
    validation_runner,
) -> None:
    adapter_calls: list[dict[str, Any]] = []
    source_adapter = _FakeSourceAdapter(adapter_calls)

    executor = PysparkExecutionExecutor(
        source_adapter=source_adapter,
        validation_runner=validation_runner,
        spark_session_factory=lambda: spark_session,
        manage_spark_session=True,
    )

    result = asyncio.run(
        executor.execute_suites(
            [_suite(suite_id="suite-adapter", suite_version=1, target_id="dov-adapter-1")],
            correlation_id="corr-adapter",
        )
    )

    assert result.status == "succeeded"
    assert [call["method"] for call in adapter_calls] == [
        "supports_execution_shape",
        "resolve_asset",
        "load_dataframe",
        "materialize_primary_key",
        "emit_validation_target",
    ]
    assert result.batchResults[0].suiteResults[0].result["sourceRef"] == "resolved-dov-adapter-1"
    assert spark_session.stop_calls == 1


def test_execute_suites_limits_incremental_targets_to_selected_batches(
    spark_session: _FakeSparkSession,
    source_loader_calls: list[str],
    validation_runner_calls: list[dict[str, Any]],
    validation_runner,
) -> None:
    def source_loader(_spark_session: Any, source_ref: str) -> dict[str, Any]:
        source_loader_calls.append(source_ref)
        scan_metrics = {"dov-2": {"rows_scanned": 128, "bytes_scanned": 4096}, "dov-3": {"rows_scanned": 64, "bytes_scanned": 2048}}
        return {"source_ref": source_ref, "scan_metrics": scan_metrics.get(source_ref)}

    executor = PysparkExecutionExecutor(
        source_loader=source_loader,
        validation_runner=validation_runner,
        spark_session_factory=lambda: spark_session,
        manage_spark_session=True,
    )

    result = asyncio.run(
        executor.execute_suites(
            [
                _suite(
                    suite_id="suite-incremental",
                    suite_version=1,
                    target_id="dov-1",
                    target_ids=["dov-1", "dov-2"],
                    incremental_selection={
                        "selectionMode": "new_partitions",
                        "selectedDataObjectVersionIds": ["dov-2"],
                    },
                ),
                _suite(suite_id="suite-full", suite_version=1, target_id="dov-3"),
            ],
            correlation_id="corr-incremental",
        )
    )

    assert result.batchCount == 2
    assert source_loader_calls == ["dov-2", "dov-3"]
    assert validation_runner_calls[0]["correlationId"] == "corr-incremental"
    assert result.batchResults[0].incrementalSelection == {
        "selectionMode": "new_partitions",
        "selectedDataObjectVersionIds": ["dov-2"],
    }
    assert result.batchResults[0].suiteResults[0].result["sourceRef"] == "dov-2"
    assert result.batchResults[0].performanceSummary is not None
    assert result.batchResults[0].performanceSummary.plannerChoice == "incremental_scope"
    assert result.batchResults[0].performanceSummary.executionPath == "incremental_grouped_execution"
    assert result.batchResults[0].performanceSummary.dataScannedRows == 128
    assert result.batchResults[0].performanceSummary.dataScannedBytes == 4096
    assert result.performanceSummary is not None
    assert result.performanceSummary.plannerChoice == "mixed_scope"
    assert result.performanceSummary.executionPath == "mixed_grouped_execution"
    assert result.performanceSummary.dataScannedRows == 192
    assert result.performanceSummary.dataScannedBytes == 6144
    assert spark_session.stop_calls == 2


def test_execute_plan_accepts_validation_artifact_batch_payload(
    spark_session: _FakeSparkSession,
    source_loader_calls: list[str],
    validation_runner_calls: list[dict[str, Any]],
    validation_runner,
) -> None:
    def source_loader(_spark_session: Any, source_ref: str) -> dict[str, Any]:
        source_loader_calls.append(source_ref)
        return {"source_ref": source_ref}

    executor = PysparkExecutionExecutor(
        source_loader=source_loader,
        validation_runner=validation_runner,
        spark_session_factory=lambda: spark_session,
        manage_spark_session=True,
    )

    suite = build_validation_artifact_envelope_from_gx_artifact(
        _suite(suite_id="suite-neutral", suite_version=1, target_id="dov-neutral-1")
    )
    result = asyncio.run(
        executor.execute_plan(
            {
                "suiteCount": 1,
                "batchCount": 1,
                "batches": [
                    {
                        "dataObjectVersionId": "dov-neutral-1",
                        "suites": [suite.model_dump(mode="python", by_alias=False, exclude_none=False)],
                    }
                ],
            },
            correlation_id="corr-neutral-batch",
        )
    )

    assert result.status == "succeeded"
    assert source_loader_calls == ["dov-neutral-1"]
    assert validation_runner_calls[0]["suiteId"] == "suite-neutral"
    assert result.batchResults[0].suiteResults[0].result["suiteId"] == "suite-neutral"
    assert spark_session.stop_calls == 1


def test_execute_plan_accepts_pyspark_native_validation_artifact_batch_payload(
    spark_session: _FakeSparkSession,
    source_loader_calls: list[str],
    validation_runner_calls: list[dict[str, Any]],
    validation_runner,
) -> None:
    def source_loader(_spark_session: Any, source_ref: str) -> dict[str, Any]:
        source_loader_calls.append(source_ref)
        return {"source_ref": source_ref}

    executor = PysparkExecutionExecutor(
        source_loader=source_loader,
        validation_runner=validation_runner,
        spark_session_factory=lambda: spark_session,
        manage_spark_session=True,
    )

    suite = _pyspark_native_suite(suite_id="suite-native", suite_version=1, target_id="dov-native-1")
    result = asyncio.run(
        executor.execute_plan(
            {
                "suiteCount": 1,
                "batchCount": 1,
                "batches": [
                    {
                        "dataObjectVersionId": "dov-native-1",
                        "suites": [suite.model_dump(mode="python", by_alias=False, exclude_none=False)],
                    }
                ],
            },
            correlation_id="corr-native-batch",
        )
    )

    assert result.status == "succeeded"
    assert source_loader_calls == ["dov-native-1"]
    assert validation_runner_calls[0]["suiteId"] == "suite-native"
    assert result.batchResults[0].suiteResults[0].result["suiteId"] == "suite-native"
    assert spark_session.stop_calls == 1


def test_execute_suites_creates_one_spark_session_per_group(
    validation_runner,
) -> None:
    sessions = [_FakeSparkSession(app_name="dq-made-easy-1"), _FakeSparkSession(app_name="dq-made-easy-2")]
    session_calls: list[str] = []
    created_sessions: list[_FakeSparkSession] = []

    def spark_session_factory() -> _FakeSparkSession:
        if not sessions:
            raise AssertionError("unexpected extra Spark session request")
        session = sessions.pop(0)
        session_calls.append(session.app_name)
        created_sessions.append(session)
        return session

    def source_loader(_spark_session: Any, source_ref: str) -> dict[str, Any]:
        return {"source_ref": source_ref}

    executor = PysparkExecutionExecutor(
        source_loader=source_loader,
        validation_runner=validation_runner,
        spark_session_factory=spark_session_factory,
        manage_spark_session=True,
    )

    result = asyncio.run(
        executor.execute_suites(
            [
                _suite(suite_id="suite-batch-1", suite_version=1, target_id="dov-batch-1"),
                _suite(suite_id="suite-batch-2", suite_version=1, target_id="dov-batch-2"),
            ],
            correlation_id="corr-batches",
        )
    )

    assert result.batchCount == 2
    assert session_calls == ["dq-made-easy-1", "dq-made-easy-2"]
    assert [session.stop_calls for session in created_sessions] == [1, 1]


def test_execute_suites_fails_fast_without_source_loader_for_single_object(
    spark_session: _FakeSparkSession,
    validation_runner,
) -> None:
    executor = PysparkExecutionExecutor(
        validation_runner=validation_runner,
        spark_session_factory=lambda: spark_session,
        manage_spark_session=True,
    )

    with pytest.raises(PysparkExecutionDependencyError) as error:
        asyncio.run(executor.execute_suites([_suite(suite_id="suite-missing-loader", suite_version=1, target_id="dov-1")]))

    assert "source_loader" in str(error.value)
    assert spark_session.stop_calls == 0


def test_execute_suites_fails_fast_without_validation_runner(
    spark_session: _FakeSparkSession,
) -> None:
    def source_loader(_spark_session: Any, source_ref: str) -> dict[str, Any]:
        return {"source_ref": source_ref}

    executor = PysparkExecutionExecutor(
        source_loader=source_loader,
        spark_session_factory=lambda: spark_session,
        manage_spark_session=True,
    )

    with pytest.raises(PysparkExecutionDependencyError) as error:
        asyncio.run(executor.execute_suites([_suite(suite_id="suite-no-runner", suite_version=1, target_id="dov-1")]))

    assert "validation_runner" in str(error.value)
    assert spark_session.stop_calls == 0