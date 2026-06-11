from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.application.use_cases.gx_dispatch import CreateAdhocGxSuiteRunsCommand
from app.application.use_cases.gx_dispatch import CreateGroupedScopeGxRunCommand
from app.application.use_cases.gx_dispatch import create_adhoc_gx_suite_runs
from app.application.use_cases.gx_dispatch import ScheduleGxSuiteRunCommand
from app.application.use_cases.gx_dispatch import create_grouped_scope_gx_run
from app.application.use_cases.gx_dispatch import schedule_gx_suite_run
from app.application.use_cases.gx_dispatch_runtime import build_execution_run_create_entity_for_grouped_dispatch
from app.application.use_cases.gx_dispatch_runtime import build_execution_run_create_entity_for_suite_dispatch
from app.application.use_cases.gx_dispatch_runtime import enqueue_scheduled_gx_suite_run
from app.application.use_cases.gx_dispatch_runtime import EnqueueScheduledGxSuiteRunCommand
from app.application.use_cases.gx_dispatch_runtime import persist_grouped_dispatch_run
from app.domain.entities.gx_execution_run import build_gx_dispatch_payload_entity
from app.domain.entities.gx_execution_run import build_gx_grouped_execution_plan_entity
from app.domain.entities.gx_run_plan import build_gx_run_plan_scope_selector_entity
from app.domain.entities.gx_run_plan import build_gx_run_plan_suite_ref_entities


def _suite(
    *,
    suite_id: str,
    suite_version: int,
    rule_ids: list[str],
    target_ids: list[str],
) -> SimpleNamespace:
    return SimpleNamespace(
        suiteId=suite_id,
        suiteVersion=suite_version,
        compiledFrom=SimpleNamespace(ruleIds=rule_ids),
        resolvedExecutionScope=SimpleNamespace(dataObjectVersionIds=target_ids),
    )


class _ExecutionContract:
    def __init__(self, engine_target: str, execution_shape: str) -> None:
        self.engineType = "gx"
        self.engineTarget = engine_target
        self.executionShape = execution_shape
        self.traceability = SimpleNamespace(ruleId="rule-1", ruleVersionId="rule-v1")

    def model_dump(self) -> dict[str, object]:
        return {"engineType": self.engineType, "engineTarget": self.engineTarget, "executionShape": self.executionShape}


@pytest.mark.anyio
async def test_schedule_gx_suite_run_resolves_suite_and_enqueues_dispatch() -> None:
    suite = _suite(suite_id="gx-suite-1", suite_version=2, rule_ids=["rule-1"], target_ids=["dov-1"])
    seen: dict[str, object] = {}

    async def resolve_suite(suite_id: str, suite_version: int | None, status: str):
        seen["resolve"] = (suite_id, suite_version, status)
        return suite

    async def enqueue_suite_run(**kwargs):
        seen["enqueue"] = kwargs
        return {"queue_message_id": "run-123", "suite_id": kwargs["suite"].suiteId, "engine_type": "gx"}

    result = await schedule_gx_suite_run(
        command=ScheduleGxSuiteRunCommand(
            suite_id="gx-suite-1",
            suite_version=2,
            scheduled_at=datetime(2026, 4, 27, 8, 0, tzinfo=UTC),
            status="active",
            requested_by="user-1",
            correlation_id="corr-123",
        ),
        resolve_suite=resolve_suite,
        enqueue_suite_run=enqueue_suite_run,
    )

    assert seen["resolve"] == ("gx-suite-1", 2, "active")
    assert seen["enqueue"] == {
        "suite": suite,
        "scheduled_at": datetime(2026, 4, 27, 8, 0, tzinfo=UTC),
        "requested_by": "user-1",
        "correlation_id": "corr-123",
        "execution_scope_override": None,
        "source_overrides_by_data_object_version_id": None,
        "status_source": "gx.suite.run.schedule",
        "status_reason": "GX suite run scheduled",
    }
    assert result.queueMessageId == "run-123"


@pytest.mark.anyio
async def test_create_adhoc_gx_suite_runs_filters_rule_ids_and_builds_overrides() -> None:
    suite = _suite(
        suite_id="gx-suite-1",
        suite_version=3,
        rule_ids=["rule-2"],
        target_ids=["dov-1", "dov-2"],
    )
    other_suite = _suite(
        suite_id="gx-suite-2",
        suite_version=1,
        rule_ids=["rule-9"],
        target_ids=["dov-9"],
    )
    seen: dict[str, object] = {}

    async def resolve_candidate_suites(data_object_version_id: str | None, rule_id: str | None, status: str, latest_only: bool):
        seen["resolve"] = (data_object_version_id, rule_id, status, latest_only)
        return [suite, other_suite]

    async def enqueue_suite_run(**kwargs):
        seen["enqueue"] = kwargs
        return {"queue_message_id": "run-456", "suite_id": kwargs["suite"].suiteId, "engine_type": "gx"}

    result = await create_adhoc_gx_suite_runs(
        command=CreateAdhocGxSuiteRunsCommand(
            scheduled_at=datetime(2026, 4, 27, 8, 15, tzinfo=UTC),
            data_object_version_id="dov-1",
            rule_ids=["rule-2"],
            target_data_object_version_ids=["dov-1", "dov-2"],
            source_override_uri="s3://override/orders.parquet",
            source_override_format="parquet",
            source_override_options={"compression": "snappy"},
            status="active",
            latest_only=True,
            requested_by="user-2",
            correlation_id="corr-456",
        ),
        resolve_candidate_suites=resolve_candidate_suites,
        enqueue_suite_run=enqueue_suite_run,
    )

    assert seen["resolve"] == ("dov-1", None, "active", True)
    assert seen["enqueue"] == {
        "suite": suite,
        "scheduled_at": datetime(2026, 4, 27, 8, 15, tzinfo=UTC),
        "requested_by": "user-2",
        "correlation_id": "corr-456",
        "execution_scope_override": ["dov-1", "dov-2"],
        "source_overrides_by_data_object_version_id": {
            "dov-1": {
                "uri": "s3://override/orders.parquet",
                "format": "parquet",
                "options": {"compression": "snappy"},
            },
            "dov-2": {
                "uri": "s3://override/orders.parquet",
                "format": "parquet",
                "options": {"compression": "snappy"},
            },
        },
        "status_source": "gx.runs.adhoc",
        "status_reason": "GX suite run scheduled",
    }
    assert len(result) == 1
    assert result[0].queueMessageId == "run-456"
    assert result[0].suiteId == "gx-suite-1"


@pytest.mark.anyio
async def test_create_adhoc_gx_suite_runs_rejects_invalid_execution_scope() -> None:
    suite = _suite(
        suite_id="gx-suite-1",
        suite_version=1,
        rule_ids=["rule-1"],
        target_ids=["dov-1"],
    )

    async def resolve_candidate_suites(data_object_version_id: str | None, rule_id: str | None, status: str, latest_only: bool):
        return [suite]

    async def enqueue_suite_run(**kwargs):
        raise AssertionError("enqueue should not be called")

    with pytest.raises(HTTPException) as error:
        await create_adhoc_gx_suite_runs(
            command=CreateAdhocGxSuiteRunsCommand(
                scheduled_at=datetime(2026, 4, 27, 8, 30, tzinfo=UTC),
                data_object_version_id="dov-1",
                target_data_object_version_ids=["dov-2"],
                status="active",
                latest_only=True,
            ),
            resolve_candidate_suites=resolve_candidate_suites,
            enqueue_suite_run=enqueue_suite_run,
        )

    assert error.value.status_code == 400
    assert error.value.detail["error"] == "conflicting_scope"


@pytest.mark.anyio
async def test_create_grouped_scope_gx_run_checks_transport_and_enqueues() -> None:
    seen: dict[str, object] = {}

    async def assert_dispatch_worker(redis_url: str, queue_key: str) -> None:
        seen["worker"] = (redis_url, queue_key)

    def build_dispatch_payload(**kwargs):
        seen["build"] = kwargs
        return {
            "run_id": "run-grouped-1",
            "queue_message_id": "run-grouped-1",
            "queue_key": kwargs.get("queue_key", "dq-gx:execution-dispatch"),
            "correlation_id": kwargs["correlation_id"],
            "engine_type": "gx",
            "execution_shape": "grouped_scope",
        }

    async def persist_run(dispatch_payload) -> None:
        seen["persist"] = dispatch_payload

    async def enqueue_payload(redis_url: str, queue_key: str, payload) -> None:
        seen["enqueue"] = (redis_url, queue_key, payload)

    result = await create_grouped_scope_gx_run(
        command=CreateGroupedScopeGxRunCommand(
            grouped_execution_plan=build_gx_grouped_execution_plan_entity({"suiteCount": 1, "batchCount": 1}),
            scope_selector=build_gx_run_plan_scope_selector_entity({"dataObjectVersionId": "dov-1"}),
            suite_refs=build_gx_run_plan_suite_ref_entities(
                [{"suiteId": "gx-suite-1", "suiteVersion": 1, "engineType": "gx"}]
            ),
            scheduled_at=datetime(2026, 4, 27, 9, 0, tzinfo=UTC),
            requested_by="user-3",
            correlation_id="corr-grouped-1",
            queue_key="dq-gx:execution-dispatch",
        ),
        resolve_redis_url=lambda: "redis://example",
        assert_dispatch_worker=assert_dispatch_worker,
        build_dispatch_payload=build_dispatch_payload,
        persist_run=persist_run,
        enqueue_payload=enqueue_payload,
    )

    assert seen["worker"] == ("redis://example", "dq-gx:execution-dispatch")
    assert seen["build"] == {
        "grouped_execution_plan": {"suite_count": 1, "batch_count": 1},
        "scope_selector": {"dataObjectVersionId": "dov-1"},
        "suite_refs": [{"suiteId": "gx-suite-1", "suiteVersion": 1, "engineType": "gx"}],
        "correlation_id": "corr-grouped-1",
        "requested_by": "user-3",
        "scheduled_at": datetime(2026, 4, 27, 9, 0, tzinfo=UTC),
        "source_overrides_by_data_object_version_id": None,
        "delivery_snapshot": None,
    }
    assert seen["persist"] == result
    assert seen["enqueue"] == ("redis://example", "dq-gx:execution-dispatch", result)
    assert result.queueMessageId == "run-grouped-1"


@pytest.mark.anyio
async def test_create_grouped_scope_gx_run_rejects_unsupported_engine_type() -> None:
    async def assert_dispatch_worker(redis_url: str, queue_key: str) -> None:
        raise AssertionError("worker check should not run")

    def build_dispatch_payload(**kwargs):
        raise AssertionError(f"dispatch payload should not be built: {kwargs}")

    async def persist_run(dispatch_payload) -> None:
        raise AssertionError(f"persist should not run: {dispatch_payload}")

    async def enqueue_payload(redis_url: str, queue_key: str, payload) -> None:
        raise AssertionError(f"enqueue should not run: {(redis_url, queue_key, payload)}")

    with pytest.raises(HTTPException) as error:
        await create_grouped_scope_gx_run(
            command=CreateGroupedScopeGxRunCommand(
                grouped_execution_plan=build_gx_grouped_execution_plan_entity({"suiteCount": 1, "batchCount": 1}),
                scope_selector=build_gx_run_plan_scope_selector_entity({"dataObjectVersionId": "dov-1"}),
                suite_refs=build_gx_run_plan_suite_ref_entities(
                    [{"suiteId": "soda-suite-1", "suiteVersion": 1, "engineType": "soda"}]
                ),
                scheduled_at=datetime(2026, 4, 27, 9, 5, tzinfo=UTC),
                requested_by="user-3",
                correlation_id="corr-grouped-unsupported",
                queue_key="dq-gx:execution-dispatch",
            ),
            resolve_redis_url=lambda: "redis://example",
            assert_dispatch_worker=assert_dispatch_worker,
            build_dispatch_payload=build_dispatch_payload,
            persist_run=persist_run,
            enqueue_payload=enqueue_payload,
        )

    assert error.value.status_code == 422
    assert error.value.detail["error"] == "unsupported_engine_type"
    assert error.value.detail["engine_type"] == "soda"


@pytest.mark.anyio
async def test_create_grouped_scope_gx_run_rejects_mixed_engine_types() -> None:
    async def assert_dispatch_worker(redis_url: str, queue_key: str) -> None:
        raise AssertionError("worker check should not run")

    def build_dispatch_payload(**kwargs):
        raise AssertionError(f"dispatch payload should not be built: {kwargs}")

    async def persist_run(dispatch_payload) -> None:
        raise AssertionError(f"persist should not run: {dispatch_payload}")

    async def enqueue_payload(redis_url: str, queue_key: str, payload) -> None:
        raise AssertionError(f"enqueue should not run: {(redis_url, queue_key, payload)}")

    with pytest.raises(HTTPException) as error:
        await create_grouped_scope_gx_run(
            command=CreateGroupedScopeGxRunCommand(
                grouped_execution_plan=build_gx_grouped_execution_plan_entity({"suiteCount": 2, "batchCount": 1}),
                scope_selector=build_gx_run_plan_scope_selector_entity({"dataObjectVersionId": "dov-1"}),
                suite_refs=build_gx_run_plan_suite_ref_entities(
                    [
                        {"suiteId": "gx-suite-1", "suiteVersion": 1, "engineType": "gx"},
                        {"suiteId": "soda-suite-1", "suiteVersion": 1, "engineType": "soda"},
                    ]
                ),
                scheduled_at=datetime(2026, 4, 27, 9, 10, tzinfo=UTC),
                requested_by="user-3",
                correlation_id="corr-grouped-mixed",
                queue_key="dq-gx:execution-dispatch",
            ),
            resolve_redis_url=lambda: "redis://example",
            assert_dispatch_worker=assert_dispatch_worker,
            build_dispatch_payload=build_dispatch_payload,
            persist_run=persist_run,
            enqueue_payload=enqueue_payload,
        )

    assert error.value.status_code == 422
    assert error.value.detail["error"] == "mixed_engine_types"
    assert error.value.detail["engine_types"] == ["gx", "soda"]


@pytest.mark.anyio
async def test_enqueue_scheduled_gx_suite_run_materializes_join_pair_before_dispatch() -> None:
    seen: dict[str, object] = {"workers": []}

    suite = SimpleNamespace(
        suiteId="gx-suite-join-1",
        suiteVersion=2,
        executionContract=SimpleNamespace(executionShape="join_pair"),
    )

    class _Repo:
        async def create_run(self, run):
            seen["create_run"] = run
            return run

        async def record_run_status_transition(self, transition):
            seen["transition"] = transition
            return transition

        async def list_runs(self, query):
            seen.setdefault("list_runs", []).append(query)
            return []

    async def assert_worker(redis_url: str, queue_key: str) -> None:
        workers = seen.setdefault("workers", [])
        assert isinstance(workers, list)
        workers.append((redis_url, queue_key))

    def build_dispatch_payload(**kwargs):
        seen["build_dispatch_payload"] = kwargs
        return {
            "run_id": "run-join-1",
            "queue_message_id": "run-join-1",
            "suite_id": "gx-suite-join-1",
            "suite_version": 2,
            "correlation_id": kwargs["correlation_id"],
            "requested_by": kwargs["requested_by"],
            "engine_type": "gx",
            "engine_target": "dq-engine",
            "execution_shape": "join_pair",
            "dispatch_mode": "queued",
            "executor_target": "dq-engine",
            "queue_key": "dq-gx:execution-dispatch",
            "handoff_status": "accepted",
            "handoff_ready": True,
            "submitted_at": "2026-04-27T09:00:00+00:00",
            "scheduled_at": kwargs["scheduled_at"].isoformat(),
            "execution_contract": {
                "engine_type": "gx",
                "engine_target": "dq-engine",
                "execution_shape": "join_pair",
                "source_materialization": {"join_type": "inner"},
            },
        }

    def inject_trace_carrier(carrier: dict[str, object]) -> None:
        carrier["traceparent"] = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"

    async def enqueue_payload(redis_url: str, payload) -> None:
        seen["enqueue"] = (redis_url, payload)

    result = await enqueue_scheduled_gx_suite_run(
        command=EnqueueScheduledGxSuiteRunCommand(
            suite=suite,
            scheduled_at=datetime(2026, 4, 27, 9, 0, tzinfo=UTC),
            requested_by="user-join",
            status_source="gx.runs.adhoc",
            status_reason="GX suite run scheduled",
            correlation_id="corr-join-1",
            queue_key="dq-gx:execution-dispatch",
            join_pair_materialization_queue_key="dq-gx:join-pair-materialize",
        ),
        execution_run_repository=_Repo(),
        resolve_redis_url=lambda: "redis://example",
        assert_dispatch_worker=assert_worker,
        assert_join_pair_materialization_worker=assert_worker,
        build_dispatch_payload=build_dispatch_payload,
        inject_trace_carrier=inject_trace_carrier,
        enqueue_payload=enqueue_payload,
        map_persistence_error=lambda suite_id, run_id, correlation_id, exc: HTTPException(
            status_code=503,
            detail={
                "error": "execution_run_persistence_failed",
                "suite_id": suite_id,
                "run_id": run_id,
                "correlation_id": correlation_id,
                "exception": exc.__class__.__name__,
            },
        ),
    )

    assert seen["workers"] == [
        ("redis://example", "dq-gx:execution-dispatch"),
        ("redis://example", "dq-gx:join-pair-materialize"),
    ]
    create_run = seen["create_run"]
    assert create_run.handoffPayload is not None
    assert create_run.handoffPayload.queueKey == "dq-gx:join-pair-materialize"
    assert create_run.handoffPayload.nextDispatchPayload is not None
    assert create_run.handoffPayload.nextDispatchPayload.queueKey == "dq-gx:execution-dispatch"
    assert create_run.statusDetails["pre_dispatch_phase"] == "join_pair_materialization"
    assert create_run.statusDetails["next_queue_key"] == "dq-gx:execution-dispatch"
    assert create_run.executionContract is not None
    assert create_run.executionContract.executionShape == "join_pair"
    assert result.queueKey == "dq-gx:join-pair-materialize"
    enqueue_result = seen["enqueue"]
    assert enqueue_result[0] == "redis://example"
    assert enqueue_result[1].headers["traceparent"] == "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
    assert enqueue_result[1].nextDispatchPayload is not None
    assert enqueue_result[1].nextDispatchPayload.headers["traceparent"] == "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"


@pytest.mark.anyio
async def test_enqueue_scheduled_gx_suite_run_rejects_active_suite_run() -> None:
    suite = _suite(suite_id="gx-suite-1", suite_version=2, rule_ids=["rule-1"], target_ids=["dov-1"])
    active_run = SimpleNamespace(
        id="run-active-1",
        status="running",
        suiteId="gx-suite-1",
        suiteVersion=2,
        handoffPayload=SimpleNamespace(runPlanId=None),
    )
    seen: dict[str, object] = {}

    class _Repo:
        async def list_runs(self, query):
            seen.setdefault("queries", []).append(query)
            if query.get("suite_id") == "gx-suite-1" and query.get("status") in {"pending", "running"}:
                return [active_run]
            return []

        async def create_run(self, run):
            raise AssertionError("create_run should not be called")

        async def record_run_status_transition(self, transition):
            raise AssertionError("record_run_status_transition should not be called")

    async def assert_worker(redis_url: str, queue_key: str) -> None:
        seen.setdefault("workers", []).append((redis_url, queue_key))

    def build_dispatch_payload(**kwargs):
        seen["build_dispatch_payload"] = kwargs
        return {
            "run_id": "run-conflict-1",
            "queue_message_id": "run-conflict-1",
            "suite_id": "gx-suite-1",
            "suite_version": 2,
            "correlation_id": kwargs["correlation_id"],
            "requested_by": kwargs["requested_by"],
            "engine_type": "gx",
            "engine_target": "dq-engine",
            "execution_shape": "small",
            "dispatch_mode": "queued",
            "executor_target": "dq-engine",
            "queue_key": "dq-gx:execution-dispatch",
            "handoff_status": "accepted",
            "handoff_ready": True,
            "submitted_at": "2026-04-27T09:00:00+00:00",
            "scheduled_at": kwargs["scheduled_at"].isoformat(),
        }

    with pytest.raises(HTTPException) as error:
        await enqueue_scheduled_gx_suite_run(
            command=EnqueueScheduledGxSuiteRunCommand(
                suite=suite,
                scheduled_at=datetime(2026, 4, 27, 9, 0, tzinfo=UTC),
                requested_by="user-active",
                status_source="gx.runs.adhoc",
                status_reason="GX suite run scheduled",
                correlation_id="corr-active-1",
                queue_key="dq-gx:execution-dispatch",
            ),
            execution_run_repository=_Repo(),
            resolve_redis_url=lambda: "redis://example",
            assert_dispatch_worker=assert_worker,
            assert_join_pair_materialization_worker=lambda *_args, **_kwargs: None,
            build_dispatch_payload=build_dispatch_payload,
            inject_trace_carrier=lambda _carrier: None,
            enqueue_payload=lambda *_args, **_kwargs: None,
            map_persistence_error=lambda suite_id, run_id, correlation_id, exc: HTTPException(
                status_code=503,
                detail={
                    "error": "execution_run_persistence_failed",
                    "suite_id": suite_id,
                    "run_id": run_id,
                    "correlation_id": correlation_id,
                    "exception": exc.__class__.__name__,
                },
            ),
        )

    assert error.value.status_code == 409
    assert error.value.detail["error"] == "gx_execution_already_active"
    assert error.value.detail["suite_id"] == "gx-suite-1"
    assert error.value.detail["active_run_id"] == "run-active-1"


@pytest.mark.anyio
async def test_persist_grouped_dispatch_run_rejects_active_run_plan() -> None:
    active_run = SimpleNamespace(
        id="run-plan-active-1",
        status="pending",
        suiteId=None,
        suiteVersion=None,
        handoffPayload=SimpleNamespace(runPlanId="run-plan-1"),
    )

    class _Repo:
        async def list_runs(self, query):
            if query.get("status") in {"pending", "running"}:
                return [active_run]
            return []

        async def create_run(self, run):
            raise AssertionError("create_run should not be called")

        async def record_run_status_transition(self, transition):
            raise AssertionError("record_run_status_transition should not be called")

    dispatch_payload = build_gx_dispatch_payload_entity(
        {
            "run_id": "run-grouped-1",
            "queue_message_id": "run-grouped-1",
            "run_plan_id": "run-plan-1",
            "correlation_id": "corr-grouped-1",
            "engine_type": "gx",
            "engine_target": "pyspark",
            "submitted_at": "2026-04-20T10:00:00Z",
            "handoff_status": "accepted",
            "handoff_ready": True,
        }
    )

    with pytest.raises(HTTPException) as error:
        await persist_grouped_dispatch_run(
            dispatch_payload=dispatch_payload,
            execution_run_repository=_Repo(),
            requested_by="user-grouped",
        )

    assert error.value.status_code == 409
    assert error.value.detail["error"] == "gx_execution_already_active"
    assert error.value.detail["run_plan_id"] == "run-plan-1"
    assert error.value.detail["active_run_id"] == "run-plan-active-1"


def test_build_execution_run_create_entity_for_suite_dispatch_uses_typed_contracts() -> None:
    suite = SimpleNamespace(
        suiteId="gx_suite_1",
        suiteVersion=1,
        executionContract=_ExecutionContract("dq-engine", "small"),
    )
    handoff_payload = build_gx_dispatch_payload_entity(
        {
            "run_id": "run-123",
            "suite_id": "gx_suite_1",
            "suite_version": 1,
            "correlation_id": "corr-1",
            "requested_by": "user-1",
            "engine_type": "gx",
            "engine_target": "dq-engine",
            "execution_shape": "small",
            "handoff_status": "accepted",
            "handoff_ready": True,
            "submitted_at": "2026-04-12T00:00:00Z",
            "execution_contract": {"engine_type": "gx", "engine_target": "dq-engine", "execution_shape": "small"},
        }
    )

    payload = build_execution_run_create_entity_for_suite_dispatch(
        suite=suite,
        handoff_payload=handoff_payload,
        requested_by="user-1",
        status_source="gx.suite.run.start",
        status_reason="GX suite run accepted",
    )

    assert payload.runId.startswith("run-")
    assert payload.suiteId == "gx_suite_1"
    assert payload.submittedAt == "2026-04-12T00:00:00Z"
    assert payload.engineType == "gx"
    assert payload.executionContract is not None
    assert payload.executionContract.engineType == "gx"
    assert payload.executionContract.executionShape == "small"
    assert payload.statusDetails["engine_type"] == "gx"


def test_build_execution_run_create_entity_for_suite_dispatch_rejects_missing_execution_contract_engine_type() -> None:
    suite = SimpleNamespace(
        suiteId="gx_suite_1",
        suiteVersion=1,
        executionContract=_ExecutionContract("dq-engine", "small"),
    )
    with pytest.raises(ValueError, match="GX dispatch execution_contract requires explicit engine_type"):
        build_gx_dispatch_payload_entity(
            {
                "run_id": "run-123",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "correlation_id": "corr-1",
                "requested_by": "user-1",
                "engine_type": "gx",
                "engine_target": "dq-engine",
                "execution_shape": "small",
                "handoff_status": "accepted",
                "handoff_ready": True,
                "submitted_at": "2026-04-12T00:00:00Z",
                "execution_contract": {"engine_target": "dq-engine", "execution_shape": "small"},
            }
        )


def test_build_execution_run_create_entity_for_grouped_dispatch_reuses_grouped_plan() -> None:
    create_payload = build_execution_run_create_entity_for_grouped_dispatch(
        handoff_payload=build_gx_dispatch_payload_entity(
            {
                "run_id": "run-grouped-1",
                "queue_message_id": "run-grouped-1",
                "correlation_id": "corr-grouped-1",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "submitted_at": "2026-04-20T10:00:00Z",
                "scope_selector": {"workspace_id": "retail-banking"},
                "suite_refs": [{"suite_id": "gx_suite_1", "engine_type": "gx"}],
                "grouped_execution_plan": {"suite_count": 3, "batch_count": 2},
                "handoff_status": "accepted",
                "handoff_ready": True,
                "queue_key": "dq-gx:execution-dispatch",
                "dispatch_mode": "queued",
            }
        ),
        requested_by="user-1",
    )

    assert create_payload.executionContract is not None
    assert create_payload.engineType == "gx"
    assert create_payload.executionContract.engineType == "gx"
    assert create_payload.executionContract.selectionMode == "grouped_scope"
    assert create_payload.executionContract.suiteCount == 3
    assert create_payload.executionContract.batchCount == 2
    assert create_payload.statusDetails["engine_type"] == "gx"
    assert create_payload.statusDetails["queue_key"] == "dq-gx:execution-dispatch"