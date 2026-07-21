"""Tests for the EMR (Enterprise Metadata Registry) app."""

from __future__ import annotations

import pytest


def test_emr_app_imports() -> None:
    """Verify EMR app can be imported."""
    from emr.main import get_app
    emr_app = get_app()
    assert emr_app.title == "EMR — Canonical Delivery Registry"


def test_emr_app_has_routes() -> None:
    """Verify EMR app has routes."""
    from emr.main import get_app
    emr_app = get_app()
    routes = [r for r in emr_app.routes if hasattr(r, 'path')]
    assert any('/health' in r.path for r in routes)
    assert any('/v1' in r.path for r in routes)


def test_emr_repository_imports() -> None:
    """Verify EMR repository can be imported."""
    from emr.repository import InMemoryEmrRepository
    repo = InMemoryEmrRepository()
    assert repo is not None


def test_emr_entities_imports() -> None:
    """Verify EMR entities can be imported."""
    from emr.domain.entities import (
        EmrDeliveryEntity,
        EmrDeliveryErrorEntity,
        EmrDeliveryLifecycleEventEntity,
        EmrDeliveryMetadataEntity,
        EmrDeliveryPageEntity,
    )
    # Verify entities can be created
    delivery = EmrDeliveryEntity(
        delivery_id="test-delivery",
        delivery_time_event="test-event",
        producer_system="test-system",
        data_object_logical_name="test-object",
        job_id="test-job",
        delivered_at="2026-07-21T00:00:00Z",
    )
    assert delivery.delivery_id == "test-delivery"
    assert delivery.delivery_type == "initial"
    assert delivery.status == "registered"
