from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

from app.application.services.exception_fact_collection import collect_exception_facts
from app.application.services.exception_fact_collection import emit_exception_fact_batch
from app.api.v1.schemas import GxExecutionRunView
from app.domain.entities import GxExecutionRunEntity
from app.domain.entities import build_dq_result_event_from_gx_execution_run
from app.domain.entities.gx_execution_run import build_gx_execution_run_status_transition_entity
from app.domain.interfaces import DqResultEventRepository
from app.domain.interfaces import ExceptionFactRepository
from app.domain.interfaces import ExceptionReasonAnalyticsProjectionRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import GxSuiteRepository
from app.domain.interfaces import RulesRepository


TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled"}


async def persist_report_violations(
    *,
    run: GxExecutionRunEntity,
    body: Any,
    violation_repository: ExceptionFactRepository,
    projection_repository: ExceptionReasonAnalyticsProjectionRepository | None,
    settings_provider: Callable[[], Any],
    exception_storage_builder: Callable[..., Any],
) -> int:
    if body.newStatus != "failed":
        return 0

    violation_batch = collect_exception_facts(run_result=body, execution_context=run)
    if not violation_batch:
        return 0

    return await emit_exception_fact_batch(
        violation_batch=violation_batch,
        settings_provider=settings_provider,
        violation_repository=violation_repository,
        exception_storage_builder=exception_storage_builder,
        projection_repository=projection_repository,
    )


async def persist_dq_result_event(
    *,
    run: GxExecutionRunEntity,
    body: Any,
    suite_repository: GxSuiteRepository,
    rules_repository: RulesRepository,
    dq_result_event_repository: DqResultEventRepository,
) -> int:
    if body.newStatus not in TERMINAL_RUN_STATUSES:
        return 0

    suite = None
    if run.suiteId is not None:
        suite = await suite_repository.get_suite_by_id(
            suite_id=run.suiteId,
            suite_version=run.suiteVersion,
        )
    rule = None
    if run.ruleId is not None:
        rule = await rules_repository.get_rule_by_id(run.ruleId)

    await dq_result_event_repository.record_result_event(
        build_dq_result_event_from_gx_execution_run(
            run,
            suite=suite,
            rule=rule,
            report_body=body,
        )
    )
    return 1


async def report_execution_run(
    *,
    run_id: str,
    body: Any,
    repository: GxExecutionRunRepository,
    suite_repository: GxSuiteRepository,
    rules_repository: RulesRepository,
    dq_result_event_repository: DqResultEventRepository,
    violation_repository: ExceptionFactRepository,
    projection_repository: ExceptionReasonAnalyticsProjectionRepository | None,
    settings_provider: Callable[[], Any],
    exception_storage_builder: Callable[..., Any],
) -> GxExecutionRunView:
    try:
        updated = await repository.record_run_status_transition(
            build_gx_execution_run_status_transition_entity(
                {
                    "run_id": run_id,
                    "new_status": body.newStatus,
                    "changed_by": body.changedBy,
                    "reason": body.reason,
                    "details": body.details,
                    "execution_progress": body.executionProgress,
                    "started_at": body.startedAt,
                    "completed_at": body.completedAt,
                    "result_summary": body.resultSummary,
                    "metrics": body.metrics,
                    "performance_summary": body.performanceSummary,
                    "diagnostics": body.diagnostics,
                    "failure_code": body.failureCode,
                    "failure_message": body.failureMessage,
                }
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "run_not_found",
                "message": f"GX execution run '{run_id}' not found",
                "run_id": run_id,
            },
        ) from exc

    try:
        await persist_dq_result_event(
            run=updated,
            body=body,
            suite_repository=suite_repository,
            rules_repository=rules_repository,
            dq_result_event_repository=dq_result_event_repository,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "dq_result_history_persistence_failed",
                "message": "GX execution result history persistence failed",
                "run_id": run_id,
                "exception": exc.__class__.__name__,
            },
        ) from exc

    try:
        await persist_report_violations(
            run=updated,
            body=body,
            violation_repository=violation_repository,
            projection_repository=projection_repository,
            settings_provider=settings_provider,
            exception_storage_builder=exception_storage_builder,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "violation_persistence_failed",
                "message": "GX execution violation persistence failed",
                "run_id": run_id,
                "exception": exc.__class__.__name__,
            },
        ) from exc

    return GxExecutionRunView.model_validate(updated.model_dump(mode="python", by_alias=False, exclude_none=True))


async def report_execution_run_view(
    *,
    run_id: str,
    body: Any,
    repository: GxExecutionRunRepository,
    suite_repository: GxSuiteRepository,
    rules_repository: RulesRepository,
    dq_result_event_repository: DqResultEventRepository,
    violation_repository: ExceptionFactRepository,
    projection_repository: ExceptionReasonAnalyticsProjectionRepository | None,
    settings_provider: Callable[[], Any],
    exception_storage_builder: Callable[..., Any],
) -> GxExecutionRunView:
    return await report_execution_run(
        run_id=run_id,
        body=body,
        repository=repository,
        suite_repository=suite_repository,
        rules_repository=rules_repository,
        dq_result_event_repository=dq_result_event_repository,
        violation_repository=violation_repository,
        projection_repository=projection_repository,
        settings_provider=settings_provider,
        exception_storage_builder=exception_storage_builder,
    )