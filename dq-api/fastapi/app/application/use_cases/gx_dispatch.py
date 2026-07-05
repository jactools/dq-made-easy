from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable
from uuid import uuid4

from fastapi import HTTPException

from app.domain.entities.gx_execution_run import GxExecutionDeliverySnapshotEntity
from app.domain.entities.gx_execution_run import build_gx_dispatch_payload_entity
from app.domain.entities.gx_execution_run import GxDispatchPayloadEntity
from app.domain.entities.gx_execution_run import GxGroupedExecutionPlanEntity
from app.domain.entities.gx_run_plan import GxRunPlanScopeSelectorEntity
from app.domain.entities.gx_run_plan import GxRunPlanSuiteRefEntity


@dataclass(slots=True)
class ScheduleGxSuiteRunCommand:
    suite_id: str
    scheduled_at: datetime
    suite_version: int | None = None
    status: str = "active"
    requested_by: str | None = None
    correlation_id: str | None = None
    source_override_uri: str | None = None
    source_override_format: str | None = None


@dataclass(slots=True)
class CreateAdhocGxSuiteRunsCommand:
    scheduled_at: datetime
    data_object_version_id: str | None = None
    rule_id: str | None = None
    rule_ids: list[str] | None = None
    tag_ids: list[str] | None = None
    target_data_object_version_ids: list[str] | None = None
    source_override_uri: str | None = None
    source_override_format: str | None = None
    source_override_options: dict[str, Any] | None = None
    status: str = "active"
    latest_only: bool = True
    requested_by: str | None = None
    correlation_id: str | None = None


ResolveScheduleSuite = Callable[[str, int | None, str], Awaitable[Any]]
ResolveCandidateSuites = Callable[[str | None, str | None, list[str] | None, str, bool], Awaitable[list[Any]]]
EnqueueSuiteRun = Callable[..., Awaitable[Any]]
ResolveRedisUrl = Callable[[], str | None]
AssertDispatchWorker = Callable[[str, str], Awaitable[None]]
BuildGroupedDispatchPayload = Callable[..., Any]
PersistGroupedDispatchRun = Callable[[GxDispatchPayloadEntity], Awaitable[None]]
EnqueueGroupedDispatchPayload = Callable[[str, str, GxDispatchPayloadEntity], Awaitable[None]]


@dataclass(slots=True)
class CreateGroupedScopeGxRunCommand:
    grouped_execution_plan: GxGroupedExecutionPlanEntity
    scope_selector: GxRunPlanScopeSelectorEntity
    suite_refs: list[GxRunPlanSuiteRefEntity]
    scheduled_at: datetime
    requested_by: str | None = None
    correlation_id: str | None = None
    run_plan_id: str | None = None
    run_plan_version_id: str | None = None
    source_overrides_by_data_object_version_id: dict[str, dict[str, Any]] | None = None
    delivery_snapshot: GxExecutionDeliverySnapshotEntity | None = None
    queue_key: str = "dq-gx:execution-dispatch"


def _normalize_optional_str(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_str_list(values: list[str] | None) -> list[str]:
    return [normalized for normalized in (_normalize_optional_str(value) for value in (values or [])) if normalized]


def _normalized_tag_ids(values: list[str] | None) -> list[str]:
    return _normalize_str_list(values)


async def _rule_ids_for_tags(rules_repository: RulesRepository, tag_ids: list[str] | None) -> set[str]:
    normalized_tag_ids = set(_normalized_tag_ids(tag_ids))
    if not normalized_tag_ids:
        return set()

    rule_ids: set[str] = set()
    for record in await rules_repository.list_rule_records():
        record_tag_ids = set(_normalized_tag_ids(list(record.tag_ids or [])))
        if record_tag_ids.intersection(normalized_tag_ids):
            rule_ids.add(str(record.id or "").strip())
    return {rule_id for rule_id in rule_ids if rule_id}


def _suite_rule_ids(suite: Any) -> set[str]:
    compiled_from = getattr(suite, "compiledFrom", None)
    rule_ids = getattr(compiled_from, "ruleIds", None)
    return {value for value in _normalize_str_list(list(rule_ids or []))}


def _suite_scope_targets(suite: Any) -> set[str]:
    resolved_scope = getattr(suite, "resolvedExecutionScope", None)
    target_ids = getattr(resolved_scope, "dataObjectVersionIds", None)
    return {value for value in _normalize_str_list(list(target_ids or []))}


def _suite_id(suite: Any) -> str:
    return str(getattr(suite, "suiteId", "") or "")


def _suite_version(suite: Any) -> int | None:
    value = getattr(suite, "suiteVersion", None)
    return int(value) if value is not None else None


def _as_dispatch_payload_entity(payload: Any) -> GxDispatchPayloadEntity:
    try:
        dispatch_payload = build_gx_dispatch_payload_entity(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_dispatch_payload",
                "message": str(exc),
            },
        ) from exc
    if dispatch_payload is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "invalid_dispatch_payload",
                "message": "GX dispatch payload could not be normalized",
            },
        )
    return dispatch_payload


def _grouped_dispatch_engine_types(
    *,
    suite_refs: list[GxRunPlanSuiteRefEntity],
    delivery_snapshot: GxExecutionDeliverySnapshotEntity | None,
) -> set[str]:
    engine_types = {
        str(item.engineType or "").strip().lower()
        for item in suite_refs
        if str(item.engineType or "").strip()
    }
    delivery_engine_type = str(delivery_snapshot.engineType or "").strip().lower() if delivery_snapshot is not None else ""
    if delivery_engine_type:
        engine_types.add(delivery_engine_type)
    return engine_types


def _assert_grouped_dispatch_engine_supported(
    *,
    suite_refs: list[GxRunPlanSuiteRefEntity],
    delivery_snapshot: GxExecutionDeliverySnapshotEntity | None,
) -> None:
    engine_types = _grouped_dispatch_engine_types(suite_refs=suite_refs, delivery_snapshot=delivery_snapshot)
    if not engine_types:
        return
    if len(engine_types) > 1:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "mixed_engine_types",
                "message": "GX grouped dispatch requires a single engine_type",
                "engine_types": sorted(engine_types),
            },
        )

    engine_type = next(iter(engine_types))
    if engine_type != "gx":
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_engine_type",
                "message": f"GX grouped dispatch does not support engine_type '{engine_type}'",
                "engine_type": engine_type,
            },
        )


async def schedule_gx_suite_run(
    command: ScheduleGxSuiteRunCommand,
    resolve_suite: ResolveScheduleSuite,
    enqueue_suite_run: EnqueueSuiteRun,
) -> GxDispatchPayloadEntity:
    suite = await resolve_suite(command.suite_id, command.suite_version, command.status)
    correlation_id = command.correlation_id or f"corr-{uuid4().hex[:12]}"
    source_override_uri = _normalize_optional_str(command.source_override_uri)
    source_override_format = _normalize_optional_str(command.source_override_format)
    suite_targets = _suite_scope_targets(suite)
    overrides_by_target: dict[str, dict[str, Any]] | None = None
    if source_override_uri and suite_targets:
        overrides_by_target = {
            target_id: {
                "uri": source_override_uri,
                "format": source_override_format,
            }
            for target_id in suite_targets
        }
    return _as_dispatch_payload_entity(
        await enqueue_suite_run(
            suite=suite,
            scheduled_at=command.scheduled_at,
            requested_by=command.requested_by,
            correlation_id=correlation_id,
            execution_scope_override=None,
            source_overrides_by_data_object_version_id=overrides_by_target,
            status_source="gx.suite.run.schedule",
            status_reason="GX suite run scheduled",
        )
    )


async def create_adhoc_gx_suite_runs(
    command: CreateAdhocGxSuiteRunsCommand,
    resolve_candidate_suites: ResolveCandidateSuites,
    enqueue_suite_run: EnqueueSuiteRun,
) -> list[GxDispatchPayloadEntity]:
    data_object_version_id = _normalize_optional_str(command.data_object_version_id)
    rule_id = _normalize_optional_str(command.rule_id)
    rule_ids = _normalize_str_list(command.rule_ids)
    tag_ids = _normalized_tag_ids(command.tag_ids)
    target_override_ids = _normalize_str_list(command.target_data_object_version_ids)
    source_override_uri = _normalize_optional_str(command.source_override_uri)
    source_override_format = _normalize_optional_str(command.source_override_format)

    if data_object_version_id and target_override_ids and data_object_version_id not in target_override_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "conflicting_scope",
                "message": "data_object_version_id must be included in target_data_object_version_ids when both are provided",
            },
        )

    if not data_object_version_id and not rule_id and not tag_ids:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_selector",
                "message": "Either data_object_version_id, rule_id, or tag_ids is required",
            },
        )

    suites = await resolve_candidate_suites(data_object_version_id, rule_id, tag_ids, command.status, command.latest_only)
    if not suites:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "gx_suites_not_found",
                "message": "No GX suites found for the requested selector",
                "data_object_version_id": data_object_version_id,
                "rule_id": rule_id,
                "tag_ids": tag_ids,
            },
        )

    if rule_ids:
        wanted_rule_ids = set(rule_ids)
        suites = [suite for suite in suites if _suite_rule_ids(suite).intersection(wanted_rule_ids)]
        if not suites:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "gx_suites_not_found",
                    "message": "No GX suites matched the provided rule_ids filter",
                    "rule_ids": rule_ids,
                },
            )

    execution_scope_override = target_override_ids or ([data_object_version_id] if data_object_version_id else [])
    if source_override_uri and not execution_scope_override:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_scope_for_override",
                "message": "source_override_uri requires an explicit execution scope (data_object_version_id or target_data_object_version_ids)",
            },
        )

    if source_override_uri and not source_override_format:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_source_override_format",
                "message": "source_override_format is required when source_override_uri is provided",
            },
        )

    correlation_id = command.correlation_id or f"corr-{uuid4().hex[:12]}"
    out: list[GxDispatchPayloadEntity] = []
    for suite in suites:
        dispatch_scope = list(execution_scope_override or [])
        if dispatch_scope:
            suite_targets = _suite_scope_targets(suite)
            missing_targets = [target_id for target_id in dispatch_scope if target_id not in suite_targets]
            if missing_targets:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "invalid_execution_scope",
                        "message": "One or more requested targets are not attached to this GX suite",
                        "suite_id": _suite_id(suite),
                        "suite_version": _suite_version(suite),
                        "missing_data_object_version_ids": missing_targets,
                    },
                )

        overrides_by_target: dict[str, dict[str, Any]] | None = None
        if source_override_uri:
            overrides_by_target = {
                target_id: {
                    "uri": source_override_uri,
                    "format": source_override_format,
                    "options": dict(command.source_override_options or {}),
                }
                for target_id in dispatch_scope
            }

        out.append(
            _as_dispatch_payload_entity(
                await enqueue_suite_run(
                    suite=suite,
                    scheduled_at=command.scheduled_at,
                    requested_by=command.requested_by,
                    correlation_id=correlation_id,
                    execution_scope_override=dispatch_scope or None,
                    source_overrides_by_data_object_version_id=overrides_by_target,
                    status_source="gx.runs.adhoc",
                    status_reason="GX suite run scheduled",
                )
            )
        )

    return out


async def create_grouped_scope_gx_run(
    command: CreateGroupedScopeGxRunCommand,
    resolve_redis_url: ResolveRedisUrl,
    assert_dispatch_worker: AssertDispatchWorker,
    build_dispatch_payload: BuildGroupedDispatchPayload,
    persist_run: PersistGroupedDispatchRun,
    enqueue_payload: EnqueueGroupedDispatchPayload,
) -> GxDispatchPayloadEntity:
    _assert_grouped_dispatch_engine_supported(
        suite_refs=command.suite_refs,
        delivery_snapshot=command.delivery_snapshot,
    )

    redis_url = resolve_redis_url()
    if not redis_url:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "dispatch_queue_unavailable",
                "message": "GX dispatch queue is not configured",
            },
        )

    await assert_dispatch_worker(redis_url, command.queue_key)

    correlation_id = command.correlation_id or f"corr-{uuid4().hex[:12]}"
    grouped_execution_plan = command.grouped_execution_plan.model_dump(by_alias=True, exclude_none=True)
    scope_selector = command.scope_selector.model_dump(by_alias=True, exclude_none=True)
    suite_refs = [item.model_dump(by_alias=True, exclude_none=True) for item in command.suite_refs]
    delivery_snapshot = (
        command.delivery_snapshot.model_dump(by_alias=True, exclude_none=True)
        if command.delivery_snapshot is not None
        else None
    )
    build_dispatch_payload_kwargs = {
        "grouped_execution_plan": grouped_execution_plan,
        "scope_selector": scope_selector,
        "suite_refs": suite_refs,
        "correlation_id": correlation_id,
        "requested_by": command.requested_by,
        "scheduled_at": command.scheduled_at,
        "source_overrides_by_data_object_version_id": command.source_overrides_by_data_object_version_id,
        "delivery_snapshot": delivery_snapshot,
    }
    if command.run_plan_id is not None:
        build_dispatch_payload_kwargs["run_plan_id"] = command.run_plan_id
    if command.run_plan_version_id is not None:
        build_dispatch_payload_kwargs["run_plan_version_id"] = command.run_plan_version_id

    dispatch_payload = _as_dispatch_payload_entity(build_dispatch_payload(**build_dispatch_payload_kwargs))

    try:
        await persist_run(dispatch_payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to persist grouped GX run") from exc

    try:
        await enqueue_payload(redis_url, str(dispatch_payload.queueKey or command.queue_key), dispatch_payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Failed to enqueue grouped GX dispatch payload") from exc

    return dispatch_payload