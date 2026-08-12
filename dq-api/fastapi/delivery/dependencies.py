"""Delivery repository dependency injection.

Provides the Delivery repository for the Canonical Delivery Registry.
"""

from __future__ import annotations

from functools import lru_cache

from delivery.repository import InMemoryDeliveryRepository


@lru_cache
def _get_delivery_repository() -> InMemoryDeliveryRepository:
    """Get the Delivery repository instance (cached)."""
    return InMemoryDeliveryRepository()


def get_delivery_repository() -> InMemoryDeliveryRepository:
    """Get the Delivery (Canonical Delivery Registry) repository.

    Currently returns an in-memory implementation. A Postgres-backed
    implementation using the delivery schema will follow.
    """
    return _get_delivery_repository()
