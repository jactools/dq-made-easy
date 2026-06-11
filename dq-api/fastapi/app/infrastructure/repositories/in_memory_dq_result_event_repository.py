from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from app.domain.entities import DqResultEventEntity
from app.domain.entities.dq_result_event import build_dq_result_event_entity
from app.domain.interfaces import DqResultEventRepository


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


class InMemoryDqResultEventRepository(DqResultEventRepository):
    def __init__(self) -> None:
        self._events: dict[str, dict[str, Any]] = {}

    async def record_result_event(self, event: DqResultEventEntity) -> DqResultEventEntity:
        normalized = build_dq_result_event_entity(event.model_dump(by_alias=True, exclude_none=True))
        if normalized is None:
            raise ValueError("DQ result event payload is invalid")

        payload = normalized.model_dump(by_alias=True, exclude_none=True)
        event_id = self._event_id(payload)
        existing = self._events.get(event_id)
        if existing is not None:
            if existing != payload:
                raise ValueError(f"DQ result event '{event_id}' already exists with different payload")
            return build_dq_result_event_entity(existing) or normalized

        self._events[event_id] = deepcopy(payload)
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

        rows = [payload for payload in self._events.values() if self._matches(payload, rule_id, dataset_id, domain_id, data_product_id, severity, status, after, before)]
        rows.sort(
            key=lambda payload: (
                _parse_iso_datetime(str(payload.get("emitted_at") or "")) or datetime.min.replace(tzinfo=UTC),
                str(_nested_value(payload, "correlation", "run_id") or ""),
            ),
            reverse=True,
        )
        window = rows[offset : offset + limit]
        events: list[DqResultEventEntity] = []
        for payload in window:
            event = build_dq_result_event_entity(payload)
            if event is not None:
                events.append(event)
        return events

    @staticmethod
    def _event_id(payload: dict[str, Any]) -> str:
        correlation_id = str(_nested_value(payload, "correlation", "correlation_id") or "")
        run_id = str(_nested_value(payload, "correlation", "run_id") or "")
        status = str(_nested_value(payload, "run_outcome", "status") or "")
        return f"{correlation_id}:{run_id}:{status}"

    @staticmethod
    def _matches(
        payload: dict[str, Any],
        rule_id: str | None,
        dataset_id: str | None,
        domain_id: str | None,
        data_product_id: str | None,
        severity: str | None,
        status: str | None,
        emitted_after: datetime | None,
        emitted_before: datetime | None,
    ) -> bool:
        if rule_id is not None and str(_nested_value(payload, "rule", "id") or "") != rule_id:
            return False
        if dataset_id is not None and str(_nested_value(payload, "dataset", "id") or "") != dataset_id:
            return False
        if domain_id is not None and str(_nested_value(payload, "domain", "id") or "") != domain_id:
            return False
        if data_product_id is not None and str(_nested_value(payload, "dataset", "data_product_id") or "") != data_product_id:
            return False
        if severity is not None and str(payload.get("severity") or "") != severity:
            return False
        if status is not None and str(_nested_value(payload, "run_outcome", "status") or "") != status:
            return False

        emitted_at = _parse_iso_datetime(str(payload.get("emitted_at") or ""))
        if emitted_after is not None and (emitted_at is None or emitted_at < emitted_after):
            return False
        if emitted_before is not None and (emitted_at is None or emitted_at > emitted_before):
            return False
        return True