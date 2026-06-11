from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select

from app.application.services.exception_reason_analytics_projection import build_reason_analytics_projection_rows
from app.application.services.exception_reason_analytics_projection import summarize_reason_analytics_projection_rows
from app.domain.entities import ExceptionRecordCreateEntity
from app.domain.entities.gx_execution_violation import GxExecutionViolationSummaryEntity
from app.domain.interfaces.v1.exception_reason_analytics_projection_repository import ExceptionReasonAnalyticsProjectionRepository
from app.infrastructure.orm.models import ExceptionReasonAnalyticsProjectionRow
from app.infrastructure.orm.session import session_scope


def _to_row_dict(row: ExceptionReasonAnalyticsProjectionRow) -> dict:
    return {
        "id": row.id,
        "bucket_start": row.bucket_start.isoformat() if row.bucket_start.tzinfo is not None else row.bucket_start.replace(tzinfo=UTC).isoformat(),
        "engine_type": row.engine_type,
        "delivery_id": row.delivery_id,
        "execution_plan_id": row.execution_plan_id,
        "execution_plan_version_id": row.execution_plan_version_id,
        "suite_id": row.suite_id,
        "data_object_version_id": row.data_object_version_id,
        "rule_id": row.rule_id,
        "rule_version_id": row.rule_version_id,
        "reason_code": row.reason_code,
        "reason_text_snapshot": row.reason_text_snapshot,
        "failed_record_count": int(row.failed_record_count or 0),
        "distinct_record_identifier_count": int(row.distinct_record_identifier_count or 0),
        "distinct_execution_run_count": int(row.distinct_execution_run_count or 0),
        "record_identifier_values": list(row.record_identifier_values_json or []),
        "execution_run_ids": list(row.execution_run_ids_json or []),
        "detected_at": row.bucket_start.isoformat() if row.bucket_start.tzinfo is not None else row.bucket_start.replace(tzinfo=UTC).isoformat(),
        "created_at": row.created_at.isoformat() if row.created_at.tzinfo is not None else row.created_at.replace(tzinfo=UTC).isoformat(),
        "updated_at": row.updated_at.isoformat() if row.updated_at.tzinfo is not None else row.updated_at.replace(tzinfo=UTC).isoformat(),
    }


class PostgresExceptionReasonAnalyticsProjectionRepository(ExceptionReasonAnalyticsProjectionRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def persist_exception_records(self, exception_records: Sequence[ExceptionRecordCreateEntity]) -> int:
        projection_rows = build_reason_analytics_projection_rows(exception_records)
        if not projection_rows:
            return 0

        now = datetime.now(UTC)
        with session_scope(self.database_url) as session:
            for row in projection_rows:
                existing = session.get(ExceptionReasonAnalyticsProjectionRow, row["id"])
                if existing is None:
                    session.add(
                        ExceptionReasonAnalyticsProjectionRow(
                            id=str(row["id"]),
                            bucket_start=_parse_iso_datetime(str(row["bucket_start"] or "")),
                            engine_type=str(row["engine_type"]),
                            delivery_id=row.get("delivery_id"),
                            execution_plan_id=row.get("execution_plan_id"),
                            execution_plan_version_id=row.get("execution_plan_version_id"),
                            suite_id=row.get("suite_id"),
                            data_object_version_id=str(row["data_object_version_id"]),
                            rule_id=str(row["rule_id"]),
                            rule_version_id=row.get("rule_version_id"),
                            reason_code=str(row["reason_code"]),
                            reason_text_snapshot=str(row["reason_text_snapshot"]),
                            failed_record_count=int(row.get("failed_record_count") or 0),
                            distinct_record_identifier_count=int(row.get("distinct_record_identifier_count") or 0),
                            distinct_execution_run_count=int(row.get("distinct_execution_run_count") or 0),
                            record_identifier_values_json=list(row.get("record_identifier_values") or []),
                            execution_run_ids_json=list(row.get("execution_run_ids") or []),
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    continue

                existing_record_identifiers = set(str(value).strip() for value in existing.record_identifier_values_json or [] if str(value).strip())
                existing_execution_run_ids = set(str(value).strip() for value in existing.execution_run_ids_json or [] if str(value).strip())
                existing_record_identifiers.update(str(value).strip() for value in row.get("record_identifier_values") or [] if str(value).strip())
                existing_execution_run_ids.update(str(value).strip() for value in row.get("execution_run_ids") or [] if str(value).strip())
                existing.failed_record_count = int(existing.failed_record_count or 0) + int(row.get("failed_record_count") or 0)
                existing.record_identifier_values_json = sorted(existing_record_identifiers)
                existing.execution_run_ids_json = sorted(existing_execution_run_ids)
                existing.distinct_record_identifier_count = len(existing_record_identifiers)
                existing.distinct_execution_run_count = len(existing_execution_run_ids)
                existing.updated_at = now
            session.commit()
        return len(projection_rows)

    async def summarize_reason_analytics(
        self,
        *,
        data_object_version_ids: Sequence[str],
        execution_run_ids: Sequence[str],
        reason_codes: Sequence[str] | None = None,
        detected_after: str | None = None,
        detected_before: str | None = None,
        bucket_origin: str | None = None,
        bucket_size_seconds: int | None = None,
        bucket_count: int | None = None,
    ) -> GxExecutionViolationSummaryEntity:
        with session_scope(self.database_url) as session:
            rows = session.execute(select(ExceptionReasonAnalyticsProjectionRow)).scalars().all()
        return summarize_reason_analytics_projection_rows(
            [_to_row_dict(row) for row in rows],
            data_object_version_ids=data_object_version_ids,
            execution_run_ids=execution_run_ids,
            reason_codes=reason_codes,
            detected_after=detected_after,
            detected_before=detected_before,
            bucket_origin=bucket_origin,
            bucket_size_seconds=bucket_size_seconds,
            bucket_count=bucket_count,
        )


def _parse_iso_datetime(value: str | None):
    if value is None:
        return datetime.now(UTC)
    payload = str(value).strip()
    if not payload:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(payload.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
