"""
Database Configuration for DQ Agent Harness.

This module provides configuration management for database connectivity,
including environment variable parsing and connection string generation.
"""

import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn


class DatabaseConfig(BaseSettings):
    """
    Configuration for database connectivity.
    
    Reads from environment variables with the following precedence:
    1. DQ_AGENT_DB_URL (explicit agent database URL)
    2. DQ_DB_INTERNAL_URL (shared DQ database URL)
    3. DQ_DB_LOCAL_URL (local development URL)
    
    Attributes:
        url: The database connection URL
        echo: Whether to log SQL statements (for debugging)
        pool_size: Maximum number of connections in the pool
        max_overflow: Maximum number of connections beyond pool_size
        pool_timeout: Seconds to wait for a connection
        pool_recycle: Seconds before recycling connections
        pool_pre_ping: Whether to test connections before use
    """
    
    # Database URL - try agent-specific first, then fall back to shared DQ DB
    url: PostgresDsn = Field(
        default=os.environ.get(
            "DQ_AGENT_DB_URL",
            os.environ.get(
                "DQ_DB_INTERNAL_URL",
                os.environ.get("DQ_DB_LOCAL_URL", "postgresql://postgres:postgres@localhost:5432/dq")
            )
        ),
        description="PostgreSQL connection URL for agent persistence"
    )
    
    # Connection pool settings
    echo: bool = Field(
        default=False,
        description="Log SQL statements (for debugging)"
    )
    pool_size: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Maximum number of connections in the pool"
    )
    max_overflow: int = Field(
        default=10,
        ge=0,
        le=50,
        description="Maximum number of connections beyond pool_size"
    )
    pool_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Seconds to wait for a connection from the pool"
    )
    pool_recycle: int = Field(
        default=3600,
        ge=0,
        description="Seconds before recycling connections (0 = disable)"
    )
    pool_pre_ping: bool = Field(
        default=True,
        description="Test connections before use to detect stale connections"
    )
    
    # Async database settings
    async_url: Optional[PostgresDsn] = Field(
        default=None,
        description="Async PostgreSQL URL (uses asyncpg). If not set, sync URL is used with +asyncpg"
    )
    
    @property
    def async_database_url(self) -> str:
        """Get the async database URL, converting sync to async if needed."""
        if self.async_url:
            url_str = str(self.async_url)
        else:
            url_str = str(self.url)
        
        # Convert postgresql:// to postgresql+asyncpg://
        if url_str.startswith("postgresql://"):
            return url_str.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url_str.startswith("postgresql+psycopg://"):
            return url_str.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
        return url_str
    
    @property
    def sync_database_url(self) -> str:
        """Get the sync database URL."""
        url_str = str(self.url)
        # Ensure it uses psycopg
        if url_str.startswith("postgresql://"):
            return url_str.replace("postgresql://", "postgresql+psycopg://", 1)
        return url_str
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DQ_AGENT_DB_",
        case_sensitive=False,
    )


@lru_cache()
def get_database_config() -> DatabaseConfig:
    """
    Get the database configuration singleton.
    
    Returns:
        DatabaseConfig: The cached configuration instance
    """
    return DatabaseConfig()


def reset_database_config() -> DatabaseConfig:
    """
    Reset the database configuration cache.
    
    Useful for testing or when configuration needs to be reloaded.
    
    Returns:
        DatabaseConfig: A new configuration instance
    """
    get_database_config.cache_clear()
    return get_database_config()
