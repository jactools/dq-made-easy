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
    "timeout_ms": 30000,
    "memory_per_task": "1GB",
    "max_row_fetch_size": 10000,
    "max_row_fetch_size_per_query": 10000,
}

TRINO_CONFIG_KEYS: dict[str, str] = {
    "DQ_TRINO_HOST": "host",
    "DQ_TRINO_PORT": "http_port",
    "DQ_TRINO_USER": "user",
    "DQ_TRINO_CATALOG": "catalog",
    "DQ_TRINO_SCHEMA": "schema",
    "DQ_TRINO_TIMEOUT": "timeout_ms",
    "DQ_TRINO_MEMORY": "memory_per_task",
    "DQ_TRINO_MAX_ROW_FETCH_SIZE": "max_row_fetch_size",
}


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
    
    return config


def validate_trino_config(config: dict[str, Any]) -> list[str]:
    """
    Validate Trino configuration values.
    
    Args:
        config: Configuration dictionary to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    if "host" in config and not config["host"]:
        errors.append("host cannot be empty")
    
    if "http_port" in config:
        port = config["http_port"]
        if not isinstance(port, int) or port < 1 or port > 65535:
            errors.append(f"http_port must be a valid port number (1-65535), got {port}")
    
    if "timeout_ms" in config:
        timeout = config["timeout_ms"]
        if not isinstance(timeout, (int, float)) or timeout < 1:
            errors.append(f"timeout_ms must be a positive number, got {timeout}")
    
    return errors
