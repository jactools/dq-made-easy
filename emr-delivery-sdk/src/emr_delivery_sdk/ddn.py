"""DataDeliveryNote — canonical delivery record combining DeliveryId and delivery_time_event.

The Data Delivery Note (DDN) is the authoritative record of a delivery occurrence.
It combines the deterministic stream key (DeliveryId) with the unique occurrence
identifier (UUIDv7) and additional metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from emr_delivery_sdk.delivery_id import DeliveryId
from emr_delivery_sdk.delivery_status import DeliveryStatus
from emr_delivery_sdk.delivery_time_event import generate_delivery_time_event
from emr_delivery_sdk.delivery_type import DeliveryType


@dataclass
class DataDeliveryNote:
    """Canonical delivery record.

    This combines the deterministic stream key (DeliveryId) with the unique
    occurrence identifier (delivery_time_event) and additional metadata.

    The delivery_time_event is the primary key for this occurrence.
    The delivery_id identifies the stream this occurrence belongs to.
    """

    delivery_id: DeliveryId
    delivery_time_event: str  # UUIDv7
    delivery_version: int
    delivery_type: DeliveryType
    producer_system: str
    data_object_logical_name: str
    job_id: str
    data_object_version: int | None = None
    layer: str | None = None
    delivery_location: str | None = None
    storage_location: str | None = None
    record_count: int = 0
    size_bytes: int = 0
    checksum: str | None = None
    checksum_algorithm: str | None = None
    delivered_at: str = ""
    delivered_by: str | None = None
    status: DeliveryStatus = DeliveryStatus.REGISTERED
    predecessor_time_event: str | None = None
    superseded_by_time_event: str | None = None
    correction_reason: str | None = None
    metadata: dict | None = field(default_factory=dict)


class DdnBuilder:
    """Builder for constructing DataDeliveryNote instances.

    This is the primary way to create delivery notes. It ensures all required
    fields are set and generates the UUIDv7 delivery_time_event automatically.

    Example:
        >>> from emr_delivery_sdk import DdnBuilder, DeliveryIdBuilder
        >>>
        >>> did = DeliveryIdBuilder() \\
        ...     .producer_system("sap") \\
        ...     .data_object("customer_master") \\
        ...     .version(1) \\
        ...     .job_id("daily-load") \\
        ...     .build()
        >>>
        >>> ddn = DdnBuilder(delivery_id=did) \\
        ...     .delivery_type("initial") \\
        ...     .storage_location("s3://bucket/data/sap/customer/2026-07-21/") \\
        ...     .record_count(15234) \\
        ...     .build()
    """

    def __init__(self, delivery_id: DeliveryId, delivery_time_event: str | None = None) -> None:
        """Initialize the DDN builder.

        Args:
            delivery_id: The deterministic stream key
            delivery_time_event: Optional UUIDv7 (generated if not provided)
        """
        self._delivery_id = delivery_id
        self._delivery_time_event = delivery_time_event or generate_delivery_time_event()
        self._delivery_version: int = 1
        self._delivery_type: DeliveryType | None = None
        self._data_object_version: int | None = None
        self._layer: str | None = None
        self._delivery_location: str | None = None
        self._storage_location: str | None = None
        self._record_count: int = 0
        self._size_bytes: int = 0
        self._checksum: str | None = None
        self._checksum_algorithm: str | None = None
        self._delivered_at: str = ""
        self._delivered_by: str | None = None
        self._status: DeliveryStatus | None = None
        self._predecessor_time_event: str | None = None
        self._correction_reason: str | None = None
        self._metadata: dict | None = {}

    def delivery_version(self, version: int) -> DdnBuilder:
        """Set the delivery version (monotonic within the stream)."""
        self._delivery_version = version
        return self

    def delivery_type(self, delivery_type: str) -> DdnBuilder:
        """Set the delivery type classification."""
        self._delivery_type = DeliveryType(delivery_type)
        return self

    def data_object_version(self, version: int) -> DdnBuilder:
        """Set the data object version."""
        self._data_object_version = version
        return self

    def layer(self, layer: str) -> DdnBuilder:
        """Set the data layer (brown, gold, silver)."""
        self._layer = layer
        return self

    def delivery_location(self, location: str) -> DdnBuilder:
        """Set the consumer-facing delivery location."""
        self._delivery_location = location
        return self

    def storage_location(self, location: str) -> DdnBuilder:
        """Set the internal storage location."""
        self._storage_location = location
        return self

    def record_count(self, count: int) -> DdnBuilder:
        """Set the record count."""
        self._record_count = count
        return self

    def size_bytes(self, size: int) -> DdnBuilder:
        """Set the delivery size in bytes."""
        self._size_bytes = size
        return self

    def checksum(self, checksum: str, algorithm: str | None = None) -> DdnBuilder:
        """Set the content checksum and algorithm."""
        self._checksum = checksum
        self._checksum_algorithm = algorithm
        return self

    def delivered_at(self, timestamp: str) -> DdnBuilder:
        """Set the canonical delivery timestamp."""
        self._delivered_at = timestamp
        return self

    def delivered_by(self, identifier: str) -> DdnBuilder:
        """Set the pipeline or agent that produced this delivery."""
        self._delivered_by = identifier
        return self

    def status(self, status: str) -> DdnBuilder:
        """Set the delivery lifecycle status."""
        self._status = DeliveryStatus(status)
        return self

    def correction(
        self, predecessor_time_event: str, reason: str
    ) -> DdnBuilder:
        """Mark this as a correction delivery.

        Args:
            predecessor_time_event: UUIDv7 of the delivery being corrected
            reason: Why the correction was needed
        """
        self._predecessor_time_event = predecessor_time_event
        self._correction_reason = reason
        self._delivery_type = DeliveryType.CORRECTION
        return self

    def metadata(self, metadata: dict | None) -> DdnBuilder:
        """Set extended metadata."""
        self._metadata = metadata
        return self

    def build(self) -> DataDeliveryNote:
        """Build and return the DataDeliveryNote.

        Returns:
            DataDeliveryNote instance
        """
        return DataDeliveryNote(
            delivery_id=self._delivery_id,
            delivery_time_event=self._delivery_time_event,
            delivery_version=self._delivery_version,
            delivery_type=self._delivery_type or DeliveryType.INITIAL,
            producer_system=self._delivery_id.producer_system,
            data_object_logical_name=self._delivery_id.data_object_logical_name,
            job_id=self._delivery_id.job_id,
            data_object_version=self._data_object_version,
            layer=self._layer,
            delivery_location=self._delivery_location,
            storage_location=self._storage_location,
            record_count=self._record_count,
            size_bytes=self._size_bytes,
            checksum=self._checksum,
            checksum_algorithm=self._checksum_algorithm,
            delivered_at=self._delivered_at,
            delivered_by=self._delivered_by,
            status=self._status or DeliveryStatus.REGISTERED,
            predecessor_time_event=self._predecessor_time_event,
            correction_reason=self._correction_reason,
            metadata=self._metadata,
        )
