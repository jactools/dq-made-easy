"""
Trino Configuration Module

Centralizes Trino configuration and defaults.
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_TRINO_CONFIG: dict[str, Any] = {
    "host": "localhost",
    "http_port": 8080,
    "user": "user",
    "catalog": "hive",
    "schema": "default",
    "http_scheme": "http",
    "verify": True,
    "timeout_ms": 30000,
    "memory_per_task": "1GB",
    "max_row_fetch_size": 10000,
    "max_result_sample_size": 1000,
    "max_row_fetch_size_per_query": 10000,
    "connection_attempts": 3,
    "connection_retry_backoff_ms": 250,
    "source": "dq-engine",
    "extra_credential_headers": {},
}

TRINO_CONFIG_KEYS: dict[str, str] = {
    "DQ_TRINO_HOST": "host",
    "DQ_TRINO_PORT": "http_port",
    "DQ_TRINO_USER": "user",
    "DQ_TRINO_CATALOG": "catalog",
    "DQ_TRINO_SCHEMA": "schema",
    "DQ_TRINO_HTTP_SCHEME": "http_scheme",
    "DQ_TRINO_VERIFY": "verify",
    "DQ_TRINO_TIMEOUT": "timeout_ms",
    "DQ_TRINO_MEMORY": "memory_per_task",
    "DQ_TRINO_MAX_ROW_FETCH_SIZE": "max_row_fetch_size",
    "DQ_TRINO_MAX_RESULT_SAMPLE_SIZE": "max_result_sample_size",
    "DQ_TRINO_CONNECTION_ATTEMPTS": "connection_attempts",
    "DQ_TRINO_CONNECTION_RETRY_BACKOFF_MS": "connection_retry_backoff_ms",
    "DQ_TRINO_SOURCE": "source",
}

INTEGER_CONFIG_KEYS = {
    "http_port",
    "timeout_ms",
    "max_row_fetch_size",
    "max_result_sample_size",
    "max_row_fetch_size_per_query",
    "connection_attempts",
    "connection_retry_backoff_ms",
}

BOOLEAN_CONFIG_KEYS = {"verify"}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return bool(value)


def normalize_trino_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = DEFAULT_TRINO_CONFIG.copy()
    normalized.update(config)

    for key in INTEGER_CONFIG_KEYS:
        if key in normalized and normalized[key] is not None:
            normalized[key] = int(normalized[key])

    for key in BOOLEAN_CONFIG_KEYS:
        if key in normalized and normalized[key] is not None:
            normalized[key] = _coerce_bool(normalized[key])

    if normalized.get("extra_credential_headers") is None:
        normalized["extra_credential_headers"] = {}

    return normalized


def load_trino_config() -> dict[str, Any]:
    """
    Load Trino configuration from environment variables with fallback to defaults.
    
    Returns:
        Dictionary with configuration values
    """
    config = DEFAULT_TRINO_CONFIG.copy()
    
    for env_key, config_key in TRINO_CONFIG_KEYS.items():
        env_value = os.environ.get(env_key)
        if env_value is not None:
            config[config_key] = env_value

    return normalize_trino_config(config)


def validate_trino_config(config: dict[str, Any]) -> list[str]:
    """
    Validate Trino configuration values.
    
    Args:
        config: Configuration dictionary to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    try:
        config = normalize_trino_config(config)
    except Exception as exc:
        return [f"invalid Trino configuration value: {exc}"]

    errors = []
    
    if "host" in config and not config["host"]:
        errors.append("host cannot be empty")

    for key in {"user", "catalog", "schema"}:
        if key in config and not str(config[key] or "").strip():
            errors.append(f"{key} cannot be empty")

    if config.get("http_scheme") not in {"http", "https"}:
        errors.append(f"http_scheme must be 'http' or 'https', got {config.get('http_scheme')!r}")
    
    if "http_port" in config:
        port = config["http_port"]
        if not isinstance(port, int) or port < 1 or port > 65535:
            errors.append(f"http_port must be a valid port number (1-65535), got {port}")
    
    if "timeout_ms" in config:
        timeout = config["timeout_ms"]
        if not isinstance(timeout, (int, float)) or timeout < 1:
            errors.append(f"timeout_ms must be a positive number, got {timeout}")

    for key in {"max_row_fetch_size", "max_result_sample_size", "connection_attempts"}:
        value = config.get(key)
        if not isinstance(value, int) or value < 1:
            errors.append(f"{key} must be a positive integer, got {value}")

    retry_backoff = config.get("connection_retry_backoff_ms")
    if not isinstance(retry_backoff, int) or retry_backoff < 0:
        errors.append(f"connection_retry_backoff_ms must be a non-negative integer, got {retry_backoff}")

    if not isinstance(config.get("extra_credential_headers"), dict):
        errors.append("extra_credential_headers must be a dictionary")
    
    return errors
