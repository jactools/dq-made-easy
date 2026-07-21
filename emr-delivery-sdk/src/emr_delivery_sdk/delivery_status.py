"""DeliveryStatus — lifecycle status of a delivery occurrence.

A delivery progresses through statuses as it moves through its lifecycle.
Corrections and supersession create explicit status transitions.
"""

from __future__ import annotations

from enum import Enum


class DeliveryStatus(str, Enum):
    """Lifecycle status of a delivery occurrence.

    - registered: Delivery record created in EMR
    - ingested: Delivery written to storage
    - validated: Controls (DTC, DQ, Guard) have passed
    - archived: Wrong data moved to archive area
    - superseded: Delivery replaced by a correction
    """

    REGISTERED = "registered"
    INGESTED = "ingested"
    VALIDATED = "validated"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"
