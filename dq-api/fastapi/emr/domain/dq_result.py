"""DQ Result entity for EMR — relates DQ execution outcomes to deliveries.

DQ Results are published to Kafka by the DQ engine and consumed by EMR.
Each result is linked to a delivery via delivery_id (deterministic stream key)
and delivery_time_event (UUIDv7 occurrence identifier).
"""

from __future__ import annotations

from pydantic import BaseModel


class EmrDqResultEntity(BaseModel):
    """DQ result record linked to a delivery.

    A DQ result captures the outcome of a data quality execution run against
    a specific delivery. Results are published to Kafka by the DQ engine and
    consumed by EMR for canonical tracking.
    """

    # Link to delivery
    delivery_id: str  # Deterministic stream key
    delivery_time_event: str | None = None  # UUIDv7 occurrence (if known)

    # DQ execution context
    execution_run_id: str  # Unique execution run identifier
    rule_id: str  # Rule that produced this result
    rule_name: str | None = None

    # Outcome
    status: str  # passed, failed, warning, error
    result: str | None = None  # pass, fail, warning
    passed: bool | None = None
    score: float | None = None
    score_label: str | None = None

    # Counts
    total_count: int | None = None
    valid_count: int | None = None
    invalid_count: int | None = None
    warning_count: int | None = None
    error_count: int | None = None

    # Timing
    observed_at: str | None = None
    duration_ms: int | None = None
    message: str | None = None

    # Metadata
    data_product_id: str | None = None
    data_set_id: str | None = None
    workspace_id: str | None = None

    # Audit
    id: str = ""
    created_at: str = ""


class EmrDqResultPageEntity(BaseModel):
    """Paginated DQ result list."""

    items: list[EmrDqResultEntity] = []
    total: int = 0
    page: int = 1
    limit: int = 100
