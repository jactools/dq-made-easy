from collections.abc import Sequence
from typing import Protocol

from app.domain.entities import (
    GxExecutionViolationCreateEntity,
    GxExecutionViolationEntity,
    GxExecutionViolationListEntity,
    GxExecutionViolationSummaryEntity,
)


class ExceptionFactRepository(Protocol):
    async def save_violation(
        self,
        *,
        data_object_version_id: str,
        execution_run_id: str,
        rule_id: str,
        data_primary_key: str,
        violation_reason: str,
        ops_metadata: dict | None = None,
        detected_at: str | None = None,
        violation_id: str | None = None,
    ) -> GxExecutionViolationEntity:
        ...

    async def save_violations(
        self,
        violations: Sequence[GxExecutionViolationCreateEntity],
    ) -> list[GxExecutionViolationEntity]:
        ...

    async def get_violation(self, data_object_version_id: str, violation_id: str) -> GxExecutionViolationEntity | None:
        ...

    async def list_violations(
        self,
        data_object_version_id: str,
        execution_run_id: str | None = None,
        rule_id: str | None = None,
        reason_codes: Sequence[str] | None = None,
        failure_class: str | None = None,
        record_identifier_type: str | None = None,
        record_identifier_value_contains: str | None = None,
        search: str | None = None,
        detected_after: str | None = None,
        detected_before: str | None = None,
        hash_stripe: int | None = None,
        hash_stripe_count: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> GxExecutionViolationListEntity:
        ...

    async def summarize_violations(
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

    async def delete_violations_detected_before(
        self,
        *,
        detected_before: str,
        limit: int = 1000,
        data_object_version_id: str | None = None,
    ) -> int:
        ...