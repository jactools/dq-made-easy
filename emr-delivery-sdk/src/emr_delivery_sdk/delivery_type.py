"""DeliveryType — classification of a delivery occurrence.

Each delivery is classified by type to distinguish the business meaning
of the occurrence (initial, retry, correction, etc.).
"""

from __future__ import annotations

from enum import Enum


class DeliveryType(str, Enum):
    """Classification of a delivery occurrence.

    - initial: First delivery for this stream at this point in time
    - retry: Identical reprocessing, no business meaning change
    - correction: Wrong data replaced; business meaning changed
    - backfill: Historic data loaded for a past period
    - deletion: Logical deletion marker (data archived, not deleted)
    - retention: Retention/snapshot event
    """

    INITIAL = "initial"
    RETRY = "retry"
    CORRECTION = "correction"
    BACKFILL = "backfill"
    DELETION = "deletion"
    RETENTION = "retention"
