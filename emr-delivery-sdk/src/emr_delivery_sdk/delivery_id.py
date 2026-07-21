"""DeliveryId — deterministic business key for a delivery stream.

The DeliveryId format is:
    {producer_system}:{data_object_logical_name}:{version}:{job_id}

This is a stable identifier for a delivery stream. Multiple delivery
occurrences (retries, corrections, backfills) share the same DeliveryId
but have distinct delivery_time_event (UUIDv7) values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Regex for validating DeliveryId format
_DELIVERY_ID_PATTERN = re.compile(
    r"^[a-zA-Z0-9_-]+:[a-zA-Z0-9_.-]+:\d+:[a-zA-Z0-9_-]+$"
)


@dataclass(frozen=True)
class DeliveryId:
    """Deterministic business key for a delivery stream.

    Format: {producer_system}:{data_object_logical_name}:{version}:{job_id}

    Example: sap:customer_master:1:daily-load-2026-07-21

    This identifier is stable across retries and corrections. To identify
    a specific delivery occurrence, use the delivery_time_event (UUIDv7).
    """

    producer_system: str
    data_object_logical_name: str
    version: int
    job_id: str

    def __str__(self) -> str:
        return f"{self.producer_system}:{self.data_object_logical_name}:{self.version}:{self.job_id}"

    def __repr__(self) -> str:
        return f"DeliveryId({self!s})"

    @classmethod
    def from_string(cls, delivery_id: str) -> DeliveryId:
        """Parse a DeliveryId string into a DeliveryId object.

        Args:
            delivery_id: String in format {producer_system}:{data_object_logical_name}:{version}:{job_id}

        Returns:
            DeliveryId object

        Raises:
            ValueError: If the format is invalid
        """
        parts = delivery_id.split(":")
        if len(parts) != 4:
            raise ValueError(
                f"Invalid DeliveryId format: '{delivery_id}'. "
                f"Expected format: producer_system:data_object_logical_name:version:job_id"
            )

        producer_system, data_object, version_str, job_id = parts

        # Validate version is an integer
        try:
            version = int(version_str)
        except ValueError:
            raise ValueError(
                f"Invalid version in DeliveryId: '{version_str}'. Must be an integer."
            )

        # Validate the full format
        if not _DELIVERY_ID_PATTERN.match(delivery_id):
            raise ValueError(
                f"Invalid DeliveryId format: '{delivery_id}'. "
                f"Allowed characters: alphanumeric, hyphen, underscore, dot"
            )

        return cls(
            producer_system=producer_system,
            data_object_logical_name=data_object,
            version=version,
            job_id=job_id,
        )


class DeliveryIdBuilder:
    """Builder for constructing DeliveryId instances.

    Example:
        >>> builder = DeliveryIdBuilder()
        >>> did = builder.producer_system("sap") \
        ...              .data_object("customer_master") \
        ...              .version(1) \
        ...              .job_id("daily-load") \
        ...              .build()
        >>> str(did)
        'sap:customer_master:1:daily-load'
    """

    def __init__(self) -> None:
        self._producer_system: str | None = None
        self._data_object_logical_name: str | None = None
        self._version: int | None = None
        self._job_id: str | None = None

    def producer_system(self, producer_system: str) -> DeliveryIdBuilder:
        """Set the producer system code (e.g., 'sap', 'crm', 'emr')."""
        self._producer_system = producer_system
        return self

    def data_object(self, data_object_logical_name: str) -> DeliveryIdBuilder:
        """Set the data object logical name (e.g., 'customer_master', 'orders')."""
        self._data_object_logical_name = data_object_logical_name
        return self

    def version(self, version: int) -> DeliveryIdBuilder:
        """Set the data object version."""
        self._version = version
        return self

    def job_id(self, job_id: str) -> DeliveryIdBuilder:
        """Set the pipeline job ID (e.g., 'daily-load', 'monthly-backfill')."""
        self._job_id = job_id
        return self

    def build(self) -> DeliveryId:
        """Build and return the DeliveryId.

        Returns:
            DeliveryId object

        Raises:
            ValueError: If any required field is missing
        """
        if not self._producer_system:
            raise ValueError("producer_system is required")
        if not self._data_object_logical_name:
            raise ValueError("data_object_logical_name is required")
        if self._version is None:
            raise ValueError("version is required")
        if not self._job_id:
            raise ValueError("job_id is required")

        return DeliveryId(
            producer_system=self._producer_system,
            data_object_logical_name=self._data_object_logical_name,
            version=self._version,
            job_id=self._job_id,
        )
