from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class GxWorkerConfigError(RuntimeError):
    pass


class GxWorkerExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        failure_code: str = "GX_WORKER_EXECUTION_ERROR",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_code = failure_code
        self.status_code = status_code


@dataclass(frozen=True)
class GxWorkerConfig:
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
    uri: str
    format: str
    options: dict[str, Any]
