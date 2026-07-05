"""Tests for dq_plan_execution_types (Layer 0)."""

from __future__ import annotations

import pytest

from dq_plan_execution_types import (
    DqWorkerConfig,
    DqWorkerConfigError,
    DqWorkerExecutionError,
    SourceLocation,
)


class TestDqWorkerConfig:
    def test_create_minimal_config(self) -> None:
        config = DqWorkerConfig(
            redis_url="redis://localhost:6379/0",
            queue_key="test:queue",
            processing_queue_key="test:processing",
            heartbeat_key="test:heartbeat",
            heartbeat_ttl_seconds=30,
            heartbeat_interval_seconds=10,
            max_rows=1000,
            poll_timeout_seconds=5,
            api_url="http://localhost:8000",
            spark_master="local[*]",
            spark_ui_port=4040,
            s3_endpoint=None,
            s3_access_key=None,
            s3_secret_key=None,
            s3_region=None,
            s3_path_style_access=True,
            s3_ssl_enabled=False,
        )
        assert config.api_url == "http://localhost:8000"
        assert config.s3_endpoint is None

    def test_frozen(self) -> None:
        config = DqWorkerConfig(
            redis_url="redis://localhost:6379/0",
            queue_key="test:queue",
            processing_queue_key="test:processing",
            heartbeat_key="test:heartbeat",
            heartbeat_ttl_seconds=30,
            heartbeat_interval_seconds=10,
            max_rows=1000,
            poll_timeout_seconds=5,
            api_url="http://localhost:8000",
            spark_master="local[*]",
            spark_ui_port=4040,
            s3_endpoint=None,
            s3_access_key=None,
            s3_secret_key=None,
            s3_region=None,
            s3_path_style_access=True,
            s3_ssl_enabled=False,
        )
        with pytest.raises(Exception):
            config.api_url = "http://other"  # type: ignore


class TestDqWorkerExecutionError:
    def test_default_failure_code(self) -> None:
        err = DqWorkerExecutionError("boom")
        assert str(err) == "boom"
        assert err.failure_code == "DQ_WORKER_EXECUTION_ERROR"
        assert err.status_code is None

    def test_custom_failure_code(self) -> None:
        err = DqWorkerExecutionError("fail", failure_code="CUSTOM_FAIL", status_code=500)
        assert err.failure_code == "CUSTOM_FAIL"
        assert err.status_code == 500


class TestDqWorkerConfigError:
    def test_is_runtime_error(self) -> None:
        err = DqWorkerConfigError("bad config")
        assert str(err) == "bad config"
        assert isinstance(err, RuntimeError)


class TestSourceLocation:
    def test_create_and_frozen(self) -> None:
        loc = SourceLocation(uri="s3a://bucket/path", format="parquet", options={"header": "true"})
        assert loc.uri == "s3a://bucket/path"
        assert loc.format == "parquet"
        assert loc.options == {"header": "true"}

        with pytest.raises(Exception):
            loc.uri = "other"  # type: ignore
