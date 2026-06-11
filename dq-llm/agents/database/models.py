"""
SQLAlchemy ORM Models for DQ Agent Harness Database Persistence.

This module defines the database tables for:
- Agent sessions (persistent session state)
- Audit logs (tracking all agent operations)
- Metrics (token usage, latency, etc.)

These models are designed to work with both sync and async SQLAlchemy.
"""

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Index, String, Text, func
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, declared_attr

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models in the agent harness."""
    pass


# Enums for model fields
class AgentTypeEnum(str, Enum):
    """Types of specialized agents."""
    GENERAL = "general"
    CONNECTOR = "connector"
    RULE = "rule"
    STEWARD = "steward"


class SessionStatusEnum(str, Enum):
    """Status of an agent session."""
    ACTIVE = "active"
    IDLE = "idle"
    COMPLETED = "completed"
    ERROR = "error"
    EXPIRED = "expired"


class AuditActionEnum(str, Enum):
    """Types of auditable actions."""
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_DESTROY = "session_destroy"
    TOOL_CALL = "tool_call"
    AGENT_RUN = "agent_run"
    AGENT_RESPONSE = "agent_response"
    ERROR = "error"


class AgentSessionModel(Base):
    """
    Database model for agent session persistence.
    
    Stores the complete state of an agent session, allowing:
    - Session resumption after service restart
    - Multi-instance session sharing
    - Historical analysis of agent interactions
    
    Attributes:
        session_id: Unique identifier for the session (UUID)
        agent_type: Type of agent (general, connector, rule, steward)
        agent_name: Human-readable name of the agent
        status: Current status of the session
        created_at: When the session was created
        last_activity_at: When the session was last active
        expires_at: When the session will expire
        tool_call_count: Number of tool calls made
        error_count: Number of errors encountered
        context: JSON field for session context
        metadata: JSON field for agent-specific metadata
        conversation_history: JSON array of message history
    """
    
    __tablename__ = "agent_sessions"
    
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    agent_type: Mapped[str] = mapped_column(
        SQLAlchemyEnum(AgentTypeEnum),
        default=AgentTypeEnum.GENERAL,
        index=True
    )
    agent_name: Mapped[str] = mapped_column(String(255), default="dq_agent")
    status: Mapped[str] = mapped_column(
        SQLAlchemyEnum(SessionStatusEnum),
        default=SessionStatusEnum.ACTIVE,
        index=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=datetime.utcnow,
        index=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    tool_call_count: Mapped[int] = mapped_column(BigInteger, default=0)
    error_count: Mapped[int] = mapped_column(BigInteger, default=0)
    
    # JSON fields for flexible state storage
    context: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})
    extra_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})
    conversation_history: Mapped[list] = mapped_column(JSON, default=[])
    
    # Indexes for common query patterns
    __table_args__ = (
        Index('ix_agent_sessions_agent_type_status', 'agent_type', 'status'),
        Index('ix_agent_sessions_created_expires', 'created_at', 'expires_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary."""
        return {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "agent_name": self.agent_name,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "tool_call_count": self.tool_call_count,
            "error_count": self.error_count,
            "context": self.context or {},
            "extra_metadata": self.extra_metadata or {},
            "conversation_history": self.conversation_history or [],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentSessionModel":
        """Create model instance from dictionary."""
        return cls(
            session_id=data.get("session_id"),
            agent_type=data.get("agent_type", AgentTypeEnum.GENERAL),
            agent_name=data.get("agent_name", "dq_agent"),
            status=data.get("status", SessionStatusEnum.ACTIVE),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            last_activity_at=datetime.fromisoformat(data["last_activity_at"]) if data.get("last_activity_at") else datetime.utcnow(),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            tool_call_count=data.get("tool_call_count", 0),
            error_count=data.get("error_count", 0),
            context=data.get("context", {}),
            extra_metadata=data.get("extra_metadata", {}),
            conversation_history=data.get("conversation_history", []),
        )


class AgentAuditLogModel(Base):
    """
    Database model for audit logging of agent operations.
    
    Captures detailed information about every agent action for:
    - Security auditing
    - Compliance reporting
    - Debugging and troubleshooting
    - Usage analytics
    
    Attributes:
        id: Auto-incrementing primary key
        session_id: The session this log entry belongs to
        action: Type of action being logged
        timestamp: When the action occurred
        user_id: Who initiated the action (if available)
        agent_type: Type of agent
        tool_name: Name of tool called (for tool_call actions)
        prompt: The user prompt (redacted if contains secrets)
        response: The agent response (redacted if contains secrets)
        parameters: Parameters passed to tools (redacted)
        result: Result from tool calls (redacted)
        duration_ms: How long the action took
        success: Whether the action succeeded
        error_message: Error details if action failed
        ip_address: Client IP address
        metadata: Additional context
    """
    
    __tablename__ = "agent_audit_logs"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(SQLAlchemyEnum(AuditActionEnum), index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )
    
    # User/agent context
    user_id: Mapped[Optional[str]] = mapped_column(String(255))
    agent_type: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Action details
    tool_name: Mapped[Optional[str]] = mapped_column(String(255))
    prompt: Mapped[Optional[str]] = mapped_column(Text)
    response: Mapped[Optional[str]] = mapped_column(Text)
    
    # Parameters and results (stored as JSON for flexibility)
    parameters: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})
    result: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})
    
    # Performance and status
    duration_ms: Mapped[float] = mapped_column(default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # Request context
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))  # IPv6 max length
    extra_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})
    
    # Indexes for common queries
    __table_args__ = (
        Index('ix_agent_audit_logs_session_action', 'session_id', 'action'),
        Index('ix_agent_audit_logs_timestamp', 'timestamp'),
        Index('ix_agent_audit_logs_user_agent', 'user_id', 'agent_type'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "action": self.action,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_id": self.user_id,
            "agent_type": self.agent_type,
            "tool_name": self.tool_name,
            "prompt": self.prompt,
            "response": self.response,
            "parameters": self.parameters or {},
            "result": self.result or {},
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error_message": self.error_message,
            "ip_address": self.ip_address,
            "extra_metadata": self.extra_metadata or {},
        }


class AgentMetricModel(Base):
    """
    Database model for agent performance metrics.
    
    Tracks usage and performance metrics for:
    - Capacity planning
    - Cost analysis
    - Performance monitoring
    - Anomaly detection
    
    Attributes:
        id: Auto-incrementing primary key
        timestamp: When the metric was recorded (bucketed)
        agent_type: Type of agent
        session_id: Optional session identifier
        metric_name: Name of the metric
        metric_value: Value of the metric
        metadata: Additional context (e.g., model used, provider)
    """
    
    __tablename__ = "agent_metrics"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )
    
    agent_type: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    metric_name: Mapped[str] = mapped_column(String(255), index=True)
    metric_value: Mapped[float] = mapped_column(default=0.0)
    extra_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})
    
    __table_args__ = (
        Index('ix_agent_metrics_timestamp_name', 'timestamp', 'metric_name'),
        Index('ix_agent_metrics_agent_session', 'agent_type', 'session_id'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "agent_type": self.agent_type,
            "session_id": self.session_id,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "extra_metadata": self.extra_metadata or {},
        }
