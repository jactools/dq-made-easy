from __future__ import annotations

import os
from typing import Any


DEFAULT_SPARK_MASTER = "local[*]"
DEFAULT_SPARK_UI_PORT = 4044
DEFAULT_SPARK_SESSION_TIMEZONE = "UTC"


def resolve_spark_master(default: str = DEFAULT_SPARK_MASTER) -> str:
    return str(os.getenv("DQ_SPARK_MASTER") or default).strip() or default


def resolve_spark_ui_port(raw_value: str | int | None = None) -> int:
    if raw_value is None:
        raw_value = os.getenv("DQ_SPARK_UI_PORT") or str(DEFAULT_SPARK_UI_PORT)
    normalized = str(raw_value).strip()
    try:
        parsed = int(normalized)
    except Exception as exc:
        raise ValueError("DQ_SPARK_UI_PORT must be a positive integer") from exc
    if parsed < 1:
        raise ValueError("DQ_SPARK_UI_PORT must be a positive integer")
    return parsed


def configure_spark_builder(
    builder: Any,
    *,
    spark_ui_port: str | int | None = None,
    session_timezone: str | None = None,
) -> Any:
    configured = builder.config("spark.ui.port", str(resolve_spark_ui_port(spark_ui_port)))
    if session_timezone:
        configured = configured.config("spark.sql.session.timeZone", str(session_timezone))

    driver_host = os.getenv("DQ_SPARK_DRIVER_HOST")
    if driver_host:
        configured = configured.config("spark.driver.host", str(driver_host))

    driver_bind_address = os.getenv("DQ_SPARK_DRIVER_BIND_ADDRESS")
    if driver_bind_address:
        configured = configured.config("spark.driver.bindAddress", str(driver_bind_address))

    # Allow overriding driver/executor memory from environment variables.
    # Respect DQ-prefixed vars first, then fall back to Spark-standard names.
    driver_mem = os.getenv("DQ_SPARK_DRIVER_MEMORY") or os.getenv("SPARK_DRIVER_MEMORY")
    executor_mem = os.getenv("DQ_SPARK_EXECUTOR_MEMORY") or os.getenv("SPARK_EXECUTOR_MEMORY")
    if driver_mem:
        configured = configured.config("spark.driver.memory", str(driver_mem))
    if executor_mem:
        configured = configured.config("spark.executor.memory", str(executor_mem))

    return configured


def build_spark_session_builder(
    *,
    SparkSession: Any,
    app_name: str,
    master: str | None = None,
    spark_ui_port: str | int | None = None,
    session_timezone: str | None = None,
) -> Any:
    builder = SparkSession.builder.appName(app_name)
    if master is not None:
        builder = builder.master(master)
    return configure_spark_builder(
        builder,
        spark_ui_port=spark_ui_port,
        session_timezone=session_timezone,
    )