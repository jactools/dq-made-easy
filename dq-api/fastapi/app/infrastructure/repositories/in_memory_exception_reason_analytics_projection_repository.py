from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime

from app.application.services.exception_reason_analytics_projection import build_reason_analytics_projection_rows
from app.application.services.exception_reason_analytics_projection import summarize_reason_analytics_projection_rows
from app.domain.entities import ExceptionRecordCreateEntity
from app.domain.entities.gx_execution_violation import GxExecutionViolationSummaryEntity
from app.domain.interfaces.v1.exception_reason_analytics_projection_repository import ExceptionReasonAnalyticsProjectionRepository


class InMemoryExceptionReasonAnalyticsProjectionRepository(ExceptionReasonAnalyticsProjectionRepository):
    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}

    async def persist_exception_records(self, exception_records: Sequence[ExceptionRecordCreateEntity]) -> int:
        projection_rows = build_reason_analytics_projection_rows(exception_records)
        now = datetime.now(UTC).isoformat()

        for row in projection_rows:
            existing = self._rows.get(str(row["id"]))
            if existing is None:
                stored = deepcopy(row)
                stored["created_at"] = now
                stored["updated_at"] = now
                self._rows[str(row["id"])] = stored
                continue

            existing_record_identifiers = set(str(value).strip() for value in existing.get("record_identifier_values") or [] if str(value).strip())
            existing_execution_run_ids = set(str(value).strip() for value in existing.get("execution_run_ids") or [] if str(value).strip())
            existing_record_identifiers.update(str(value).strip() for value in row.get("record_identifier_values") or [] if str(value).strip())
            existing_execution_run_ids.update(str(value).strip() for value in row.get("execution_run_ids") or [] if str(value).strip())
            existing["failed_record_count"] = int(existing.get("failed_record_count") or 0) + int(row.get("failed_record_count") or 0)
            existing["record_identifier_values"] = sorted(existing_record_identifiers)
            existing["execution_run_ids"] = sorted(existing_execution_run_ids)
            existing["distinct_record_identifier_count"] = len(existing_record_identifiers)
            existing["distinct_execution_run_count"] = len(existing_execution_run_ids)
            existing["updated_at"] = now
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
        return summarize_reason_analytics_projection_rows(
            list(self._rows.values()),
            data_object_version_ids=data_object_version_ids,
            execution_run_ids=execution_run_ids,
            reason_codes=reason_codes,
            detected_after=detected_after,
            detected_before=detected_before,
            bucket_origin=bucket_origin,
            bucket_size_seconds=bucket_size_seconds,
            bucket_count=bucket_count,
        )
