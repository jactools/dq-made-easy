"""Tests for the Delivery Registry app."""

from __future__ import annotations

import pytest

from metadata_sdk.domain.models.delivery_types import DeliveryStatus
from metadata_sdk.domain.models.delivery_types import DeliveryType


def test_delivery_app_imports() -> None:
    """Verify Delivery app can be imported."""
    from delivery.main import get_app
    delivery_app = get_app()
    assert delivery_app.title == "Delivery — Canonical Delivery Registry"


def test_delivery_app_has_routes() -> None:
    """Verify Delivery app has routes."""
    from delivery.main import get_app
    delivery_app = get_app()
    routes = [r for r in delivery_app.routes if hasattr(r, 'path')]
    assert any('/health' in r.path for r in routes)
    assert any('/v1' in r.path for r in routes)


def test_delivery_repository_imports() -> None:
    """Verify Delivery repository can be imported."""
    from delivery.repository import InMemoryDeliveryRepository
    repo = InMemoryDeliveryRepository()
    assert repo is not None


def test_delivery_entities_imports() -> None:
    """Verify Delivery entities can be imported."""
    from delivery.domain.entities import (
        DeliveryEntity,
        DeliveryErrorEntity,
        DeliveryLifecycleEventEntity,
        DeliveryMetadataEntity,
        DeliveryPageEntity,
    )
    # Verify entities can be created
    delivery = DeliveryEntity(
        delivery_id="test-delivery",
        delivery_time_event="test-event",
        producer_system="test-system",
        data_object_logical_name="test-object",
        job_id="test-job",
        delivered_at="2026-07-21T00:00:00Z",
    )
    assert delivery.delivery_id == "test-delivery"
    assert delivery.delivery_type == DeliveryType.INITIAL
    assert delivery.status == DeliveryStatus.REGISTERED
