"""EMR Delivery SDK — canonical DeliveryId and Data Delivery Note generation.

This package provides the core logic for generating deterministic DeliveryIds
and UUIDv7 delivery time events. It is the single source of truth used by:

1. The EMR Delivery CLI (emr-delivery-cli)
2. The EMR API (dq-api/fastapi/emr)
3. Any other component that produces delivery metadata
"""

from emr_delivery_sdk.delivery_id import DeliveryId, DeliveryIdBuilder
from emr_delivery_sdk.delivery_time_event import generate_delivery_time_event
from emr_delivery_sdk.delivery_type import DeliveryType
from emr_delivery_sdk.delivery_status import DeliveryStatus
from emr_delivery_sdk.ddn import DataDeliveryNote, DdnBuilder

__all__ = [
    "DeliveryId",
    "DeliveryIdBuilder",
    "generate_delivery_time_event",
    "DeliveryType",
    "DeliveryStatus",
    "DataDeliveryNote",
    "DdnBuilder",
]
