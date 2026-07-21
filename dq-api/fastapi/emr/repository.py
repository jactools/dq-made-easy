"""In-memory EMR repository for the Canonical Delivery Registry.

Provides a mock implementation for testing and development.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from emr.domain.entities import (
    EmrDeliveryEntity,
    EmrDeliveryErrorEntity,
    EmrDeliveryLifecycleEventEntity,
    EmrDeliveryMetadataEntity,
    EmrDeliveryPageEntity,
)
from emr_delivery_sdk import (DeliveryId, DeliveryIdBuilder, generate_delivery_time_event)


class InMemoryEmrRepository:
    """In-memory implementation of EmrRepository."""

    def __init__(self) -> None:
        self._deliveries: dict[str, EmrDeliveryEntity] = {}
        self._lifecycle_events: list[EmrDeliveryLifecycleEventEntity] = []
        self._errors: list[EmrDeliveryErrorEntity] = []
        self._metadata: dict[str, EmrDeliveryMetadataEntity] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def register_delivery(self, delivery: EmrDeliveryEntity) -> EmrDeliveryEntity:
        now = self._now()
        if not delivery.created_at:
            delivery.created_at = now
        if not delivery.updated_at:
            delivery.updated_at = now
        self._deliveries[delivery.delivery_time_event] = delivery

        # Record lifecycle event
        event = EmrDeliveryLifecycleEventEntity(
            id=f"evt-{uuid.uuid4().hex[:12]}",
            delivery_time_event=delivery.delivery_time_event,
            event_type="registered",
            event_kind="instantaneous",
            occurred_at=now,
            triggered_by="emr",
            created_at=now,
        )
        self._lifecycle_events.append(event)
        return delivery

    def get_delivery(self, delivery_time_event: str) -> EmrDeliveryEntity | None:
        return self._deliveries.get(delivery_time_event)

    def get_deliveries_by_stream(
        self, delivery_id: str, *, page: int = 1, limit: int = 100
    ) -> EmrDeliveryPageEntity:
        items = [
            d for d in self._deliveries.values() if d.delivery_id == delivery_id
        ]
        total = len(items)
        start = (page - 1) * limit
        end = start + limit
        return EmrDeliveryPageEntity(
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
    ) -> EmrDeliveryPageEntity:
        items = list(self._deliveries.values())
        if producer_system:
            items = [d for d in items if d.producer_system == producer_system]
        if data_object_logical_name:
            items = [d for d in items if d.data_object_logical_name == data_object_logical_name]
        if delivery_type:
            items = [d for d in items if d.delivery_type == delivery_type]
        if status:
            items = [d for d in items if d.status == status]

        total = len(items)
        start = (page - 1) * limit
        end = start + limit
        return EmrDeliveryPageEntity(
            items=items[start:end],
            total=total,
            page=page,
            limit=limit,
        )

    def update_delivery_status(
        self, delivery_time_event: str, status: str, *, reason: str | None = None
    ) -> EmrDeliveryEntity | None:
        delivery = self._deliveries.get(delivery_time_event)
        if delivery is None:
            return None

        now = self._now()
        delivery.status = status
        delivery.updated_at = now

        # Record lifecycle event
        event = EmrDeliveryLifecycleEventEntity(
            id=f"evt-{uuid.uuid4().hex[:12]}",
            delivery_time_event=delivery_time_event,
            event_type=status,
            event_kind="instantaneous",
            occurred_at=now,
            triggered_by="emr",
            created_at=now,
            metadata_json={"reason": reason} if reason else None,
        )
        self._lifecycle_events.append(event)
        return delivery

    def record_lifecycle_event(
        self, event: EmrDeliveryLifecycleEventEntity
    ) -> EmrDeliveryLifecycleEventEntity:
        if not event.id:
            event.id = f"evt-{uuid.uuid4().hex[:12]}"
        if not event.created_at:
            event.created_at = self._now()
        self._lifecycle_events.append(event)
        return event

    def get_lifecycle_events(
        self, delivery_time_event: str
    ) -> list[EmrDeliveryLifecycleEventEntity]:
        return [
            e for e in self._lifecycle_events
            if e.delivery_time_event == delivery_time_event
        ]

    def record_error(self, error: EmrDeliveryErrorEntity) -> EmrDeliveryErrorEntity:
        if not error.id:
            error.id = f"err-{uuid.uuid4().hex[:12]}"
        if not error.created_at:
            error.created_at = self._now()
        self._errors.append(error)
        return error

    def get_errors(self, delivery_time_event: str) -> list[EmrDeliveryErrorEntity]:
        return [e for e in self._errors if e.delivery_time_event == delivery_time_event]

    def upsert_metadata(
        self, metadata: EmrDeliveryMetadataEntity
    ) -> EmrDeliveryMetadataEntity:
        now = self._now()
        if not metadata.created_at:
            metadata.created_at = now
        if not metadata.updated_at:
            metadata.updated_at = now
        self._metadata[metadata.delivery_time_event] = metadata
        return metadata

    def get_metadata(self, delivery_time_event: str) -> EmrDeliveryMetadataEntity | None:
        return self._metadata.get(delivery_time_event)
