"""In-memory Delivery repository for the Canonical Delivery Registry.

Provides a mock implementation for testing and development.
Uses metadata-utils for UUIDv7 generation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from delivery.domain.dq_result import DeliveryResultEntity, DeliveryResultPageEntity
from delivery.domain.entities import (
    DeliveryEntity,
    DeliveryErrorEntity,
    DeliveryLifecycleEventEntity,
    DeliveryMetadataEntity,
    DeliveryPageEntity,
)
from metadata_utils import generate_uuid7


class InMemoryDeliveryRepository:
    """In-memory implementation of EmrRepository."""

    def __init__(self) -> None:
        self._deliveries: dict[str, DeliveryEntity] = {}
        self._lifecycle_events: list[DeliveryLifecycleEventEntity] = []
        self._errors: list[DeliveryErrorEntity] = []
        self._metadata: dict[str, DeliveryMetadataEntity] = {}
        self._dq_results: list[DeliveryResultEntity] = []

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def register_delivery(self, delivery: DeliveryEntity) -> DeliveryEntity:
        now = self._now()
        if not delivery.created_at:
            delivery.created_at = now
        if not delivery.updated_at:
            delivery.updated_at = now
        self._deliveries[delivery.delivery_time_event] = delivery

        # Record lifecycle event with UUIDv7 ID
        event = DeliveryLifecycleEventEntity(
            id=f"evt-{generate_uuid7()}",
            delivery_time_event=delivery.delivery_time_event,
            event_type="registered",
            event_kind="instantaneous",
            occurred_at=now,
            triggered_by="delivery",
            created_at=now,
        )
        self._lifecycle_events.append(event)
        return delivery

    def get_delivery(self, delivery_time_event: str) -> DeliveryEntity | None:
        return self._deliveries.get(delivery_time_event)

    def get_deliveries_by_stream(
        self, delivery_id: str, *, page: int = 1, limit: int = 100
    ) -> DeliveryPageEntity:
        items = [
            d for d in self._deliveries.values() if d.delivery_id == delivery_id
        ]
        total = len(items)
        start = (page - 1) * limit
        end = start + limit
        return DeliveryPageEntity(
            items=items[start:end],
            total=total,
            page=page,
            limit=limit,
        )

    def query_deliveries(
        self,
        *,
        producer_system: str | None = None,
        data_object_logical_name: str | None = None,
        delivery_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        limit: int = 100,
    ) -> DeliveryPageEntity:
        items = list(self._deliveries.values())
        if producer_system:
            items = [d for d in items if d.producer_system == producer_system]
        if data_object_logical_name:
            items = [d for d in items if d.data_object_logical_name == data_object_logical_name]
        if delivery_type:
            items = [d for d in items if d.delivery_type.value == delivery_type]
        if status:
            items = [d for d in items if d.status.value == status]

        total = len(items)
        start = (page - 1) * limit
        end = start + limit
        return DeliveryPageEntity(
            items=items[start:end],
            total=total,
            page=page,
            limit=limit,
        )

    def update_delivery_status(
        self, delivery_time_event: str, status: str, *, reason: str | None = None
    ) -> DeliveryEntity | None:
        delivery = self._deliveries.get(delivery_time_event)
        if delivery is None:
            return None

        now = self._now()
        delivery.status = status
        delivery.updated_at = now

        # Record lifecycle event with UUIDv7 ID
        event = DeliveryLifecycleEventEntity(
            id=f"evt-{generate_uuid7()}",
            delivery_time_event=delivery_time_event,
            event_type=status,
            event_kind="instantaneous",
            occurred_at=now,
            triggered_by="delivery",
            created_at=now,
            metadata_json={"reason": reason} if reason else None,
        )
        self._lifecycle_events.append(event)
        return delivery

    def record_lifecycle_event(
        self, event: DeliveryLifecycleEventEntity
    ) -> DeliveryLifecycleEventEntity:
        if not event.id:
            event.id = f"evt-{generate_uuid7()}"
        if not event.created_at:
            event.created_at = self._now()
        self._lifecycle_events.append(event)
        return event

    def get_lifecycle_events(
        self, delivery_time_event: str
    ) -> list[DeliveryLifecycleEventEntity]:
        return [
            e for e in self._lifecycle_events
            if e.delivery_time_event == delivery_time_event
        ]

    def record_error(self, error: DeliveryErrorEntity) -> DeliveryErrorEntity:
        if not error.id:
            error.id = f"err-{generate_uuid7()}"
        if not error.created_at:
            error.created_at = self._now()
        self._errors.append(error)
        return error

    def get_errors(self, delivery_time_event: str) -> list[DeliveryErrorEntity]:
        return [e for e in self._errors if e.delivery_time_event == delivery_time_event]

    def upsert_metadata(
        self, metadata: DeliveryMetadataEntity
    ) -> DeliveryMetadataEntity:
        now = self._now()
        if not metadata.created_at:
            metadata.created_at = now
        if not metadata.updated_at:
            metadata.updated_at = now
        self._metadata[metadata.delivery_time_event] = metadata
        return metadata

    def get_metadata(self, delivery_time_event: str) -> DeliveryMetadataEntity | None:
        return self._metadata.get(delivery_time_event)

    # ------------------------------------------------------------------
    # DQ Results
    # ------------------------------------------------------------------

    def store_dq_result(self, result: DeliveryResultEntity) -> DeliveryResultEntity:
        """Store a DQ result linked to a delivery."""
        now = self._now()
        if not result.id:
            result.id = f"dq-{generate_uuid7()}"
        if not result.created_at:
            result.created_at = now
        self._dq_results.append(result)
        return result

    def get_dq_results_by_delivery(
        self,
        delivery_time_event: str,
        *,
        page: int = 1,
        limit: int = 100,
    ) -> DeliveryResultPageEntity:
        """Get all DQ results for a specific delivery occurrence."""
        items = [
            r for r in self._dq_results
            if r.delivery_time_event == delivery_time_event
        ]
        total = len(items)
        start = (page - 1) * limit
        end = start + limit
        return DeliveryResultPageEntity(
            items=items[start:end],
            total=total,
            page=page,
            limit=limit,
        )

    def get_dq_results_by_stream(
        self,
        delivery_id: str,
        *,
        page: int = 1,
        limit: int = 100,
    ) -> DeliveryResultPageEntity:
        """Get all DQ results for a delivery stream (all occurrences)."""
        items = [r for r in self._dq_results if r.delivery_id == delivery_id]
        total = len(items)
        start = (page - 1) * limit
        end = start + limit
        return DeliveryResultPageEntity(
            items=items[start:end],
            total=total,
            page=page,
            limit=limit,
        )
