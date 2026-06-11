from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.domain.entities import DqResultEventEntity
from app.domain.entities.dq_result_event import build_dq_result_event_entity
from app.domain.interfaces import DqResultEventRepository
from app.infrastructure.orm.models import DqResultEventRow
from app.infrastructure.orm.session import session_scope


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    payload = str(value).strip()
    if not payload:
        return None
    return datetime.fromisoformat(payload.replace("Z", "+00:00"))


def _nested_value(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


class PostgresDqResultEventRepository(DqResultEventRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def record_result_event(self, event: DqResultEventEntity) -> DqResultEventEntity:
        normalized = build_dq_result_event_entity(event.model_dump(by_alias=True, exclude_none=True))
        if normalized is None:
            raise ValueError("DQ result event payload is invalid")

        payload = normalized.model_dump(by_alias=True, exclude_none=True)
        row_id = self._event_id(payload)
        with session_scope(self.database_url) as session:
            existing = session.get(DqResultEventRow, row_id)
            if existing is not None:
                if existing.event_json != payload:
                    raise ValueError(f"DQ result event '{row_id}' already exists with different payload")
                return build_dq_result_event_entity(existing.event_json) or normalized

            session.add(self._build_row(row_id, payload))
            session.commit()
        return normalized

    async def list_result_events(
        self,
        *,
        rule_id: str | None = None,
        dataset_id: str | None = None,
        domain_id: str | None = None,
        data_product_id: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        emitted_after: str | None = None,
        emitted_before: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DqResultEventEntity]:
        if limit < 0 or offset < 0:
            raise ValueError("limit and offset must be non-negative")

        after = _parse_iso_datetime(emitted_after)
        before = _parse_iso_datetime(emitted_before)

        with session_scope(self.database_url) as session:
            stmt = select(DqResultEventRow)
            if rule_id is not None:
                stmt = stmt.where(DqResultEventRow.rule_id == rule_id)
            if dataset_id is not None:
                stmt = stmt.where(DqResultEventRow.dataset_id == dataset_id)
            if domain_id is not None:
                stmt = stmt.where(DqResultEventRow.domain_id == domain_id)
            if data_product_id is not None:
                stmt = stmt.where(DqResultEventRow.dataset_data_product_id == data_product_id)
            if severity is not None:
                stmt = stmt.where(DqResultEventRow.severity == severity)
            if status is not None:
                stmt = stmt.where(DqResultEventRow.run_status == status)
            if after is not None:
                stmt = stmt.where(DqResultEventRow.emitted_at >= after)
            if before is not None:
                stmt = stmt.where(DqResultEventRow.emitted_at <= before)
            stmt = stmt.order_by(DqResultEventRow.emitted_at.desc(), DqResultEventRow.created_at.desc(), DqResultEventRow.id.desc())
            rows = session.execute(stmt).scalars().all()

        window = rows[offset : offset + limit]
        return [build_dq_result_event_entity(row.event_json) for row in window if row.event_json is not None]

    @staticmethod
    def _event_id(payload: dict[str, Any]) -> str:
        correlation_id = str(_nested_value(payload, "correlation", "correlation_id") or "")
        run_id = str(_nested_value(payload, "correlation", "run_id") or "")
        status = str(_nested_value(payload, "run_outcome", "status") or "")
        return f"{correlation_id}:{run_id}:{status}"

    @staticmethod
    def _build_row(row_id: str, payload: dict[str, Any]) -> DqResultEventRow:
        emitted_at = _parse_iso_datetime(str(payload.get("emitted_at") or "")) or datetime.now(UTC)
        run_outcome = _nested_value(payload, "run_outcome") or {}
        correlation = _nested_value(payload, "correlation") or {}
        dataset = _nested_value(payload, "dataset") or {}
        domain = _nested_value(payload, "domain") or {}
        rule = _nested_value(payload, "rule") or {}
        return DqResultEventRow(
            id=row_id,
            event_type=str(payload.get("event_type") or "dq_result_event"),
            event_version=str(payload.get("event_version") or "1"),
            emitted_at=emitted_at,
            severity=str(payload.get("severity") or "info"),
            dataset_id=str(dataset.get("id") or ""),
            dataset_name=dataset.get("name"),
            dataset_workspace_id=dataset.get("workspace_id"),
            dataset_data_product_id=dataset.get("data_product_id"),
            dataset_data_object_id=dataset.get("data_object_id"),
            dataset_data_object_version_id=dataset.get("data_object_version_id"),
            domain_id=domain.get("id"),
            domain_name=domain.get("name"),
            rule_id=str(rule.get("id") or ""),
            rule_name=rule.get("name"),
            rule_version_id=rule.get("version_id"),
            rule_version_number=rule.get("version_number"),
            run_status=str(run_outcome.get("status") or ""),
            run_result=run_outcome.get("result"),
            run_passed=run_outcome.get("passed"),
            run_total_count=run_outcome.get("total_count"),
            run_valid_count=run_outcome.get("valid_count"),
            run_invalid_count=run_outcome.get("invalid_count"),
            run_warning_count=run_outcome.get("warning_count"),
            run_error_count=run_outcome.get("error_count"),
            run_score=run_outcome.get("score"),
            run_score_label=run_outcome.get("score_label"),
            run_observed_at=_parse_iso_datetime(str(run_outcome.get("observed_at") or "")) or emitted_at,
            run_duration_ms=run_outcome.get("duration_ms"),
            run_message=run_outcome.get("message"),
            correlation_id=str(correlation.get("correlation_id") or ""),
            run_id=correlation.get("run_id"),
            request_id=correlation.get("request_id"),
            queue_message_id=correlation.get("queue_message_id"),
            trace_id=correlation.get("trace_id"),
            parent_correlation_id=correlation.get("parent_correlation_id"),
            source_system=correlation.get("source_system"),
            score_dimensions_json=payload.get("score_dimensions") or [],
            event_json=payload,
        )