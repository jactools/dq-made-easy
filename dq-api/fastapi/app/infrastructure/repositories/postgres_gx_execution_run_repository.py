from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.domain.entities import (
    GxExecutionRunCreateEntity,
    GxExecutionRunEntity,
    GxExecutionRunListQueryEntity,
    GxExecutionRunStatusHistoryEntity,
    GxExecutionRunStatusTransitionEntity,
)
from app.domain.entities.gx_execution_run import (
    build_gx_execution_run_entity,
    build_gx_execution_run_list_query_entity,
    build_gx_execution_run_status_history_entity,
)
from app.domain.interfaces import GxExecutionRunRepository
from app.infrastructure.orm.models import GxExecutionRunRow
from app.infrastructure.orm.models import GxExecutionRunStatusHistoryRow
from app.infrastructure.orm.session import session_scope


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    payload = str(value).strip()
    if not payload:
        return None
    return datetime.fromisoformat(payload.replace("Z", "+00:00"))


def _format_iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


class PostgresGxExecutionRunRepository(GxExecutionRunRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def create_run(self, run: GxExecutionRunCreateEntity) -> GxExecutionRunEntity:
        with session_scope(self.database_url) as session:
            if session.get(GxExecutionRunRow, run.runId) is not None:
                raise ValueError(f"GX execution run '{run.runId}' already exists")

            now = datetime.now(UTC)
            run_row = GxExecutionRunRow(
                id=run.runId,
                suite_id=run.suiteId,
                suite_version=run.suiteVersion,
                rule_id=run.ruleId,
                rule_version_id=run.ruleVersionId,
                correlation_id=run.correlationId,
                requested_by=run.requestedBy,
                engine_type=run.engineType,
                engine_target=run.engineTarget,
                execution_shape=run.executionShape,
                status=run.status,
                submitted_at=_parse_iso_datetime(run.submittedAt) or now,
                started_at=_parse_iso_datetime(run.startedAt),
                completed_at=_parse_iso_datetime(run.completedAt),
                execution_progress_json=dict(run.executionProgress) if run.executionProgress is not None else None,
                execution_contract_json=run.executionContract.model_dump(by_alias=True, exclude_none=True),
                handoff_payload_json=(
                    run.handoffPayload.model_dump(by_alias=True, exclude_none=True)
                    if run.handoffPayload is not None
                    else None
                ),
                result_summary_json=(
                    run.resultSummary.model_dump(by_alias=True, exclude_none=True)
                    if run.resultSummary is not None
                    else {}
                ),
                metrics_json=(dict(run.metrics or run.performanceSummary or {}) or None),
                diagnostics_json=[
                    item.model_dump(by_alias=True, exclude_none=True) for item in run.diagnostics or []
                ],
                failure_code=run.failureCode,
                failure_message=run.failureMessage,
                comments=run.comments,
                created_at=now,
                updated_at=now,
            )
            session.add(run_row)
            session.flush()

            session.add(
                GxExecutionRunStatusHistoryRow(
                    id=f"gx-run-hist-{uuid4().hex}",
                    run_id=run.runId,
                    from_status=None,
                    to_status=run.status,
                    changed_by=run.requestedBy,
                    reason=run.statusReason,
                    details=dict(run.statusDetails or {}),
                )
            )
            session.commit()

        run = await self.get_run(run.runId)
        if run is None:
            raise RuntimeError(f"GX execution run '{run.runId}' was not persisted")
        return run

    async def get_run(self, run_id: str) -> GxExecutionRunEntity | None:
        with session_scope(self.database_url) as session:
            run_row = session.get(GxExecutionRunRow, run_id)
            if run_row is None:
                return None

            history_stmt = (
                select(GxExecutionRunStatusHistoryRow)
                .where(GxExecutionRunStatusHistoryRow.run_id == run_id)
                .order_by(GxExecutionRunStatusHistoryRow.changed_at.asc())
            )
            history_rows = session.execute(history_stmt).scalars().all()

        return build_gx_execution_run_entity(self._serialize_run(run_row, history_rows))

    async def list_runs(
        self,
        query: GxExecutionRunListQueryEntity | Mapping[str, Any],
    ) -> list[GxExecutionRunEntity]:
        normalized_query = build_gx_execution_run_list_query_entity(query)
        with session_scope(self.database_url) as session:
            stmt = select(GxExecutionRunRow)
            if normalized_query.submittedAfter is not None:
                stmt = stmt.where(GxExecutionRunRow.submitted_at >= normalized_query.submittedAfter)
            if normalized_query.submittedBefore is not None:
                stmt = stmt.where(GxExecutionRunRow.submitted_at <= normalized_query.submittedBefore)
            if normalized_query.suiteId is not None:
                stmt = stmt.where(GxExecutionRunRow.suite_id == normalized_query.suiteId)
            if normalized_query.ruleId is not None:
                stmt = stmt.where(GxExecutionRunRow.rule_id == normalized_query.ruleId)
            if normalized_query.status is not None:
                stmt = stmt.where(GxExecutionRunRow.status == normalized_query.status)
            stmt = stmt.order_by(GxExecutionRunRow.submitted_at.desc(), GxExecutionRunRow.created_at.desc())
            rows = session.execute(stmt).scalars().all()

        return [build_gx_execution_run_entity(self._serialize_run(row, [])) for row in rows]

    async def list_run_status_history(self, run_id: str) -> list[GxExecutionRunStatusHistoryEntity]:
        with session_scope(self.database_url) as session:
            history_stmt = (
                select(GxExecutionRunStatusHistoryRow)
                .where(GxExecutionRunStatusHistoryRow.run_id == run_id)
                .order_by(GxExecutionRunStatusHistoryRow.changed_at.asc())
            )
            history_rows = session.execute(history_stmt).scalars().all()
        return [build_gx_execution_run_status_history_entity(self._serialize_history(row)) for row in history_rows]

    async def record_run_status_transition(
        self,
        transition: GxExecutionRunStatusTransitionEntity,
    ) -> GxExecutionRunEntity:
        with session_scope(self.database_url) as session:
            run_row = session.get(GxExecutionRunRow, transition.runId)
            if run_row is None:
                raise ValueError(f"GX execution run '{transition.runId}' not found")

            old_status = str(run_row.status or "") or None
            run_row.status = transition.newStatus
            if transition.startedAt is not None:
                run_row.started_at = _parse_iso_datetime(transition.startedAt)
            if transition.completedAt is not None:
                run_row.completed_at = _parse_iso_datetime(transition.completedAt)
            if transition.executionProgress is not None:
                run_row.execution_progress_json = dict(transition.executionProgress)
            if transition.newStatus == "running" and run_row.started_at is None:
                run_row.started_at = datetime.now(UTC)
            if transition.newStatus in {"succeeded", "failed", "cancelled"} and run_row.completed_at is None:
                run_row.completed_at = datetime.now(UTC)

            if transition.resultSummary is not None:
                run_row.result_summary_json = transition.resultSummary.model_dump(by_alias=True, exclude_none=True)
            if transition.metrics is not None:
                run_row.metrics_json = dict(transition.metrics)
            elif transition.performanceSummary is not None:
                run_row.metrics_json = dict(transition.performanceSummary)
            if transition.diagnostics is not None:
                run_row.diagnostics_json = [
                    item.model_dump(by_alias=True, exclude_none=True) for item in transition.diagnostics
                ]
            if transition.failureCode is not None:
                run_row.failure_code = transition.failureCode
            if transition.failureMessage is not None:
                run_row.failure_message = transition.failureMessage
            run_row.updated_at = datetime.now(UTC)

            if old_status != transition.newStatus:
                session.add(
                    GxExecutionRunStatusHistoryRow(
                        id=f"gx-run-hist-{uuid4().hex}",
                        run_id=transition.runId,
                        from_status=old_status,
                        to_status=transition.newStatus,
                        changed_by=transition.changedBy,
                        reason=transition.reason,
                        details=dict(transition.details or {}),
                    )
                )
            session.commit()

        run = await self.get_run(transition.runId)
        if run is None:
            raise RuntimeError(f"GX execution run '{transition.runId}' was not persisted")
        return run

    async def update_run_comments(self, run_id: str, comments: str | None) -> GxExecutionRunEntity | None:
        with session_scope(self.database_url) as session:
            run_row = session.get(GxExecutionRunRow, run_id)
            if run_row is None:
                return None

            run_row.comments = str(comments or "").strip() or None
            run_row.updated_at = datetime.now(UTC)
            session.commit()

        return await self.get_run(run_id)

    @staticmethod
    def _serialize_history(row: GxExecutionRunStatusHistoryRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "runId": row.run_id,
            "fromStatus": row.from_status,
            "toStatus": row.to_status,
            "changedBy": row.changed_by,
            "changedAt": _format_iso_datetime(row.changed_at),
            "reason": row.reason,
            "details": row.details or {},
        }

    def _serialize_run(
        self,
        row: GxExecutionRunRow,
        history_rows: list[GxExecutionRunStatusHistoryRow],
    ) -> dict[str, Any]:
        return {
            "id": row.id,
            "suiteId": row.suite_id,
            "suiteVersion": row.suite_version,
            "ruleId": row.rule_id,
            "ruleVersionId": row.rule_version_id,
            "correlationId": row.correlation_id,
            "requestedBy": row.requested_by,
            "engineType": row.engine_type,
            "engineTarget": row.engine_target,
            "executionShape": row.execution_shape,
            "status": row.status,
            "submittedAt": _format_iso_datetime(row.submitted_at),
            "startedAt": _format_iso_datetime(row.started_at),
            "completedAt": _format_iso_datetime(row.completed_at),
            "createdAt": _format_iso_datetime(row.created_at) or "",
            "updatedAt": _format_iso_datetime(row.updated_at) or "",
            "executionProgress": dict(row.execution_progress_json or {}) if row.execution_progress_json is not None else None,
            "executionContract": dict(row.execution_contract_json or {}),
            "handoffPayload": dict(row.handoff_payload_json or {}) if row.handoff_payload_json is not None else None,
            "resultSummary": dict(row.result_summary_json or {}),
            "metrics": dict(getattr(row, "metrics_json", None) or {}) if getattr(row, "metrics_json", None) is not None else None,
            "performanceSummary": dict(getattr(row, "metrics_json", None) or {}) if getattr(row, "metrics_json", None) is not None else None,
            "diagnostics": list(row.diagnostics_json or []),
            "failureCode": row.failure_code,
            "failureMessage": row.failure_message,
            "comments": getattr(row, "comments", None),
            "statusHistory": [self._serialize_history(history_row) for history_row in history_rows],
        }
