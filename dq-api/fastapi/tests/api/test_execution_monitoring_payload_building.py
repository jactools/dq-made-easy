from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from app.api.presenters.gx import build_gx_suite_entity
from app.api.presenters.gx import build_gx_suite_expectation_entity
from app.api.v1 import gx_report_api
from app.api.v1 import gx_runtime_api
from app.api.v1 import gx_run_plan_api
from app.api.v1 import gx_start_api
from app.api.v1 import gx_suite_api
from app.api.v1.schemas.gx_artifact_view import GxArtifactEnvelopeView
from app.api.v1.schemas.gx_artifact_view import GxSuiteRetrievalQueryView
from app.api.presenters.gx import extract_itsm_ticket_number
from app.api.presenters.gx import build_itsm_response_entity
from app.api.v1.endpoints import execution_monitoring as gx_endpoints
from app.application.services.exception_fact_collection import extract_exception_fact_target_ids
from app.domain.entities.gx_execution_run import build_gx_dispatch_payload_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_list_query_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_summary_entity
from app.domain.entities.gx_execution_run import build_gx_grouped_execution_plan_entity
from app.domain.entities.gx_execution_run import build_gx_structured_error_detail_entity
from app.domain.entities.gx_run_plan import build_gx_run_plan_grouped_suite_snapshot_entity
from app.domain.entities.gx_run_plan import build_gx_run_plan_suite_selection_entity


class DummyExecutionContract:
    def __init__(self, engine_target: str, execution_shape: str) -> None:
        self.engineType = "gx"
        self.engineTarget = engine_target
        self.executionShape = execution_shape
        self.traceability = SimpleNamespace(ruleId="rule-1", ruleVersionId="rule-v1")

    def model_dump(self) -> dict[str, object]:
        return {"engineType": self.engineType, "engineTarget": self.engineTarget, "executionShape": self.executionShape}


class DummySuite:
    def __init__(self, suite_id: str, execution_contract: object, resolved_execution_scope: object, gx_suite: object | None = None) -> None:
        self.suiteId = suite_id
        self.suiteVersion = 1
        self.executionContract = execution_contract
        self.resolvedExecutionScope = resolved_execution_scope
        self.gxSuite = gx_suite if gx_suite is not None else {
            "expectations": [{"expectation_type": "exists", "kwargs": {"field": "id"}}]
        }


class DummyDeliveryRepo:
    def __init__(self, deliveries: list[SimpleNamespace]) -> None:
        self._deliveries = deliveries

    def list_data_deliveries(self, version_id: str | None = None) -> list[SimpleNamespace]:
        if version_id is None:
            return list(self._deliveries)
        return [delivery for delivery in self._deliveries if str(delivery.data_object_version_id or "") == str(version_id)]


def test_assert_gx_suite_runnable_rejects_invalid_suites() -> None:
    suite = DummySuite(
        suite_id="gx_suite_1",
        execution_contract=None,
        resolved_execution_scope=SimpleNamespace(dataObjectVersionIds=["dov-1"]),
        gx_suite={"expectations": [{"expectation_type": "exists", "kwargs": {"field": "id"}}]},
    )
    with pytest.raises(HTTPException) as exc:
        gx_start_api._assert_suite_runnable(suite)
    assert exc.value.status_code == 422
    assert exc.value.detail["reason"] == "missing_execution_contract"

    suite.executionContract = SimpleNamespace(engineTarget="dq-engine", executionShape="small")
    suite.resolvedExecutionScope = SimpleNamespace(dataObjectVersionIds=[])
    with pytest.raises(HTTPException) as exc2:
        gx_start_api._assert_suite_runnable(suite)
    assert exc2.value.detail["reason"] == "missing_targets"

    suite.resolvedExecutionScope = SimpleNamespace(dataObjectVersionIds=["dov-1"])
    suite.gxSuite = None
    with pytest.raises(HTTPException) as exc3:
        gx_start_api._assert_suite_runnable(suite)
    assert exc3.value.detail["reason"] == "missing_gx_suite"

    suite.gxSuite = {"expectations": []}
    with pytest.raises(HTTPException) as exc4:
        gx_start_api._assert_suite_runnable(suite)
    assert exc4.value.detail["reason"] == "empty_expectations"


def test_assert_gx_suite_runnable_rejects_invalid_expectations() -> None:
    suite = DummySuite(
        suite_id="gx_suite_1",
        execution_contract=DummyExecutionContract("dq-engine", "small"),
        resolved_execution_scope=SimpleNamespace(dataObjectVersionIds=["dov-1"]),
        gx_suite={"expectations": [None]},
    )
    with pytest.raises(HTTPException) as missing_expectation:
        gx_start_api._assert_suite_runnable(suite)
    assert missing_expectation.value.detail["reason"] == "empty_expectations"

    suite.gxSuite = {"expectations": [{"kwargs": {"column": "order_id"}}]}
    with pytest.raises(HTTPException) as missing_expectation_type:
        gx_start_api._assert_suite_runnable(suite)
    assert missing_expectation_type.value.detail["reason"] == "invalid_expectation"

    suite.gxSuite = {"expectations": [{"expectation_type": "expect_column_values_to_not_be_null", "kwargs": {}}]}
    with pytest.raises(HTTPException) as missing_kwargs:
        gx_start_api._assert_suite_runnable(suite)
    assert missing_kwargs.value.detail["reason"] == "invalid_expectation"


def test_build_suite_run_handoff_payload_and_http400(monkeypatch) -> None:
    suite = DummySuite(
        suite_id="gx_suite_1",
        execution_contract=DummyExecutionContract("dq-engine", "small"),
        resolved_execution_scope=SimpleNamespace(dataObjectVersionIds=["dov-1"]),
    )

    payload = gx_start_api.build_suite_run_handoff_payload(
        suite=suite,
        correlation_id="corr-1",
        requested_by="user-1",
        data_catalog_repository=DummyDeliveryRepo(
            [
                SimpleNamespace(
                    id="del-1",
                    data_object_version_id="dov-1",
                    delivery_location="s3a://bucket/do-1/v1/LOAD_DTS=20260412T101500000Z",
                )
            ]
        ),
    )
    assert payload["handoff_status"] == "accepted"
    assert payload["engine_type"] == "gx"
    assert payload["execution_contract"]["engine_target"] == "dq-engine"
    assert payload["execution_contract"]["resolved_data_object_version_id"] == "dov-1"
    assert payload["execution_contract"]["resolved_data_delivery_id"] == "del-1"
    assert payload["execution_contract"]["delivery_resolution_mode"] == "latest_delivery"
    assert payload["correlation_id"] == "corr-1"

    class SampleSchema(BaseModel):
        value: int

    with pytest.raises(ValidationError) as exc:
        SampleSchema(value="bad")

    converted = gx_suite_api._as_http_400(exc.value)
    assert converted.status_code == 400
    assert converted.detail["message"] == "Invalid GX retrieval query"


def test_as_http_400_makes_query_validation_errors_json_safe() -> None:
    with pytest.raises(ValidationError) as exc:
        GxSuiteRetrievalQueryView()

    converted = gx_suite_api._as_http_400(exc.value)

    assert converted.status_code == 400
    assert converted.detail["message"] == "Invalid GX retrieval query"
    assert converted.detail["errors"][0]["msg"] == (
        "Value error, Exactly one primary scope filter is required: "
        "dataObjectId, dataObjectVersionId, datasetId, or dataProductId"
    )
    json.dumps(converted.detail)


def test_gx_artifact_envelope_accepts_uuid_data_product_id() -> None:
    envelope = GxArtifactEnvelopeView.model_validate(
        {
            "suiteId": "gx-suite-uuid",
            "suiteVersion": 1,
            "artifactVersion": "v1",
            "assignmentScope": {
                "dataObjectId": "data-object-1",
                "datasetId": None,
                "dataProductId": "019e0488-9a53-785b-990e-2f4738a0f9eb",
            },
            "resolvedExecutionScope": {
                "dataObjectVersionIds": ["dov-1"],
            },
            "gxSuite": {"expectations": []},
            "compiledFrom": {
                "ruleIds": ["rule-1"],
                "compilerVersion": "1.0.0",
                "generatedAt": "2026-05-10T00:00:00Z",
            },
            "executionHints": {
                "recommendedEngine": "pyspark",
                "primaryKeyFields": [],
                "businessKeyFields": [],
            },
        }
    )

    assert envelope.assignmentScope.dataProductId == "019e0488-9a53-785b-990e-2f4738a0f9eb"


def test_resolve_gx_execution_queue_keys_and_worker_heartbeat(monkeypatch) -> None:
    monkeypatch.setenv("GX_EXECUTION_QUEUE_KEY", "dq-gx:execution-dispatch")
    monkeypatch.setenv("GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY", "dq-gx:join-pair-materialize")
    assert gx_runtime_api.resolve_execution_queue_key() == "dq-gx:execution-dispatch"
    assert gx_runtime_api.resolve_join_pair_materialization_queue_key() == "dq-gx:join-pair-materialize"
    assert gx_runtime_api.resolve_execution_worker_heartbeat_key("queue") == "queue:worker-heartbeat"
    assert gx_runtime_api.resolve_execution_worker_heartbeat_ttl_seconds() >= 1

    monkeypatch.delenv("GX_EXECUTION_QUEUE_KEY", raising=False)
    monkeypatch.delenv("DQ_GX_EXECUTION_QUEUE_KEY", raising=False)
    with pytest.raises(HTTPException) as execution_error:
        gx_runtime_api.resolve_execution_queue_key()
    assert execution_error.value.status_code == 503

    monkeypatch.delenv("GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY", raising=False)
    monkeypatch.delenv("DQ_GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY", raising=False)
    with pytest.raises(HTTPException) as join_pair_error:
        gx_runtime_api.resolve_join_pair_materialization_queue_key()
    assert join_pair_error.value.status_code == 503


def test_build_gx_execution_dispatch_payload_and_overrides(monkeypatch) -> None:
    suite = DummySuite(
        suite_id="gx_suite_1",
        execution_contract=DummyExecutionContract("dq-engine", "small"),
        resolved_execution_scope=SimpleNamespace(dataObjectVersionIds=["dov-1"]),
    )
    payload = gx_runtime_api.build_execution_dispatch_payload(
        suite=suite,
        correlation_id="corr-1",
        requested_by="user-1",
        scheduled_at=datetime.now(UTC),
        run_plan_id="run-plan-1",
        run_plan_version_id="run-plan-version-1",
        execution_scope_override=["dov-1"],
        source_overrides_by_data_object_version_id={"dov-1": {"uri": "s3://x", "format": "parquet"}},
        queue_key="dq-gx:execution-dispatch",
        data_catalog_repository=DummyDeliveryRepo(
            [
                SimpleNamespace(
                    id="del-1",
                    data_object_version_id="dov-1",
                    delivery_location="s3a://bucket/do-1/v1/LOAD_DTS=20260412T101500000Z",
                )
            ]
        ),
    )
    assert payload["suite_id"] == "gx_suite_1"
    assert payload["execution_scope_override"] == ["dov-1"]
    assert payload["run_plan_id"] == "run-plan-1"
    assert payload["run_plan_version_id"] == "run-plan-version-1"
    assert payload["source_overrides_by_data_object_version_id"]["dov-1"]["uri"] == "s3://x"
    assert payload["execution_contract"]["resolved_data_object_version_id"] == "dov-1"
    assert payload["execution_contract"]["resolved_data_delivery_id"] == "del-1"
    assert payload["execution_contract"]["resolved_delivery_location"] == "s3a://bucket/do-1/v1/LOAD_DTS=20260412T101500000Z"
    assert payload["execution_contract"]["delivery_resolution_mode"] == "latest_delivery"


def test_build_gx_execution_dispatch_payload_fails_when_delivery_missing() -> None:
    suite = DummySuite(
        suite_id="gx_suite_1",
        execution_contract=DummyExecutionContract("dq-engine", "small"),
        resolved_execution_scope=SimpleNamespace(dataObjectVersionIds=["dov-1"]),
    )
    with pytest.raises(HTTPException) as exc:
        gx_runtime_api.build_execution_dispatch_payload(
            suite=suite,
            correlation_id="corr-1",
            requested_by="user-1",
            scheduled_at=datetime.now(UTC),
            queue_key="dq-gx:execution-dispatch",
            data_catalog_repository=DummyDeliveryRepo([]),
        )

    assert exc.value.status_code == 422
    assert exc.value.detail["error"] == "missing_data_delivery"


def test_build_grouped_gx_execution_dispatch_payload() -> None:
    result = gx_runtime_api.build_grouped_execution_dispatch_payload(
        grouped_execution_plan={"suite_count": 1},
        scope_selector={"dataObjectVersionIds": ["dov-1"]},
        suite_refs=[{"suiteId": "gx_suite_1", "engineType": "gx"}],
        correlation_id="corr-2",
        requested_by="user-2",
        scheduled_at=datetime.now(UTC),
        run_plan_id="run-plan-2",
        run_plan_version_id="run-plan-version-2",
        queue_key="dq-gx:execution-dispatch",
        delivery_snapshot={
            "engineType": "gx",
            "resolvedDataObjectVersionId": "dov-1",
            "resolvedDataDeliveryId": "del-1",
            "resolvedDeliveryLocation": "s3a://bucket/do-1/v1/LOAD_DTS=20260412T101500000Z",
            "deliveryResolutionMode": "latest_delivery",
        },
    )
    assert result["dispatch_mode"] == "queued"
    assert result["engine_type"] == "gx"
    assert result["engine_target"] == "pyspark"
    assert result["run_plan_id"] == "run-plan-2"
    assert result["run_plan_version_id"] == "run-plan-version-2"
    assert result["suite_refs"][0]["engine_type"] == "gx"
    assert result["suite_refs"][0]["suite_id"] == "gx_suite_1"
    assert result["delivery_snapshot"]["engine_type"] == "gx"
    assert result["delivery_snapshot"]["resolved_data_delivery_id"] == "del-1"


def test_build_grouped_scope_command_accepts_snake_case_and_artifact_ref_aliases() -> None:
    command = gx_runtime_api.build_grouped_scope_command(
        grouped_execution_plan={"suite_count": 2, "batch_count": 1},
        scope_selector={"dataObjectVersionId": "dov-1"},
        suite_refs=[
            {"suite_id": "gx_suite_1", "suite_version": 1, "engine_type": "gx"},
            {"artifact_id": "gx_suite_2", "artifact_version": 2, "engine_type": "gx"},
        ],
        scheduled_at=datetime.now(UTC),
        requested_by="user-2",
        correlation_id="corr-suite-refs",
        run_plan_id="run-plan-3",
        run_plan_version_id="run-plan-version-3",
        source_overrides_by_data_object_version_id=None,
        delivery_snapshot=None,
        queue_key="dq-gx:execution-dispatch",
    )

    assert command.suite_refs[0].suiteId == "gx_suite_1"
    assert command.suite_refs[0].suiteVersion == 1
    assert command.suite_refs[0].engineType == "gx"
    assert command.suite_refs[1].suiteId == "gx_suite_2"
    assert command.suite_refs[1].suiteVersion == 2
    assert command.suite_refs[1].engineType == "gx"
    assert command.run_plan_id == "run-plan-3"
    assert command.run_plan_version_id == "run-plan-version-3"


def test_build_dispatch_queue_payload_parses_execution_contract_traceability() -> None:
    payload = build_gx_dispatch_payload_entity(
        {
            "run_id": "run-1",
            "queue_message_id": "run-1",
            "engine_type": "gx",
            "queue_key": "dq-gx:execution-dispatch",
            "execution_contract": {
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "join_pair",
                "traceability": {
                    "rule_id": "rule-1",
                    "rule_version_id": "rule-v1",
                    "gx_suite_id": "gx-suite-1",
                    "gx_suite_version": 2,
                    "data_object_version_id": "dov-1",
                    "source_rule_expression": "status = 'ACTIVE'",
                    "compiled_expression": "status = 'ACTIVE'",
                    "artifact_key": "artifact-1",
                },
                "source_materialization": {
                    "landing_zone_artifact_id": "lz-1",
                    "left_source": {"data_object_id": "do-left", "data_object_version_id": "dov-left"},
                    "right_source": {"data_object_id": "do-right", "data_object_version_id": "dov-right"},
                },
            },
        }
    )

    assert payload is not None
    assert payload.executionContract is not None
    assert payload.executionContract.traceability is not None
    assert payload.executionContract.traceability.sourceRuleExpression == "status = 'ACTIVE'"
    assert payload.executionContract.traceability.artifactKey == "artifact-1"
    assert payload.executionContract.sourceMaterialization is not None
    assert payload.executionContract.sourceMaterialization.leftSource is not None
    assert payload.executionContract.sourceMaterialization.leftSource.dataObjectVersionId == "dov-left"


def test_build_execution_report_payloads_and_error_detail_accept_snake_case() -> None:
    result_summary = gx_report_api._build_execution_result_summary_payload(
        {
            "results": [
                {
                    "data_object_version_id": "dov-1",
                    "ok": False,
                    "violation_count": "4",
                }
            ],
            "failed_count": "4",
        }
    )
    result_items = gx_report_api._build_execution_result_items(result_summary)
    diagnostics = gx_report_api._build_execution_diagnostic_payloads(
        [
            {
                "data_object_version_id": "dov-1",
                "row_identifier": "order_id=42",
                "reason": "expectation_failed",
                "message": "Expectation failed",
            }
        ]
    )
    error_detail = build_gx_structured_error_detail_entity(
        {
            "reason": "queue_unavailable",
            "message": "Worker queue unavailable",
            "correlation_id": "corr-1",
            "queue_message_id": "msg-1",
        }
    )

    assert result_summary is not None
    assert result_summary.failedCount == "4"
    assert len(result_items) == 1
    assert result_items[0].dataObjectVersionId == "dov-1"
    assert result_items[0].violationCount == "4"
    assert len(diagnostics) == 1
    assert diagnostics[0].rowIdentifier == "order_id=42"
    assert error_detail is not None
    assert error_detail.correlationId == "corr-1"
    assert error_detail.queueMessageId == "msg-1"


def test_build_dispatch_queue_payload_parses_grouped_execution_plan() -> None:
    payload = build_gx_dispatch_payload_entity(
        {
            "run_id": "run-grouped-1",
            "queue_message_id": "run-grouped-1",
            "engine_type": "gx",
            "queue_key": "dq-gx:execution-dispatch",
            "execution_shape": "grouped_scope",
            "grouped_execution_plan": {
                "suite_count": 3,
                "batch_count": 2,
            },
        }
    )

    assert payload is not None
    assert payload.groupedExecutionPlan is not None
    assert payload.groupedExecutionPlan == build_gx_grouped_execution_plan_entity({"suite_count": 3, "batch_count": 2})


def test_build_dispatch_queue_payload_parses_next_dispatch_payload() -> None:
    payload = build_gx_dispatch_payload_entity(
        {
            "run_id": "run-join-1",
            "queue_message_id": "run-join-1",
            "engine_type": "gx",
            "queue_key": "dq-gx:join-pair-materialize",
            "next_dispatch_payload": {
                "run_id": "run-join-1",
                "queue_message_id": "run-join-1",
                "engine_type": "gx",
                "queue_key": "dq-gx:execution-dispatch",
                "execution_shape": "join_pair",
            },
        }
    )

    assert payload is not None
    assert payload.nextDispatchPayload is not None
    assert payload.nextDispatchPayload.queueKey == "dq-gx:execution-dispatch"


def test_build_gx_execution_run_entity_accepts_snake_case_and_artifact_aliases() -> None:
    payload = build_gx_execution_run_entity(
        {
            "id": "run-neutral-1",
            "artifact_id": "artifact-suite-1",
            "artifact_version": 4,
            "rule_id": "rule-1",
            "rule_version_id": "rule-v1",
            "correlation_id": "corr-run-1",
            "requested_by": "user-1",
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "grouped_scope",
            "status": "pending",
            "submitted_at": "2026-04-26T10:00:00Z",
            "created_at": "2026-04-26T10:00:00Z",
            "updated_at": "2026-04-26T10:01:00Z",
            "execution_contract": {
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "grouped_scope",
            },
            "handoff_payload": {
                "engine_type": "gx",
                "queue_key": "dq-gx:execution-dispatch",
                "queue_message_id": "run-neutral-1",
            },
            "execution_progress": {
                "percent": 20,
                "completed_steps": 1,
                "total_steps": 5,
                "updated_at": "2026-04-26T10:00:30Z",
            },
            "result_summary": {"results": []},
            "failure_code": "queued",
            "failure_message": "queued for worker",
            "status_history": [
                {
                    "id": "hist-1",
                    "run_id": "run-neutral-1",
                    "to_status": "pending",
                    "changed_at": "2026-04-26T10:00:00Z",
                    "details": {"source": "gx.run_plan.grouped.activate"},
                }
            ],
        }
    )

    assert payload.suiteId == "artifact-suite-1"
    assert payload.suiteVersion == 4
    assert payload.ruleId == "rule-1"
    assert payload.ruleVersionId == "rule-v1"
    assert payload.engineType == "gx"
    assert payload.executionProgress is not None
    assert payload.executionProgress.completedSteps == 1
    assert payload.executionProgress.totalSteps == 5
    assert payload.statusHistory[0].runId == "run-neutral-1"
    assert payload.statusHistory[0].toStatus == "pending"


def test_build_gx_execution_run_entity_rejects_missing_top_level_engine_type() -> None:
    with pytest.raises(ValueError, match="requires explicit engine_type"):
        build_gx_execution_run_entity(
            {
                "id": "run-legacy-1",
                "correlation_id": "corr-legacy-1",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "pending",
                "submitted_at": "2026-04-26T10:00:00Z",
                "created_at": "2026-04-26T10:00:00Z",
                "updated_at": "2026-04-26T10:00:00Z",
                "execution_contract": {
                    "engine_type": "gx",
                    "engine_target": "pyspark",
                    "execution_shape": "single_object",
                },
            }
        )


def test_build_gx_execution_run_summary_entity_accepts_snake_case_and_validation_aliases() -> None:
    payload = build_gx_execution_run_summary_entity(
        {
            "id": "run-summary-1",
            "validation_artifact_id": "artifact-suite-2",
            "validation_artifact_version": 7,
            "rule_id": "rule-2",
            "rule_name": "Grouped scope run",
            "data_object_version_id": "dov-2",
            "data_object_names": ["Customer", "Order"],
            "correlation_id": "corr-summary-1",
            "requested_by": "user-2",
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "grouped_scope",
            "status": "running",
            "failed_record_count": 3,
            "submitted_at": "2026-04-26T11:00:00Z",
            "created_at": "2026-04-26T11:00:00Z",
            "updated_at": "2026-04-26T11:01:00Z",
        }
    )

    assert payload.suiteId == "artifact-suite-2"
    assert payload.suiteVersion == 7
    assert payload.engineType == "gx"
    assert payload.dataObjectVersionId == "dov-2"
    assert payload.failedRecordCount == 3


def test_build_gx_execution_run_list_query_entity_accepts_artifact_aliases() -> None:
    payload = build_gx_execution_run_list_query_entity(
        {
            "submitted_after": "2026-04-26T00:00:00Z",
            "submitted_before": "2026-04-27T00:00:00Z",
            "artifact_id": "artifact-suite-3",
            "rule_id": "rule-3",
            "status": "running",
        }
    )

    assert payload.suiteId == "artifact-suite-3"
    assert payload.ruleId == "rule-3"
    assert payload.status == "running"


def test_run_plan_grouped_plan_builders_reuse_typed_entity() -> None:
    suite_selection = build_gx_run_plan_suite_selection_entity(
        {
            "selectionMode": "grouped_scope",
            "scopeSelector": {"dataObjectVersionId": "dov-1"},
            "suiteRefs": [{"suiteId": "gx_suite_1", "suiteVersion": 3, "engineType": "gx"}],
            "groupedExecutionPlan": {"suite_count": 4, "batch_count": 2},
        }
    )
    grouped_snapshot = build_gx_run_plan_grouped_suite_snapshot_entity(
        {
            "groupedExecutionPlan": {"suiteCount": 4, "batchCount": 2},
            "suiteEnvelopes": [{"suiteId": "gx_suite_1"}],
        }
    )

    assert suite_selection.groupedExecutionPlan is not None
    assert suite_selection.groupedExecutionPlan.suiteCount == 4
    assert suite_selection.groupedExecutionPlan.batchCount == 2
    assert len(suite_selection.suiteRefs) == 1
    assert suite_selection.suiteRefs[0].suiteId == "gx_suite_1"
    assert suite_selection.suiteRefs[0].suiteVersion == 3
    assert suite_selection.suiteRefs[0].engineType == "gx"
    assert suite_selection.scopeSelector.dataObjectVersionId == "dov-1"
    assert grouped_snapshot.groupedExecutionPlan is not None
    assert grouped_snapshot.groupedExecutionPlan.suiteCount == 4
    assert grouped_snapshot.groupedExecutionPlan.batchCount == 2
    assert grouped_snapshot.suiteEnvelopes[0].suiteId == "gx_suite_1"


def test_build_gx_suite_and_itsm_response_payloads_accept_snake_case() -> None:
    gx_suite = build_gx_suite_entity(
        {
            "expectations": [
                {
                    "expectation_type": "expect_column_values_to_not_be_null",
                    "kwargs": {"column": "order_id"},
                }
            ]
        }
    )
    expectation = build_gx_suite_expectation_entity(
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "order_id"},
        }
    )
    itsm_response = build_itsm_response_entity(
        {
            "ticket_number": "HAL-4242",
            "ticket_url": "https://itsm.example.com/ticket/HAL-4242",
            "ticket": {"number": "HAL-4242"},
            "data": {"ticket_id": "internal-42"},
        }
    )

    assert gx_suite is not None
    assert len(gx_suite.expectations) == 1
    assert gx_suite.expectations[0].expectationType == "expect_column_values_to_not_be_null"
    assert expectation is not None
    assert expectation.expectationType == "expect_column_values_to_not_be_null"
    assert itsm_response is not None
    assert itsm_response.ticketNumber == "HAL-4242"
    assert itsm_response.ticketUrl == "https://itsm.example.com/ticket/HAL-4242"
    assert itsm_response.ticket is not None
    assert itsm_response.ticket.number == "HAL-4242"
    assert itsm_response.data is not None
    assert itsm_response.data.ticketId == "internal-42"
    assert extract_itsm_ticket_number({"data": {"ticket_number": "HAL-4242"}}) == "HAL-4242"


def test_gx_endpoint_internal_payload_helpers_cover_resolution_and_status_sync() -> None:
    class TraceableExecutionContract:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def model_dump(self) -> dict[str, object]:
            return dict(self._payload)

    suite_from_contract = SimpleNamespace(
        executionContract=TraceableExecutionContract(
            {
                "engine_target": "dq-engine",
                "execution_shape": "small",
                "traceability": {"data_object_version_id": "dov-contract"},
            }
        ),
        resolvedExecutionScope=SimpleNamespace(dataObjectVersionIds=["dov-scope"]),
    )
    suite_from_scope = SimpleNamespace(
        executionContract=TraceableExecutionContract({"engine_target": "dq-engine", "execution_shape": "small"}),
        resolvedExecutionScope=SimpleNamespace(dataObjectVersionIds=["dov-scope"]),
    )
    suite_without_target = SimpleNamespace(executionContract=None, resolvedExecutionScope=None)
    suite_with_many_targets = SimpleNamespace(
        executionContract=None,
        resolvedExecutionScope=SimpleNamespace(dataObjectVersionIds=["dov-1", "dov-2"]),
    )

    assert gx_start_api._resolve_primary_data_object_version_id(suite_from_contract) == "dov-contract"
    assert gx_start_api._resolve_primary_data_object_version_id(suite_from_scope) == "dov-scope"
    assert gx_start_api._resolve_primary_data_object_version_id(suite_without_target) is None
    assert gx_start_api._resolve_primary_data_object_version_id(suite_with_many_targets) is None
    assert gx_start_api._resolve_execution_delivery_snapshot(
        suite=suite_without_target,
        data_catalog_repository=DummyDeliveryRepo([]),
    ) is None
    assert gx_suite_api._payload_extra_value({"ticketId": "ticket-1"}, "ticketId", "ticket_id") == "ticket-1"
    assert gx_suite_api._payload_extra_value(SimpleNamespace(model_extra={"ticket_id": "ticket-2"}), "ticketId", "ticket_id") == "ticket-2"
    assert gx_start_api._snakecase_payload(
        {"ticketId": "HAL-1", "children": [{"runPlanVersionId": "rpv-1"}]}
    ) == {
        "ticket_id": "HAL-1",
        "children": [{"run_plan_version_id": "rpv-1"}],
    }


def test_extract_report_violation_target_ids_prefers_diagnostics_then_results_then_contract() -> None:
    run = SimpleNamespace(
        executionContract={
            "engine_target": "dq-engine",
            "execution_shape": "small",
            "traceability": {"data_object_version_id": "dov-contract"},
        }
    )

    diagnostics_body = gx_endpoints.GxExecutionRunReportRequestView.model_validate(
        {
            "new_status": "failed",
            "diagnostics": [
                {"data_object_version_id": "dov-diagnostic", "row_identifier": "pk-1"},
                {"data_object_version_id": "dov-diagnostic", "row_identifier": "pk-2"},
            ],
        }
    )
    assert extract_exception_fact_target_ids(run_result=diagnostics_body, execution_context=run) == ["dov-diagnostic"]

    result_summary_body = gx_endpoints.GxExecutionRunReportRequestView.model_validate(
        {
            "new_status": "failed",
            "diagnostics": [{"row_identifier": "pk-3"}],
            "result_summary": {
                "results": [{"data_object_version_id": "dov-result", "ok": False, "violation_count": 1}],
                "failed_count": 1,
            },
        }
    )
    assert extract_exception_fact_target_ids(run_result=result_summary_body, execution_context=run) == ["dov-result"]


def test_enqueue_scheduled_suite_run_queue_unavailable(monkeypatch) -> None:
    class DummyRepo:
        async def create_run(self, run=None, **kwargs):
            raise AssertionError("should not create run")

    request = SimpleNamespace(headers={})
    suite = DummySuite(
        suite_id="gx_suite_1",
        execution_contract=DummyExecutionContract("dq-engine", "small"),
        resolved_execution_scope=SimpleNamespace(dataObjectVersionIds=["dov-1"]),
    )
    monkeypatch.setenv("GX_EXECUTION_QUEUE_KEY", "dq-gx:execution-dispatch")
    monkeypatch.setenv("GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY", "dq-gx:join-pair-materialize")
    monkeypatch.setattr(gx_endpoints.gx_queue_service, "resolve_redis_url", lambda settings: None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            gx_runtime_api.enqueue_scheduled_suite_run(
                request=request,
                suite=suite,
                scheduled_at=datetime.now(UTC),
                execution_run_repository=DummyRepo(),
                requested_by="user-1",
                status_source="source",
                status_reason="reason",
                execution_scope_override=None,
                source_overrides_by_data_object_version_id=None,
                delivery_snapshot=None,
                correlation_id=None,
                queue_key=gx_runtime_api.resolve_execution_queue_key(),
                join_pair_materialization_queue_key=gx_runtime_api.resolve_join_pair_materialization_queue_key(),
                data_catalog_repository=DummyDeliveryRepo([]),
                settings_provider=lambda: None,
                dispatch_worker_heartbeat_key_builder=gx_runtime_api.resolve_execution_worker_heartbeat_key,
                dispatch_worker_heartbeat_ttl_seconds=gx_runtime_api.resolve_execution_worker_heartbeat_ttl_seconds(),
                join_pair_materialization_worker_heartbeat_key_builder=gx_runtime_api.resolve_join_pair_materialization_worker_heartbeat_key,
                join_pair_materialization_worker_heartbeat_ttl_seconds=gx_runtime_api.resolve_join_pair_materialization_worker_heartbeat_ttl_seconds(),
                inject_trace_carrier=lambda carrier: None,
                map_persistence_error=gx_runtime_api.map_execution_run_persistence_error,
                async_redis_module=gx_endpoints.aioredis,
                sync_redis_module=gx_endpoints.redis_sync,
                logger=logging.getLogger(__name__),
            )
        )
    assert exc.value.status_code == 503


@pytest.mark.anyio
async def test_create_adhoc_gx_suite_runs_requires_selector_and_conflicting_scope(monkeypatch) -> None:
    class DummyRepo:
        async def list_suites(self, **kwargs):
            return []

        async def list_suites_for_rule(self, **kwargs):
            return []

    request = SimpleNamespace(headers={})
    monkeypatch.setenv("GX_EXECUTION_QUEUE_KEY", "dq-gx:execution-dispatch")
    monkeypatch.setenv("GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY", "dq-gx:join-pair-materialize")
    monkeypatch.setattr(gx_endpoints.gx_queue_service, "resolve_redis_url", lambda settings: "redis://example")

    async def noop_assert_active_gx_dispatch_worker(redis_url: str, queue_key: str) -> None:
        return None

    async def patched_assert_worker_heartbeat(
        redis_url: str,
        *,
        queue_key: str,
        heartbeat_key: str,
        expected_ttl_seconds: int,
        unavailable_error: str,
        unavailable_message: str,
        status_failed_error: str,
        status_failed_message: str,
        async_redis_module,
        sync_redis_module,
        logger,
    ) -> None:
        await noop_assert_active_gx_dispatch_worker(redis_url, queue_key)

    monkeypatch.setattr(gx_endpoints.gx_queue_service, "assert_worker_heartbeat", patched_assert_worker_heartbeat)

    body = gx_endpoints.GxAdhocSuiteRunsRequestView.model_validate({})
    with pytest.raises(HTTPException) as exc:
        await gx_endpoints.create_adhoc_gx_suite_runs(
            request=request,
            request_body=body,
            repository=DummyRepo(),
            execution_run_repository=DummyRepo(),
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["error"] == "missing_selector"

    body2 = gx_endpoints.GxAdhocSuiteRunsRequestView.model_validate(
        {
            "data_object_version_id": "dov-1",
            "target_data_object_version_ids": ["dov-2"],
        }
    )
    with pytest.raises(HTTPException) as exc2:
        await gx_endpoints.create_adhoc_gx_suite_runs(
            request=request,
            request_body=body2,
            repository=DummyRepo(),
            execution_run_repository=DummyRepo(),
        )
    assert exc2.value.status_code == 400
    assert exc2.value.detail["error"] == "conflicting_scope"