from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.application.services.delivery_linked_execution_orchestrator as orchestrator_module
from app.application.services.delivery_linked_execution_orchestrator import DeliveryLinkedExecutionOrchestrator
from app.domain.entities import build_validation_artifact_envelope_entity
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact
from app.domain.entities import GxArtifactAssignmentScopeEntity
from app.domain.entities import GxArtifactCompiledFromEntity
from app.domain.entities import GxArtifactEnvelopeEntity
from app.domain.entities import GxArtifactExecutionHintsEntity
from app.domain.entities import GxArtifactResolvedExecutionScopeEntity
from app.domain.entities import ValidationArtifactEnvelopeEntity


@pytest.fixture
def orchestrator() -> DeliveryLinkedExecutionOrchestrator:
    return DeliveryLinkedExecutionOrchestrator(
        catalog_repository=SimpleNamespace(),
        validation_artifact_repository=SimpleNamespace(get_artifact_by_id=AsyncMock(return_value=None)),
        validation_run_plan_repository=SimpleNamespace(),
        execution_run_repository=SimpleNamespace(),
        runtime_api=SimpleNamespace(),
    )


@pytest.fixture
def valid_suite_entity() -> GxArtifactEnvelopeEntity:
    return GxArtifactEnvelopeEntity(
        suiteId="suite-a",
        suiteVersion=1,
        artifactVersion="v1",
        assignmentScope=GxArtifactAssignmentScopeEntity(dataObjectId="do-1"),
        resolvedExecutionScope=GxArtifactResolvedExecutionScopeEntity(dataObjectVersionIds=["dov-1"]),
        gxSuite={"expectation_suite_name": "suite-a", "expectations": [], "meta": {}},
        compiledFrom=GxArtifactCompiledFromEntity(
            ruleIds=["rule-1"],
            compilerVersion="dq-compiler-7.3",
            generatedAt="2026-04-25T00:00:00Z",
        ),
        executionHints=GxArtifactExecutionHintsEntity(recommendedEngine="pyspark", primaryKeyFields=["id"]),
    )


@pytest.fixture
def valid_artifact_entity(valid_suite_entity: GxArtifactEnvelopeEntity) -> ValidationArtifactEnvelopeEntity:
    return build_validation_artifact_envelope_from_gx_artifact(valid_suite_entity)


def test_choose_execution_mode_matrix() -> None:
    assert DeliveryLinkedExecutionOrchestrator._choose_execution_mode(
        {
            "execution_selector": {"selector_type": "gx_suite"},
            "execution_resolution": {"applicable_gx_suites": []},
        }
    ) == "single_suite"

    assert DeliveryLinkedExecutionOrchestrator._choose_execution_mode(
        {
            "execution_selector": {"selector_type": "run_plan"},
            "resolved_run_plan_id": "rp-1",
            "execution_resolution": {
                "applicable_run_plans": [
                    {"run_plan_id": "rp-1", "planning_mode": "grouped_scope"},
                ],
                "applicable_gx_suites": [{"suite_id": "suite-a", "suite_version": 1, "engine_type": "gx"}],
            },
        }
    ) == "grouped_scope"

    assert DeliveryLinkedExecutionOrchestrator._choose_execution_mode(
        {
            "execution_resolution": {
                "applicable_gx_suites": [
                    {"suite_id": "suite-a", "suite_version": 1, "engine_type": "gx"},
                    {"suite_id": "suite-b", "suite_version": 1, "engine_type": "gx"},
                ]
            },
        }
    ) == "grouped_scope"


def test_delivery_snapshot_requires_delivery_fields() -> None:
    with pytest.raises(HTTPException) as missing_format:
        DeliveryLinkedExecutionOrchestrator._delivery_snapshot(
            {
                "data_delivery_id": "del-1",
                "resolved_data_object_version_id": "dov-1",
                "resolved_delivery_location": "s3://bucket/path",
                "delivery_note": {},
            }
        )
    assert missing_format.value.detail["error"] == "missing_delivery_format"

    with pytest.raises(HTTPException) as missing_version:
        DeliveryLinkedExecutionOrchestrator._delivery_snapshot(
            {
                "data_delivery_id": "del-1",
                "resolved_data_object_version_id": "",
                "resolved_delivery_location": "s3://bucket/path",
                "delivery_note": {"delivery_format": "parquet"},
            }
        )
    assert missing_version.value.detail["error"] == "missing_data_object_version_id"

    with pytest.raises(HTTPException) as missing_location:
        DeliveryLinkedExecutionOrchestrator._delivery_snapshot(
            {
                "data_delivery_id": "del-1",
                "resolved_data_object_version_id": "dov-1",
                "resolved_delivery_location": "",
                "delivery_note": {"delivery_format": "parquet"},
            }
        )
    assert missing_location.value.detail["error"] == "missing_delivery_location"

    snapshot = DeliveryLinkedExecutionOrchestrator._delivery_snapshot(
        {
            "data_delivery_id": "del-1",
            "resolved_data_object_version_id": "dov-1",
            "resolved_delivery_location": "s3://bucket/path",
            "resolved_engine_type": "gx",
            "delivery_note": {"delivery_format": "parquet"},
        }
    )
    assert snapshot["engineType"] == "gx"


@pytest.mark.anyio
async def test_load_suite_rejects_missing_selection(orchestrator: DeliveryLinkedExecutionOrchestrator) -> None:
    with pytest.raises(HTTPException) as error:
        await orchestrator._load_suite({"data_delivery_id": "del-1"})

    assert error.value.status_code == 422
    assert error.value.detail["error"] == "missing_gx_suite_selection"


@pytest.mark.anyio
async def test_load_suite_rejects_unknown_suite(orchestrator: DeliveryLinkedExecutionOrchestrator) -> None:
    with pytest.raises(HTTPException) as error:
        await orchestrator._load_suite(
            {
                "data_delivery_id": "del-1",
                "resolved_gx_suite_id": "suite-missing",
                "resolved_gx_suite_version": 1,
            }
        )

    assert error.value.status_code == 404
    assert error.value.detail["error"] == "gx_suite_not_found"


@pytest.mark.anyio
async def test_load_suite_accepts_pretyped_entity(
    orchestrator: DeliveryLinkedExecutionOrchestrator,
    valid_artifact_entity: ValidationArtifactEnvelopeEntity,
) -> None:
    orchestrator._validation_artifact_repository = SimpleNamespace(
        get_artifact_by_id=AsyncMock(return_value=valid_artifact_entity)
    )

    loaded = await orchestrator._load_suite(
        {
            "data_delivery_id": "del-1",
            "resolved_gx_suite_id": "suite-a",
            "resolved_gx_suite_version": 1,
        }
    )

    assert loaded.suiteId == "suite-a"
    assert loaded.suiteVersion == 1


@pytest.mark.anyio
async def test_load_suite_rejects_unsupported_engine_type(
    orchestrator: DeliveryLinkedExecutionOrchestrator,
) -> None:
    artifact = build_validation_artifact_envelope_entity(
        {
            "validationArtifactId": "suite-a",
            "validationArtifactVersion": 1,
            "artifactContractVersion": "v1",
            "engineType": "soda",
            "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-1"]},
            "engineArtifact": {
                "engineType": "soda",
                "artifactKind": "scan",
                "artifactSchemaVersion": "v1",
                "payload": {},
            },
        }
    )
    orchestrator._validation_artifact_repository = SimpleNamespace(
        get_artifact_by_id=AsyncMock(return_value=artifact)
    )

    with pytest.raises(HTTPException) as error:
        await orchestrator._load_suite(
            {
                "data_delivery_id": "del-1",
                "resolved_gx_suite_id": "suite-a",
                "resolved_gx_suite_version": 1,
            }
        )

    assert error.value.status_code == 422
    assert error.value.detail["error"] == "unsupported_engine_type"


@pytest.mark.anyio
async def test_load_suite_maps_invalid_envelope_to_http_exception(
    monkeypatch: pytest.MonkeyPatch,
    orchestrator: DeliveryLinkedExecutionOrchestrator,
) -> None:
    class _Row:
        def model_dump(self, **kwargs):
            del kwargs
            return {"validationArtifactId": "broken"}

    try:
        ValidationArtifactEnvelopeEntity.model_validate({})
    except ValidationError as exc:
        validation_error = exc

    orchestrator._validation_artifact_repository = SimpleNamespace(get_artifact_by_id=AsyncMock(return_value=_Row()))
    monkeypatch.setattr(
        orchestrator_module,
        "build_validation_artifact_envelope_entity",
        lambda payload: (_ for _ in ()).throw(validation_error),
    )

    with pytest.raises(HTTPException) as error:
        await orchestrator._load_suite(
            {
                "data_delivery_id": "del-1",
                "resolved_gx_suite_id": "suite-a",
                "resolved_gx_suite_version": 1,
            }
        )

    assert error.value.status_code == 422
    assert error.value.detail["error"] == "invalid_gx_suite_envelope"


@pytest.mark.anyio
async def test_execute_submission_dispatches_single_suite_mode(
    monkeypatch: pytest.MonkeyPatch,
    orchestrator: DeliveryLinkedExecutionOrchestrator,
    valid_suite_entity: GxArtifactEnvelopeEntity,
) -> None:
    runtime_api = SimpleNamespace(
        resolve_execution_queue_key=lambda: "queue:gx",
        resolve_join_pair_materialization_queue_key=lambda: "queue:join-pair",
        resolve_execution_worker_heartbeat_key=lambda workspace, run_id: f"hb:{workspace}:{run_id}",
        resolve_execution_worker_heartbeat_ttl_seconds=lambda: 120,
        resolve_join_pair_materialization_worker_heartbeat_key=lambda workspace, run_id: f"hb:jp:{workspace}:{run_id}",
        resolve_join_pair_materialization_worker_heartbeat_ttl_seconds=lambda: 180,
        map_execution_run_persistence_error=lambda exc: exc,
        enqueue_scheduled_suite_run=AsyncMock(
            return_value={
                "run_id": "run-1",
                "queue_message_id": "msg-1",
                "queue_key": "queue:gx",
            }
        ),
    )
    orchestrator._runtime_api = runtime_api
    orchestrator._resolver = SimpleNamespace(
        resolve_submission=AsyncMock(
            return_value={
                "data_delivery_id": "del-1",
                "resolved_data_object_version_id": "dov-1",
                "resolved_delivery_location": "s3://bucket/path",
                "delivery_note": {"delivery_format": "parquet"},
                "resolved_engine_type": "gx",
                "execution_selector": {"selector_type": "gx_suite"},
            }
        )
    )
    monkeypatch.setattr(orchestrator, "_load_suite", AsyncMock(return_value=valid_suite_entity))

    result = await orchestrator.execute_submission(
        request=SimpleNamespace(headers={"X-Correlation-ID": "corr-1"}),
        data_delivery_id="del-1",
        requested_by="user-a",
    )

    assert result["execution_mode"] == "single_suite"
    assert result["execution_run_id"] == "msg-1"
    assert result["resolved_engine_type"] == "gx"
    assert result["execution_dispatch"]["queue_message_id"] == "msg-1"
    runtime_api.enqueue_scheduled_suite_run.assert_awaited_once()
    assert runtime_api.enqueue_scheduled_suite_run.await_args.kwargs["delivery_snapshot"]["engineType"] == "gx"


@pytest.mark.anyio
async def test_execute_submission_dispatches_grouped_scope_mode(
    orchestrator: DeliveryLinkedExecutionOrchestrator,
) -> None:
    runtime_api = SimpleNamespace(
        resolve_execution_queue_key=lambda: "queue:gx",
        resolve_execution_worker_heartbeat_key=lambda workspace, run_id: f"hb:{workspace}:{run_id}",
        resolve_execution_worker_heartbeat_ttl_seconds=lambda: 120,
        build_grouped_scope_command=lambda payload: payload,
        enqueue_grouped_scope_run=AsyncMock(
            return_value={
                "run_id": "run-2",
                "queue_message_id": "msg-2",
                "queue_key": "queue:gx",
            }
        ),
    )
    orchestrator._runtime_api = runtime_api
    orchestrator._resolver = SimpleNamespace(
        resolve_submission=AsyncMock(
            return_value={
                "data_delivery_id": "del-1",
                "resolved_data_object_version_id": "dov-1",
                "resolved_delivery_location": "s3://bucket/path",
                "delivery_note": {"delivery_format": "parquet"},
                "resolved_engine_type": "gx",
                "resolved_run_plan_id": "rp-1",
                "resolved_run_plan_version_id": "rv-1",
                "execution_selector": {"selector_type": "run_plan"},
                "execution_resolution": {
                    "grouped_execution_plan": {"suite_count": 2, "batch_count": 1},
                    "applicable_gx_suites": [
                        {"suite_id": "suite-a", "suite_version": 1, "engine_type": "gx"},
                        {"suite_id": "suite-b", "suite_version": 3, "engine_type": "gx"},
                    ],
                    "applicable_run_plans": [
                        {"run_plan_id": "rp-1", "planning_mode": "grouped_scope"},
                    ],
                },
            }
        )
    )

    result = await orchestrator.execute_submission(
        request=SimpleNamespace(headers={"X-Correlation-ID": "corr-2"}),
        data_delivery_id="del-1",
        requested_by="user-b",
        correlation_id="corr-explicit",
    )

    assert result["execution_mode"] == "grouped_scope"
    assert result["execution_run_id"] == "msg-2"
    assert result["resolved_engine_type"] == "gx"
    assert result["execution_dispatch"]["queue_message_id"] == "msg-2"
    runtime_api.enqueue_grouped_scope_run.assert_awaited_once()
    assert runtime_api.enqueue_grouped_scope_run.await_args.kwargs["delivery_snapshot"]["engineType"] == "gx"
    assert runtime_api.enqueue_grouped_scope_run.await_args.kwargs["run_plan_id"] == "rp-1"
    assert runtime_api.enqueue_grouped_scope_run.await_args.kwargs["run_plan_version_id"] == "rv-1"
    assert runtime_api.enqueue_grouped_scope_run.await_args.kwargs["suite_refs"][0]["suite_id"] == "suite-a"
    assert runtime_api.enqueue_grouped_scope_run.await_args.kwargs["suite_refs"][0]["engine_type"] == "gx"


@pytest.mark.anyio
async def test_execute_submission_fails_closed_for_unsupported_engine_type(
    orchestrator: DeliveryLinkedExecutionOrchestrator,
) -> None:
    orchestrator._resolver = SimpleNamespace(
        resolve_submission=AsyncMock(
            return_value={
                "data_delivery_id": "del-1",
                "resolved_data_object_version_id": "dov-1",
                "resolved_delivery_location": "s3://bucket/path",
                "delivery_note": {"delivery_format": "parquet"},
                "resolved_engine_type": "soda",
                "execution_selector": {"selector_type": "gx_suite"},
            }
        )
    )

    with pytest.raises(HTTPException) as error:
        await orchestrator.execute_submission(
            request=SimpleNamespace(headers={}),
            data_delivery_id="del-1",
        )

    assert error.value.status_code == 422
    assert error.value.detail["error"] == "unsupported_engine_type"


@pytest.mark.anyio
async def test_execute_submission_grouped_scope_fails_closed_for_mixed_engine_types(
    orchestrator: DeliveryLinkedExecutionOrchestrator,
) -> None:
    runtime_api = SimpleNamespace(enqueue_grouped_scope_run=AsyncMock())
    orchestrator._runtime_api = runtime_api
    orchestrator._resolver = SimpleNamespace(
        resolve_submission=AsyncMock(
            return_value={
                "data_delivery_id": "del-1",
                "resolved_data_object_version_id": "dov-1",
                "resolved_delivery_location": "s3://bucket/path",
                "delivery_note": {"delivery_format": "parquet"},
                "resolved_engine_type": None,
                "resolved_run_plan_id": "rp-1",
                "execution_selector": {"selector_type": "run_plan"},
                "execution_resolution": {
                    "grouped_execution_plan": {"suite_count": 1, "batch_count": 1},
                    "applicable_gx_suites": [
                        {"suite_id": "suite-a", "suite_version": 1, "engine_type": "gx"},
                    ],
                    "applicable_run_plans": [
                        {
                            "run_plan_id": "rp-1",
                            "planning_mode": "grouped_scope",
                            "active_version": {
                                "run_plan_version_id": "rv-1",
                                "engine_type": "soda",
                                "suite_id": "suite-a",
                                "suite_version": 1,
                            },
                        }
                    ],
                },
            }
        )
    )

    with pytest.raises(HTTPException) as error:
        await orchestrator.execute_submission(
            request=SimpleNamespace(headers={}),
            data_delivery_id="del-1",
        )

    assert error.value.status_code == 422
    assert error.value.detail["error"] == "mixed_engine_types"
    assert error.value.detail["engine_types"] == ["gx", "soda"]
    runtime_api.enqueue_grouped_scope_run.assert_not_awaited()


@pytest.mark.anyio
async def test_execute_submission_grouped_scope_fails_closed_for_unsupported_grouped_engine_type(
    orchestrator: DeliveryLinkedExecutionOrchestrator,
) -> None:
    runtime_api = SimpleNamespace(enqueue_grouped_scope_run=AsyncMock())
    orchestrator._runtime_api = runtime_api
    orchestrator._resolver = SimpleNamespace(
        resolve_submission=AsyncMock(
            return_value={
                "data_delivery_id": "del-1",
                "resolved_data_object_version_id": "dov-1",
                "resolved_delivery_location": "s3://bucket/path",
                "delivery_note": {"delivery_format": "parquet"},
                "resolved_engine_type": "soda",
                "resolved_run_plan_id": "rp-1",
                "execution_selector": {"selector_type": "run_plan"},
                "execution_resolution": {
                    "grouped_execution_plan": {"suite_count": 1, "batch_count": 1},
                    "applicable_gx_suites": [],
                    "applicable_run_plans": [
                        {
                            "run_plan_id": "rp-1",
                            "planning_mode": "grouped_scope",
                            "active_version": {
                                "run_plan_version_id": "rv-1",
                                "engine_type": "soda",
                                "suite_id": None,
                                "suite_version": None,
                            },
                        }
                    ],
                },
            }
        )
    )

    with pytest.raises(HTTPException) as error:
        await orchestrator.execute_submission(
            request=SimpleNamespace(headers={}),
            data_delivery_id="del-1",
        )

    assert error.value.status_code == 422
    assert error.value.detail["error"] == "unsupported_engine_type"
    assert error.value.detail["engine_type"] == "soda"
    runtime_api.enqueue_grouped_scope_run.assert_not_awaited()