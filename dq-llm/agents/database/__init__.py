"""
Database persistence layer for DQ Agent Harness.

This module provides database-backed persistence for:
- Agent sessions
- Audit logs
- Metrics

Modules:
- models.py: SQLAlchemy ORM models
- session_store.py: Database implementation of SessionStore
- config.py: Database configuration management
- init_db.py: Database initialization utilities
"""

from .models import Base, AgentSessionModel, AgentAuditLogModel, AgentMetricModel
from .session_store import DatabaseSessionStore
from .config import DatabaseConfig, get_database_config, reset_database_config
from .init_db import (
    DatabaseInitializer,
    init_database,
    drop_database,
    sync_init_database,
    sync_drop_database,
)

__all__ = [
    "Base",
    "AgentSessionModel",
    "AgentAuditLogModel",
    "AgentMetricModel",
    "DatabaseSessionStore",
    "DatabaseConfig",
    "get_database_config",
    "reset_database_config",
    "DatabaseInitializer",
    "init_database",
    "drop_database",
    "sync_init_database",
    "sync_drop_database",
]
