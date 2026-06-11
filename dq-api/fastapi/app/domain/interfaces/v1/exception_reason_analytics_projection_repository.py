from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.domain.entities import ExceptionRecordCreateEntity
from app.domain.entities.gx_execution_violation import GxExecutionViolationSummaryEntity


class ExceptionReasonAnalyticsProjectionRepository(Protocol):
    async def persist_exception_records(self, exception_records: Sequence[ExceptionRecordCreateEntity]) -> int:
        ...

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
        ...
