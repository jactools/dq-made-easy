from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi import Request
from pydantic import ValidationError

from app.api.presenters.gx import to_gx_suite_run_dispatch_handoff_view
from app.api.presenters.gx import to_gx_suite_run_dispatch_handoff_views
from app.api.v1.schemas import GxArtifactEnvelopeView
from app.api.v1.schemas import GxSuiteRunDispatchHandoffView
from app.application.use_cases.gx_dispatch import create_adhoc_gx_suite_runs as create_adhoc_gx_suite_runs_use_case
from app.application.use_cases.gx_dispatch import CreateAdhocGxSuiteRunsCommand
from app.application.use_cases.gx_dispatch import schedule_gx_suite_run as schedule_gx_suite_run_use_case
from app.application.use_cases.gx_dispatch import ScheduleGxSuiteRunCommand
from app.domain.entities.gx_execution_run import GxDispatchPayloadEntity
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import GxSuiteRepository
from app.domain.interfaces import RulesRepository


ResolveAdhocCandidateSuites = Callable[..., Awaitable[list[GxArtifactEnvelopeView]]]
EnqueueSuiteRun = Callable[..., Awaitable[GxDispatchPayloadEntity]]


@dataclass(slots=True)
class ScheduleSuiteRunResult:
    suite: GxArtifactEnvelopeView
    dispatch_view: GxSuiteRunDispatchHandoffView


class GxScheduleSuiteRunError(HTTPException):
    def __init__(self, *, status_code: int, detail: Any, suite: GxArtifactEnvelopeView | None = None) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.suite = suite


def request_correlation_id(request: Request | None) -> str:
    return (request.headers.get("X-Correlation-ID") if request is not None else None) or f"corr-{uuid4().hex[:12]}"


def build_schedule_command(
    *,
    request: Request,
    suite_id: str,
    suite_version: int | None,
    status: str,
    request_body: Any,
    requested_by: str | None,
) -> ScheduleGxSuiteRunCommand:
    return ScheduleGxSuiteRunCommand(
        suite_id=suite_id,
        suite_version=suite_version,
        scheduled_at=request_body.scheduledAt,
        status=status,
        requested_by=requested_by,
        correlation_id=request_correlation_id(request),
        source_override_uri=(
            str(request_body.sourceOverrideUri or "").strip()
            if request_body.sourceOverrideUri is not None
            else None
        ),
        source_override_format=(
            str(request_body.sourceOverrideFormat or "").strip().lower()
            if request_body.sourceOverrideFormat is not None
            else None
        ),
    )


def build_adhoc_command(
    *,
    request: Request,
    request_body: Any,
    requested_by: str | None,
) -> CreateAdhocGxSuiteRunsCommand:
    return CreateAdhocGxSuiteRunsCommand(
        scheduled_at=datetime.now(UTC),
        data_object_version_id=request_body.dataObjectVersionId,
        rule_id=request_body.ruleId,
        rule_ids=list(request_body.ruleIds or []),
        tag_ids=list(request_body.tagIds or []),
        target_data_object_version_ids=list(request_body.targetDataObjectVersionIds or []),
        source_override_uri=request_body.sourceOverrideUri,
        source_override_format=(
            str(request_body.sourceOverrideFormat or "").strip().lower()
            if request_body.sourceOverrideFormat is not None
            else None
        ),
        source_override_options=(
            dict(request_body.sourceOverrideOptions)
            if isinstance(request_body.sourceOverrideOptions, dict)
            else None
        ),
        status=request_body.status,
        latest_only=request_body.latestOnly,
        requested_by=requested_by,
        correlation_id=request_correlation_id(request),
    )


def bind_cached_suite_resolver(
    suite: GxArtifactEnvelopeView,
) -> Callable[[str, int | None, str], Awaitable[GxArtifactEnvelopeView]]:
    async def _resolver(_suite_id: str, _suite_version: int | None, _status: str) -> GxArtifactEnvelopeView:
        return suite

    return _resolver


def bind_adhoc_candidate_suite_resolver(
    *,
    repository: GxSuiteRepository,
    rules_repository: RulesRepository | None = None,
) -> Callable[[str | None, str | None, list[str] | None, str, bool], Awaitable[list[GxArtifactEnvelopeView]]]:
    async def _resolver(
        data_object_version_id: str | None,
        rule_id: str | None,
        tag_ids: list[str] | None,
        status: str,
        latest_only: bool,
    ) -> list[GxArtifactEnvelopeView]:
        normalized_tag_ids = [str(tag_id or "").strip() for tag_id in (tag_ids or []) if str(tag_id or "").strip()]
        matching_rule_ids: set[str] = set()
        if normalized_tag_ids and rules_repository is not None:
            for record in await rules_repository.list_rule_records():
                record_tag_ids = [str(tag_id or "").strip() for tag_id in (record.tag_ids or []) if str(tag_id or "").strip()]
                if set(record_tag_ids).intersection(normalized_tag_ids):
                    matching_rule_ids.add(str(record.id or "").strip())

        if data_object_version_id:
            rows = await repository.list_suites(
                data_object_id=None,
                data_object_version_id=data_object_version_id,
                dataset_id=None,
                data_product_id=None,
                status=status,
                latest_only=latest_only,
            )
        elif rule_id:
            rows = await repository.list_suites_for_rule(
                rule_id=rule_id,
                status=status,
                latest_only=latest_only,
            )
        elif matching_rule_ids:
            rows = []
            seen: set[tuple[str, int]] = set()
            for matching_rule_id in sorted(matching_rule_ids):
                rule_rows = await repository.list_suites_for_rule(
                    rule_id=matching_rule_id,
                    status=status,
                    latest_only=latest_only,
                )
                for row in rule_rows:
                    suite_key = (str(row.suiteId or ""), int(row.suiteVersion or 0))
                    if suite_key in seen:
                        continue
                    seen.add(suite_key)
                    rows.append(row)
        else:
            rows = []

        if matching_rule_ids and (data_object_version_id or rule_id):
            rows = [
                row
                for row in rows
                if matching_rule_ids.intersection({str(rule_id or "").strip() for rule_id in (row.compiledFrom.ruleIds if row.compiledFrom else []) if str(rule_id or "").strip()})
            ]
        return [GxArtifactEnvelopeView.model_validate(row) for row in rows]

    return _resolver


def bind_suite_run_dispatcher(
    *,
    request: Request,
    execution_run_repository: GxExecutionRunRepository,
    enqueue_suite_run: EnqueueSuiteRun,
) -> Callable[..., Awaitable[GxDispatchPayloadEntity]]:
    async def _dispatch(
        *,
        suite: GxArtifactEnvelopeView,
        scheduled_at: datetime,
        requested_by: str | None,
        correlation_id: str,
        execution_scope_override: list[str] | None,
        source_overrides_by_data_object_version_id: dict[str, dict[str, Any]] | None,
        status_source: str,
        status_reason: str,
    ) -> GxDispatchPayloadEntity:
        return await enqueue_suite_run(
            request=request,
            suite=suite,
            scheduled_at=scheduled_at,
            execution_run_repository=execution_run_repository,
            requested_by=requested_by,
            correlation_id=correlation_id,
            execution_scope_override=execution_scope_override,
            source_overrides_by_data_object_version_id=source_overrides_by_data_object_version_id,
            status_source=status_source,
            status_reason=status_reason,
        )

    return _dispatch


def _reject_non_runnable_suite(
    *,
    suite_id: str,
    suite_version: int | None,
    message: str,
    reason: str,
) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "error": "gx_suite_not_runnable",
            "message": message,
            "reason": reason,
            "suite_id": suite_id,
            "suite_version": suite_version,
        },
    )


async def resolve_schedulable_suite(
    *,
    suite_id: str,
    suite_version: int | None,
    status: str,
    repository: GxSuiteRepository,
) -> GxArtifactEnvelopeView:
    row = await repository.get_suite_by_id(
        suite_id=suite_id,
        suite_version=suite_version,
        status=status,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"GX suite '{suite_id}' not found")

    try:
        return GxArtifactEnvelopeView.model_validate(row)
    except ValidationError as exc:
        raise _reject_non_runnable_suite(
            suite_id=suite_id,
            suite_version=suite_version,
            message="GX suite envelope is invalid",
            reason="invalid_envelope",
        ) from exc


async def schedule_suite_run(
    *,
    request: Request,
    suite_id: str,
    suite_version: int | None,
    status: str,
    request_body: Any,
    repository: GxSuiteRepository,
    execution_run_repository: GxExecutionRunRepository,
    requested_by: str | None,
    enqueue_suite_run: EnqueueSuiteRun,
) -> ScheduleSuiteRunResult:
    suite = await resolve_schedulable_suite(
        suite_id=suite_id,
        suite_version=suite_version,
        status=status,
        repository=repository,
    )

    try:
        dispatch_payload = await schedule_gx_suite_run_use_case(
            command=build_schedule_command(
                request=request,
                suite_id=suite_id,
                suite_version=suite_version,
                status=status,
                request_body=request_body,
                requested_by=requested_by,
            ),
            resolve_suite=bind_cached_suite_resolver(suite),
            enqueue_suite_run=bind_suite_run_dispatcher(
                request=request,
                execution_run_repository=execution_run_repository,
                enqueue_suite_run=enqueue_suite_run,
            ),
        )
    except HTTPException as exc:
        raise GxScheduleSuiteRunError(status_code=exc.status_code, detail=exc.detail, suite=suite) from exc

    return ScheduleSuiteRunResult(
        suite=suite,
        dispatch_view=to_gx_suite_run_dispatch_handoff_view(dispatch_payload),
    )


async def create_adhoc_suite_runs(
    *,
    request: Request,
    request_body: Any,
    repository: GxSuiteRepository,
    rules_repository: RulesRepository | None = None,
    execution_run_repository: GxExecutionRunRepository,
    requested_by: str | None,
    enqueue_suite_run: EnqueueSuiteRun,
) -> list[GxSuiteRunDispatchHandoffView]:
    accepted_payloads = await create_adhoc_gx_suite_runs_use_case(
        command=build_adhoc_command(
            request=request,
            request_body=request_body,
            requested_by=requested_by,
        ),
        resolve_candidate_suites=bind_adhoc_candidate_suite_resolver(
            repository=repository,
            rules_repository=rules_repository,
        ),
        enqueue_suite_run=bind_suite_run_dispatcher(
            request=request,
            execution_run_repository=execution_run_repository,
            enqueue_suite_run=enqueue_suite_run,
        ),
    )
    return to_gx_suite_run_dispatch_handoff_views(accepted_payloads)