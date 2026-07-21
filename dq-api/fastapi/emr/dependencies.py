"""EMR repository dependency injection.

Provides the EMR repository for the Canonical Delivery Registry.
"""

from __future__ import annotations

from functools import lru_cache

from emr.repository import InMemoryEmrRepository


@lru_cache
def _get_emr_repository() -> InMemoryEmrRepository:
    """Get the EMR repository instance (cached)."""
    return InMemoryEmrRepository()


def get_emr_repository() -> InMemoryEmrRepository:
    """Get the EMR (Canonical Delivery Registry) repository.

    Currently returns an in-memory implementation. A Postgres-backed
    implementation using the emr schema will follow.
    """
    return _get_emr_repository()
