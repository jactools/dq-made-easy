"""UUIDv7 generator — pure Python, no external dependencies.

UUIDv7 (RFC 9562) provides time-ordered identifiers with millisecond
precision. Used as the primary key for delivery occurrences in EMR.

Layout (128 bits):
  - 48 bits: unix_ts_ms (milliseconds since Unix epoch)
  - 4 bits: version (0111 = 7)
  - 12 bits: rand_a
  - 2 bits: variant (10)
  - 62 bits: rand_b
"""

from __future__ import annotations

import os
import time
import uuid


def generate_uuid7() -> str:
    """Generate a UUIDv7 identifier.

    Returns:
        UUIDv7 string in standard format (e.g., '019a2b3c-4d5e-7f01-8a9b-0c1d2e3f4a5b')
    """
    timestamp_ms = int(time.time() * 1000)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0xFFF  # 12 bits
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF  # 62 bits

    int_value = (
        (timestamp_ms & 0xFFFFFFFFFFFF) << 80
    ) | (
        7 << 76  # version 7
    ) | (
        rand_a << 64
    ) | (
        0b10 << 62  # variant
    ) | rand_b

    return str(uuid.UUID(int=int_value))


def uuid7_from_timestamp(timestamp_ms: int) -> str:
    """Create a UUIDv7 from a specific millisecond timestamp.

    Useful for testing and reproducible identifiers.

    Args:
        timestamp_ms: Milliseconds since Unix epoch

    Returns:
        UUIDv7 string with the specified timestamp
    """
    rand_a = int.from_bytes(os.urandom(2), "big") & 0xFFF  # 12 bits
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF  # 62 bits

    int_value = (
        (timestamp_ms & 0xFFFFFFFFFFFF) << 80
    ) | (
        7 << 76  # version 7
    ) | (
        rand_a << 64
    ) | (
        0b10 << 62  # variant
    ) | rand_b

    return str(uuid.UUID(int=int_value))
