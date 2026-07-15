"""Engine-agnostic execution types (Layer 0).

These types are shared across all engines and layers. They carry no GX-specific
semantics and must never import from any gx_dispatch_* module.

Types:
    DqWorkerConfig     — worker configuration (renamed from GxWorkerConfig)
    DqWorkerConfigError — configuration error (renamed from GxWorkerConfigError)
    DqWorkerExecutionError — execution error (renamed from GxWorkerExecutionError)
    SourceLocation     — source URI + format + options (unchanged)

Backward-compat aliases:
    GxWorkerConfig, GxWorkerConfigError, GxWorkerExecutionError
    (kept in gx_dispatch_types.py shim until Phase 7)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class DqWorkerConfigError(RuntimeError):
    """Error raised when worker configuration is invalid or missing."""


class DqWorkerExecutionError(RuntimeError):
    """Error raised when a worker execution fails."""

    def __init__(
        self,
        message: str,
        *,
        failure_code: str = "DQ_WORKER_EXECUTION_ERROR",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_code = failure_code
        self.status_code = status_code


@dataclass(frozen=True)
class DqWorkerConfig:
    """Configuration for an execution worker (engine-agnostic)."""

    redis_url: str
    queue_key: str
    processing_queue_key: str
    heartbeat_key: str
    heartbeat_ttl_seconds: int
    heartbeat_interval_seconds: int
    max_rows: int
    poll_timeout_seconds: int

    # API access (must be via Kong)
    api_url: str

    # Spark + S3
    spark_master: str
    spark_ui_port: int
    s3_endpoint: str | None
    s3_access_key: str | None
    s3_secret_key: str | None
    s3_region: str | None
    s3_path_style_access: bool
    s3_ssl_enabled: bool | None


@dataclass(frozen=True)
class SourceLocation:
    """Describes a data source location."""

    uri: str
    format: str
    options: dict[str, Any]


# ---------------------------------------------------------------------------
# Backward-compat aliases (for gx_dispatch_types.py shim, Phase 1–6)
# ---------------------------------------------------------------------------
GxWorkerConfigError = DqWorkerConfigError
GxWorkerConfig = DqWorkerConfig
GxWorkerExecutionError = DqWorkerExecutionError
