"""
Agent Audit Logger for DQ-RuleBuilder.

This module provides comprehensive audit logging for all agent operations,
including automatic secrets redaction (LLM-1.16) and integration with existing
audit trail (WF-1.5).

Features:
- Automatic logging of all agent actions
- Secrets redaction from prompts, responses, and parameters
- Async database persistence
- Structured logging
- Configurable logging levels

Security:
- NEVER logs raw credentials, API keys, or secrets
- Redacts sensitive fields automatically
- Supports custom redaction patterns
- Integrates with SIEM systems
"""

import functools
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Union

import httpx
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_agent_config
from .database.models import (
    AgentAuditLogModel,
    AuditActionEnum,
)
from .database.config import get_database_config


logger = logging.getLogger(__name__)


# ============================================================================
# Secrets Redaction
# ============================================================================

# Default sensitive field names that should be redacted
DEFAULT_SENSITIVE_KEYS: Set[str] = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "api_key",
    "apikey",
    "api-key",
    "token",
    "access_token",
    "refresh_token",
    "auth_token",
    "authorization",
    "credential",
    "credentials",
    "private_key",
    "privatekey",
    "connection_string",
    "conn_string",
    "conn_str",
    "database_url",
    "db_url",
}

# Patterns for detecting sensitive values in strings
DEFAULT_SENSITIVE_PATTERNS: List[re.Pattern] = [
    # Bearer tokens
    re.compile(r"Bearer\s+[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+", re.IGNORECASE),
    # Generic API keys (long alphanumeric strings)
    re.compile(r"[A-Za-z0-9\-_]{32,}", re.IGNORECASE),
    # PostgreSQL connection strings
    re.compile(r"postgresql://[^\s]+", re.IGNORECASE),
    re.compile(r"postgresql\+psycopg://[^\s]+", re.IGNORECASE),
    # Generic connection strings
    re.compile(r"[a-z]+://[^\s]+:[^\s]+@[^\s]+", re.IGNORECASE),
    # JSON secrets
    re.compile(r'"(password|secret|api_key|token)"\s*:\s*"[^"]+"', re.IGNORECASE),
]

# Placeholder for redacted values
REDACTED_PLACEHOLDER = "[REDACTED]"


@dataclass
class RedactionConfig:
    """Configuration for secrets redaction."""
    sensitive_keys: Set[str] = field(default_factory=lambda: DEFAULT_SENSITIVE_KEYS.copy())
    sensitive_patterns: List[re.Pattern] = field(default_factory=lambda: DEFAULT_SENSITIVE_PATTERNS.copy())
    redact_nested: bool = True
    redact_values: bool = True
    redact_keys: bool = True
    max_depth: int = 10


class SecretsRedactor:
    """
    Handles automatic redaction of sensitive information from logs.
    
    This class ensures that secrets, credentials, and other sensitive data
    are never written to logs or the database.
    """
    
    def __init__(self, config: Optional[RedactionConfig] = None):
        """
        Initialize the secrets redactor.
        
        Args:
            config: Optional redaction configuration
        """
        self.config = config or RedactionConfig()
        self._compiled_patterns = self.config.sensitive_patterns
    
    def redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively redact sensitive keys and values from a dictionary.
        
        Args:
            data: Dictionary to redact
            
        Returns:
            Redacted dictionary
        """
        if not isinstance(data, dict):
            return data
        
        return self._redact_dict_recursive(data, depth=0)
    
    def _redact_dict_recursive(self, data: Dict[str, Any], depth: int) -> Dict[str, Any]:
        """Recursively redact dictionary values."""
        if depth > self.config.max_depth:
            return {k: REDACTED_PLACEHOLDER for k in data.keys()}
        
        result = {}
        for key, value in data.items():
            # Check if key is sensitive
            if self._is_sensitive_key(key):
                if self.config.redact_keys:
                    result[key] = REDACTED_PLACEHOLDER
                    continue
            
            # Recursively process nested structures
            if isinstance(value, dict):
                result[key] = self._redact_dict_recursive(value, depth + 1)
            elif isinstance(value, list):
                result[key] = [
                    self._redact_dict_recursive(item, depth + 1) if isinstance(item, dict) else 
                    self._redact_value(item)
                    for item in value
                ]
            elif isinstance(value, str):
                result[key] = self._redact_value(value)
            else:
                result[key] = value
        
        return result
    
    def redact_value(self, value: Any) -> Any:
        """
        Redact sensitive patterns from a string value.
        
        Args:
            value: Value to redact
            
        Returns:
            Redacted value
        """
        if not isinstance(value, str):
            return value
        
        result = value
        
        # Apply pattern-based redaction
        for pattern in self._compiled_patterns:
            result = pattern.sub(REDACTED_PLACEHOLDER, result)
        
        return result
    
    def _is_sensitive_key(self, key: str) -> bool:
        """Check if a key name is sensitive."""
        key_lower = key.lower()
        for sensitive_key in self.config.sensitive_keys:
            if sensitive_key.lower() in key_lower:
                return True
        return False
    
    def redact_string(self, text: str) -> str:
        """
        Redact sensitive patterns from a string.
        
        Args:
            text: String to redact
            
        Returns:
            Redacted string
        """
        if not isinstance(text, str):
            return text
        
        result = text
        for pattern in self._compiled_patterns:
            result = pattern.sub(REDACTED_PLACEHOLDER, result)
        
        return result
    
    def redact_all(self, data: Any) -> Any:
        """
        Redact sensitive information from any data type.
        
        Args:
            data: Data to redact
            
        Returns:
            Redacted data
        """
        if isinstance(data, dict):
            return self.redact_dict(data)
        elif isinstance(data, list):
            return [self.redact_all(item) for item in data]
        elif isinstance(data, str):
            return self.redact_string(data)
        else:
            return data


# Global redactor instance
_redactor: Optional[SecretsRedactor] = None


def get_redactor() -> SecretsRedactor:
    """Get the global secrets redactor instance."""
    global _redactor
    if _redactor is None:
        _redactor = SecretsRedactor()
    return _redactor


def reset_redactor() -> SecretsRedactor:
    """Reset the global secrets redactor instance."""
    global _redactor
    _redactor = SecretsRedactor()
    return _redactor


# ============================================================================
# Audit Logger
# ============================================================================

@dataclass
class AuditLogEntry:
    """Represents a single audit log entry."""
    session_id: Optional[str] = None
    action: str = ""
    endpoint: Optional[str] = None
    method: Optional[str] = None
    response_type: Optional[str] = None
    status_code: Optional[int] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    request_origin: Optional[str] = None
    user_agent: Optional[str] = None
    user_id: Optional[str] = None
    agent_type: Optional[str] = None
    agent_source: Optional[str] = None
    agent_instance_id: Optional[str] = None
    tool_name: Optional[str] = None
    prompt: Optional[str] = None
    response: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    ip_address: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[datetime] = None


class AgentAuditLogger:
    """
    Central audit logger for all agent operations.
    
    This class provides:
    - Structured logging of all agent actions
    - Automatic secrets redaction (LLM-1.16)
    - Database persistence of audit logs
    - Integration with existing audit trail (WF-1.5)
    - Async support for non-blocking logging
    """
    
    def __init__(
        self,
        redactor: Optional[SecretsRedactor] = None,
        log_to_db: bool = True,
        log_to_file: bool = True,
        mirror_to_existing_audit_trail: bool = True,
        existing_audit_trail_base_url: Optional[str] = None,
        existing_audit_trail_api_key_provider: Optional[Callable[[], Optional[str]]] = None,
        existing_audit_trail_timeout_seconds: float = 30.0,
    ):
        """
        Initialize the audit logger.
        
        Args:
            redactor: Optional secrets redactor (uses global if not provided)
            log_to_db: Whether to log to database
            log_to_file: Whether to log to file
            mirror_to_existing_audit_trail: Whether to forward audit events to dq-api
            existing_audit_trail_base_url: Base URL for the dq-api audit endpoint
            existing_audit_trail_api_key_provider: Callable returning the current dq-api API key
            existing_audit_trail_timeout_seconds: Timeout for dq-api audit requests
        """
        self.redactor = redactor or get_redactor()
        self.log_to_db = log_to_db
        self.log_to_file = log_to_file
        self.mirror_to_existing_audit_trail = mirror_to_existing_audit_trail
        agent_config = get_agent_config()
        self._existing_audit_trail_base_url = str(existing_audit_trail_base_url or agent_config.api_base_url or "").strip().rstrip("/")
        self._existing_audit_trail_api_key_provider = existing_audit_trail_api_key_provider or agent_config.get_api_key_provider()
        self._existing_audit_trail_timeout_seconds = float(existing_audit_trail_timeout_seconds)
        self._db_engine = None
        self._db_session_maker = None
        self._existing_audit_trail_client: Optional[httpx.AsyncClient] = None
        self._initialized = False
        
        logger.info("AgentAuditLogger initialized")
    
    async def initialize(self) -> None:
        """Initialize database connection for persistence."""
        if self._initialized:
            return
        
        if self.log_to_db:
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy.orm import sessionmaker
            from .database.config import get_database_config
            
            config = get_database_config()
            
            self._db_engine = create_async_engine(
                config.async_database_url,
                echo=False,
                pool_size=2,
                max_overflow=5,
            )
            
            self._db_session_maker = sessionmaker(
                self._db_engine,
                expire_on_commit=False,
                class_=AsyncSession
            )
            
            self._initialized = True
            logger.info("AgentAuditLogger database connection initialized")
    
    async def close(self) -> None:
        """Close database connection."""
        if self._db_engine:
            await self._db_engine.dispose()
            self._db_engine = None
            self._initialized = False
            logger.info("AgentAuditLogger database connection closed")
        if self._existing_audit_trail_client:
            await self._existing_audit_trail_client.aclose()
            self._existing_audit_trail_client = None
    
    async def log(
        self,
        action: Union[str, AuditActionEnum],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        tool_name: Optional[str] = None,
        prompt: Optional[str] = None,
        response: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an audit entry.
        
        Args:
            action: The action being logged
            session_id: The session ID
            user_id: The user who initiated the action
            agent_type: The type of agent
            tool_name: The name of the tool (for tool_call actions)
            prompt: The user prompt
            response: The agent response
            parameters: Parameters passed to the tool
            result: Result from the tool
            duration_ms: How long the action took
            success: Whether the action succeeded
            error_message: Error details if failed
            ip_address: Client IP address
            metadata: Additional context
        """
        if not self._initialized and self.log_to_db:
            await self.initialize()
        
        # Create the log entry
        entry = AuditLogEntry(
            session_id=session_id,
            action=action if isinstance(action, str) else action.value,
            user_id=user_id,
            agent_type=agent_type,
            tool_name=tool_name,
            prompt=prompt,
            response=response,
            parameters=parameters or {},
            result=result or {},
            duration_ms=duration_ms or 0.0,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            metadata=metadata or {},
            timestamp=datetime.utcnow(),
        )
        
        # Apply redaction
        entry = self._redact_entry(entry)
        
        # Log to database
        if self.log_to_db:
            await self._log_to_db(entry)
        
        # Log to file
        if self.log_to_file:
            self._log_to_file(entry)

    async def record_existing_audit_event(
        self,
        *,
        action: Union[str, AuditActionEnum],
        endpoint: str,
        method: str,
        response_type: str,
        status_code: int,
        success: bool,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        agent_source: Optional[str] = None,
        agent_instance_id: Optional[str] = None,
        request_origin: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        prompt: Optional[str] = None,
        response: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an audit entry locally and mirror it to dq-api's existing audit trail."""
        if not self._initialized and self.log_to_db:
            await self.initialize()

        entry = AuditLogEntry(
            session_id=session_id,
            action=action if isinstance(action, str) else action.value,
            endpoint=endpoint,
            method=method,
            response_type=response_type,
            status_code=status_code,
            request_id=request_id,
            correlation_id=correlation_id,
            request_origin=request_origin,
            user_agent=user_agent,
            user_id=user_id,
            agent_type=agent_type,
            agent_source=agent_source,
            agent_instance_id=agent_instance_id,
            tool_name=tool_name,
            prompt=prompt,
            response=response,
            parameters=parameters or {},
            result=result or {},
            duration_ms=duration_ms or 0.0,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            metadata=metadata or {},
            timestamp=datetime.utcnow(),
        )

        await self._persist_entry(entry)
        await self._mirror_to_existing_audit_trail(entry)

    async def _persist_entry(self, entry: AuditLogEntry) -> None:
        """Persist an audit entry to the configured local stores."""
        entry = self._redact_entry(entry)

        if self.log_to_db:
            await self._log_to_db(entry)

        if self.log_to_file:
            self._log_to_file(entry)

    def _build_existing_audit_payload(self, entry: AuditLogEntry) -> Dict[str, Any]:
        details: Dict[str, Any] = {
            "session_id": entry.session_id,
            "tool_name": entry.tool_name,
            "prompt": entry.prompt,
            "response": entry.response,
            "parameters": entry.parameters,
            "result": entry.result,
            "duration_ms": entry.duration_ms,
            "metadata": entry.metadata,
        }
        if entry.error_message:
            details["error_message"] = entry.error_message

        details = {key: value for key, value in details.items() if value is not None and value != {}}

        return {
            "action": entry.action,
            "endpoint": entry.endpoint or "",
            "method": entry.method or "POST",
            "actor_id": entry.user_id,
            "correlation_id": entry.correlation_id or entry.session_id,
            "agent_type": entry.agent_type,
            "agent_source": entry.agent_source or "dq-llm",
            "agent_instance_id": entry.agent_instance_id or entry.session_id,
            "request_origin": entry.request_origin or "dq-llm",
            "user_agent": entry.user_agent,
            "response_type": entry.response_type or "agent_audit_event_response",
            "status_code": entry.status_code if entry.status_code is not None else (200 if entry.success else 500),
            "success": entry.success,
            "request_id": entry.request_id,
            "details": details,
        }

    async def _mirror_to_existing_audit_trail(self, entry: AuditLogEntry) -> None:
        if not self.mirror_to_existing_audit_trail:
            return
        if not self._existing_audit_trail_base_url:
            raise RuntimeError("DQ API base URL is required to mirror agent audit events")

        if self._existing_audit_trail_client is None:
            self._existing_audit_trail_client = httpx.AsyncClient(timeout=self._existing_audit_trail_timeout_seconds)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._existing_audit_trail_api_key_provider is not None:
            api_key = str(self._existing_audit_trail_api_key_provider() or "").strip()
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

        response = await self._existing_audit_trail_client.post(
            f"{self._existing_audit_trail_base_url}/agent/v1/audit/events",
            json=self._build_existing_audit_payload(entry),
            headers=headers,
        )
        response.raise_for_status()
    
    def _redact_entry(self, entry: AuditLogEntry) -> AuditLogEntry:
        """Apply redaction to an audit log entry."""
        # Redact string fields
        if entry.prompt:
            entry.prompt = self.redactor.redact_string(entry.prompt)
        if entry.response:
            entry.response = self.redactor.redact_string(entry.response)
        if entry.error_message:
            entry.error_message = self.redactor.redact_string(entry.error_message)
        
        # Redact dict fields
        if entry.parameters:
            entry.parameters = self.redactor.redact_dict(entry.parameters)
        if entry.result:
            entry.result = self.redactor.redact_dict(entry.result)
        if entry.metadata:
            entry.metadata = self.redactor.redact_dict(entry.metadata)
        
        return entry
    
    async def _log_to_db(self, entry: AuditLogEntry) -> None:
        """Log entry to database."""
        if not self._db_session_maker:
            return
        
        try:
            async with self._db_session_maker() as session:
                stmt = insert(AgentAuditLogModel).values(
                    session_id=entry.session_id,
                    action=entry.action,
                    timestamp=entry.timestamp,
                    user_id=entry.user_id,
                    agent_type=entry.agent_type,
                    tool_name=entry.tool_name,
                    prompt=entry.prompt,
                    response=entry.response,
                    parameters=entry.parameters,
                    result=entry.result,
                    duration_ms=entry.duration_ms,
                    success=entry.success,
                    error_message=entry.error_message,
                    ip_address=entry.ip_address,
                    metadata=entry.metadata,
                )
                await session.execute(stmt)
                await session.commit()
                
            logger.debug(f"Audit log: {entry.action} (session={entry.session_id})")
        except Exception as e:
            logger.error(f"Failed to log to database: {e}")
            # Fall back to file logging
            self._log_to_file(entry)
    
    def _log_to_file(self, entry: AuditLogEntry) -> None:
        """Log entry to structured logger."""
        log_data = {
            "audit": True,
            "action": entry.action,
            "session_id": entry.session_id,
            "endpoint": entry.endpoint,
            "method": entry.method,
            "response_type": entry.response_type,
            "status_code": entry.status_code,
            "request_id": entry.request_id,
            "correlation_id": entry.correlation_id,
            "user_id": entry.user_id,
            "agent_type": entry.agent_type,
            "agent_source": entry.agent_source,
            "agent_instance_id": entry.agent_instance_id,
            "tool_name": entry.tool_name,
            "duration_ms": entry.duration_ms,
            "success": entry.success,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        }
        
        if entry.error_message:
            log_data["error"] = entry.error_message
        
        if entry.prompt:
            log_data["prompt"] = entry.prompt[:200] + "..." if len(entry.prompt) > 200 else entry.prompt
        
        if entry.response:
            log_data["response"] = entry.response[:200] + "..." if len(entry.response) > 200 else entry.response
        
        if entry.ip_address:
            log_data["ip_address"] = entry.ip_address
        
        # Log at appropriate level
        if entry.success:
            logger.info("Agent Audit", extra=log_data)
        else:
            logger.warning("Agent Audit Error", extra=log_data)
    
    # ========================================================================
    # Convenience Methods
    # ========================================================================
    
    async def log_session_start(
        self,
        session_id: str,
        agent_type: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log the start of a new session."""
        await self.log(
            action=AuditActionEnum.SESSION_START,
            session_id=session_id,
            user_id=user_id,
            agent_type=agent_type,
            ip_address=ip_address,
            metadata=metadata,
        )
    
    async def log_session_end(
        self,
        session_id: str,
        agent_type: str,
        user_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log the end of a session."""
        await self.log(
            action=AuditActionEnum.SESSION_END,
            session_id=session_id,
            user_id=user_id,
            agent_type=agent_type,
            duration_ms=duration_ms,
            success=True,
            metadata=metadata,
        )
    
    async def log_session_destroy(
        self,
        session_id: str,
        agent_type: str,
        user_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Log the destruction of a session."""
        await self.log(
            action=AuditActionEnum.SESSION_DESTROY,
            session_id=session_id,
            user_id=user_id,
            agent_type=agent_type,
            success=True,
            metadata={"reason": reason} if reason else None,
        )
    
    async def log_tool_call(
        self,
        session_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        result: Dict[str, Any],
        duration_ms: float,
        success: bool = True,
        error_message: Optional[str] = None,
        agent_type: Optional[str] = None,
    ) -> None:
        """Log a tool call."""
        await self.log(
            action=AuditActionEnum.TOOL_CALL,
            session_id=session_id,
            agent_type=agent_type,
            tool_name=tool_name,
            parameters=parameters,
            result=result,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
        )
    
    async def log_agent_run(
        self,
        session_id: str,
        prompt: str,
        agent_type: str,
        duration_ms: Optional[float] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an agent run request."""
        await self.log(
            action=AuditActionEnum.AGENT_RUN,
            session_id=session_id,
            user_id=user_id,
            agent_type=agent_type,
            prompt=prompt,
            duration_ms=duration_ms,
            metadata=metadata,
        )
    
    async def log_agent_response(
        self,
        session_id: str,
        response: str,
        agent_type: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        duration_ms: Optional[float] = None,
    ) -> None:
        """Log an agent response."""
        metadata = None
        if tool_calls:
            metadata = {"tool_call_count": len(tool_calls)}
        
        await self.log(
            action=AuditActionEnum.AGENT_RESPONSE,
            session_id=session_id,
            agent_type=agent_type,
            response=response,
            duration_ms=duration_ms,
            metadata=metadata,
        )
    
    async def log_error(
        self,
        session_id: Optional[str],
        error: Exception,
        action: str,
        agent_type: Optional[str] = None,
        tool_name: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Log an error."""
        await self.log(
            action=AuditActionEnum.ERROR,
            session_id=session_id,
            user_id=user_id,
            agent_type=agent_type,
            tool_name=tool_name,
            success=False,
            error_message=str(error),
            metadata={
                "error_type": type(error).__name__,
                "action": action,
            },
        )


# Global audit logger instance
_audit_logger: Optional[AgentAuditLogger] = None


def get_audit_logger() -> AgentAuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        config = get_agent_config()
        _audit_logger = AgentAuditLogger(
            log_to_db=config.audit_enabled,
            log_to_file=config.audit_enabled,
            mirror_to_existing_audit_trail=config.audit_enabled,
            existing_audit_trail_base_url=config.api_base_url,
            existing_audit_trail_api_key_provider=config.get_api_key_provider(),
        )
    return _audit_logger


def reset_audit_logger() -> AgentAuditLogger:
    """Reset the global audit logger instance."""
    global _audit_logger
    if _audit_logger:
        # Close existing connection
        import asyncio
        asyncio.run(_audit_logger.close())
    config = get_agent_config()
    _audit_logger = AgentAuditLogger(
        log_to_db=config.audit_enabled,
        log_to_file=config.audit_enabled,
        mirror_to_existing_audit_trail=config.audit_enabled,
        existing_audit_trail_base_url=config.api_base_url,
        existing_audit_trail_api_key_provider=config.get_api_key_provider(),
    )
    return _audit_logger


# ============================================================================
# Decorator for Automatic Audit Logging
# ============================================================================

def audit_agent_action(
    action: Union[str, AuditActionEnum],
    get_session_id: Optional[Callable[..., str]] = None,
    get_agent_type: Optional[Callable[..., str]] = None,
    get_user_id: Optional[Callable[..., str]] = None,
):
    """
    Decorator to automatically log agent actions.
    
    Example:
        @audit_agent_action(AuditActionEnum.TOOL_CALL, get_session_id=lambda self: self.session_id)
        async def run_tool(self, tool_name: str, params: dict):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            audit = get_audit_logger()
            
            # Get context
            session_id = None
            agent_type = None
            user_id = None
            
            if get_session_id:
                try:
                    session_id = get_session_id(*args, **kwargs)
                except Exception:
                    pass
            
            if get_agent_type:
                try:
                    agent_type = get_agent_type(*args, **kwargs)
                except Exception:
                    pass
            
            if get_user_id:
                try:
                    user_id = get_user_id(*args, **kwargs)
                except Exception:
                    pass
            
            # Execute the function
            start_time = time.time()
            success = True
            error_message = None
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error_message = str(e)
                raise
            finally:
                # Log the action
                duration_ms = (time.time() - start_time) * 1000
                await audit.log(
                    action=action,
                    session_id=session_id,
                    user_id=user_id,
                    agent_type=agent_type,
                    duration_ms=duration_ms,
                    success=success,
                    error_message=error_message,
                )
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            audit = get_audit_logger()
            
            # Get context
            session_id = None
            agent_type = None
            user_id = None
            
            if get_session_id:
                try:
                    session_id = get_session_id(*args, **kwargs)
                except Exception:
                    pass
            
            if get_agent_type:
                try:
                    agent_type = get_agent_type(*args, **kwargs)
                except Exception:
                    pass
            
            if get_user_id:
                try:
                    user_id = get_user_id(*args, **kwargs)
                except Exception:
                    pass
            
            # Execute the function
            start_time = time.time()
            success = True
            error_message = None
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error_message = str(e)
                raise
            finally:
                # Log the action
                duration_ms = (time.time() - start_time) * 1000
                import asyncio
                asyncio.run(audit.log(
                    action=action,
                    session_id=session_id,
                    user_id=user_id,
                    agent_type=agent_type,
                    duration_ms=duration_ms,
                    success=success,
                    error_message=error_message,
                ))
        
        # Choose wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
