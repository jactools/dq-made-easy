"""DeliveryTimeEvent — UUIDv7 unique occurrence identifier.

Each delivery occurrence (initial, retry, correction, backfill) gets a unique
UUIDv7. This is the primary key for individual deliveries within a stream.
"""

from __future__ import annotations

from emr_utils import generate_uuid7


def generate_delivery_time_event() -> str:
    """Generate a UUIDv7 delivery time event identifier.

    UUIDv7 provides time-ordered identifiers with millisecond precision,
    making them suitable for delivery tracking where chronological ordering
    matters.

    Returns:
        UUIDv7 string in standard format (e.g., '019a2b3c-4d5e-7f01-8a9b-0c1d2e3f4a5b')
    """
    return generate_uuid7()
