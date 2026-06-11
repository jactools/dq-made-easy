"""
Agent Session Management for DQ-RuleBuilder Pi Agent Harness.

This module provides session persistence, lifecycle management, and cleanup
for DQ agent sessions.

Key Classes:
- AgentSession: Represents a single agent session with state
- AgentSessionManager: Manages multiple agent sessions
- SessionStore: Abstract base class for session persistence
- FileSessionStore: File-based session persistence
"""

import asyncio
import json
import logging
import os
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterator, List, Optional

from .base import DQAgent, DQAgentFactory, AgentStatus
from .config import DQAgentConfig, get_agent_config


logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """State of an agent session that can be serialized."""
    session_id: str
    agent_type: str
    agent_name: str
    status: str
    created_at: str
    last_activity_at: str
    tool_call_count: int = 0
    error_count: int = 0
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_agent(cls, agent: DQAgent) -> "SessionState":
        """Create SessionState from a DQAgent instance."""
        now = datetime.utcnow()
        return cls(
            session_id=agent.session_id,
            agent_type=agent.name.split('_')[1] if '_' in agent.name else "general",
            agent_name=agent.name,
            status=agent.status.value,
            created_at=agent._initialized_at.isoformat(),
            last_activity_at=now.isoformat(),
            tool_call_count=len(agent.tool_calls),
            error_count=agent.metrics.tool_errors_total,
            context={},
            metadata=agent.get_state(),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "agent_name": self.agent_name,
            "status": self.status,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "tool_call_count": self.tool_call_count,
            "error_count": self.error_count,
            "context": self.context,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            agent_type=data.get("agent_type", "general"),
            agent_name=data.get("agent_name", "dq_agent"),
            status=data.get("status", AgentStatus.IDLE.value),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            last_activity_at=data.get("last_activity_at", datetime.utcnow().isoformat()),
            tool_call_count=data.get("tool_call_count", 0),
            error_count=data.get("error_count", 0),
            context=data.get("context", {}),
            metadata=data.get("metadata", {}),
        )
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    @classmethod
    def from_json(cls, json_str: str) -> "SessionState":
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))


class SessionStore(ABC):
    """Abstract base class for session persistence."""
    
    @abstractmethod
    async def save_session(self, session_id: str, state: SessionState) -> None:
        """Save a session state."""
        pass
    
    @abstractmethod
    async def load_session(self, session_id: str) -> Optional[SessionState]:
        """Load a session state."""
        pass
    
    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        pass
    
    @abstractmethod
    async def list_sessions(self) -> List[SessionState]:
        """List all sessions."""
        pass
    
    @abstractmethod
    async def cleanup_expired(self, timeout_seconds: int) -> int:
        """Clean up expired sessions. Returns count of deleted sessions."""
        pass


class FileSessionStore(SessionStore):
    """
    File-based session persistence.
    
    Stores session state as JSON files in a configured directory.
    """
    
    def __init__(self, workspace_path: Optional[Path] = None):
        """
        Initialize the file session store.
        
        Args:
            workspace_path: Directory to store session files
        """
        self.config = get_agent_config()
        self.workspace_path = workspace_path or self.config.get_workspace_path()
        self._lock = Lock()
        
        # Ensure workspace exists
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileSessionStore initialized at {self.workspace_path}")
    
    def _get_session_path(self, session_id: str) -> Path:
        """Get the file path for a session."""
        return self.workspace_path / f"{session_id}.json"
    
    async def save_session(self, session_id: str, state: SessionState) -> None:
        """Save a session state to a file."""
        session_path = self._get_session_path(session_id)
        
        with self._lock:
            try:
                with open(session_path, 'w') as f:
                    f.write(state.to_json())
                logger.debug(f"Session {session_id}: Saved to {session_path}")
            except (IOError, OSError) as e:
                logger.error(f"Session {session_id}: Failed to save: {e}")
                raise
    
    async def load_session(self, session_id: str) -> Optional[SessionState]:
        """Load a session state from a file."""
        session_path = self._get_session_path(session_id)
        
        with self._lock:
            if not session_path.exists():
                logger.debug(f"Session {session_id}: Not found at {session_path}")
                return None
            
            try:
                with open(session_path, 'r') as f:
                    content = f.read()
                    state = SessionState.from_json(content)
                    logger.debug(f"Session {session_id}: Loaded from {session_path}")
                    return state
            except (IOError, OSError, json.JSONDecodeError) as e:
                logger.error(f"Session {session_id}: Failed to load: {e}")
                return None
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session file."""
        session_path = self._get_session_path(session_id)
        
        with self._lock:
            if session_path.exists():
                try:
                    session_path.unlink()
                    logger.debug(f"Session {session_id}: Deleted from {session_path}")
                    return True
                except (IOError, OSError) as e:
                    logger.error(f"Session {session_id}: Failed to delete: {e}")
                    return False
            return False
    
    async def list_sessions(self) -> List[SessionState]:
        """List all sessions from the workspace directory."""
        sessions = []
        
        with self._lock:
            for session_file in self.workspace_path.glob("*.json"):
                try:
                    with open(session_file, 'r') as f:
                        content = f.read()
                        state = SessionState.from_json(content)
                        sessions.append(state)
                except (IOError, OSError, json.JSONDecodeError) as e:
                    logger.warning(f"Failed to load session {session_file.name}: {e}")
                    continue
        
        # Sort by creation time (newest first)
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return sessions
    
    async def cleanup_expired(self, timeout_seconds: int) -> int:
        """Clean up sessions older than timeout_seconds. Returns count deleted."""
        cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
        deleted_count = 0
        
        with self._lock:
            for session_file in self.workspace_path.glob("*.json"):
                try:
                    with open(session_file, 'r') as f:
                        content = f.read()
                        state = SessionState.from_json(content)
                        
                    # Check if session is expired
                    created_at = datetime.fromisoformat(state.created_at)
                    if created_at < cutoff:
                        session_file.unlink()
                        logger.info(f"Session {state.session_id}: Cleaned up (expired)")
                        deleted_count += 1
                except (IOError, OSError, json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to check session {session_file.name}: {e}")
                    continue
        
        return deleted_count


class AgentSession:
    """
    Represents a single agent session with lifecycle management.
    
    An AgentSession wraps a DQAgent instance and provides:
    - Session lifecycle management
    - State persistence
    - Activity tracking
    - Automatic cleanup
    
    Usage:
        session = AgentSession(session_id="abc123", agent_type="connector")
        async with session:
            result = await session.agent.run("Onboard a PostgreSQL connector")
    """
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        agent_type: str = "general",
        agent: Optional[DQAgent] = None,
        store: Optional[SessionStore] = None,
        timeout_seconds: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
        **kwargs: Any
    ):
        """
        Initialize an agent session.
        
        Args:
            session_id: Unique session identifier (generated if None)
            agent_type: Type of agent ("general", "connector", "rule", "steward")
            agent: Pre-created DQAgent instance
            store: SessionStore for persistence
            timeout_seconds: Session timeout in seconds
            max_tool_calls: Maximum tool calls allowed
            **kwargs: Additional arguments passed to DQAgent
        """
        self.config = get_agent_config()
        self.session_id = session_id or str(uuid.uuid4())
        self.agent_type = agent_type
        self.timeout_seconds = timeout_seconds or self.config.session_timeout_seconds
        self.max_tool_calls = max_tool_calls or self.config.max_tool_calls_per_session
        self.store = store or FileSessionStore()
        self._lock = Lock()
        
        # Track activity
        self._created_at = datetime.utcnow()
        self._last_activity_at = self._created_at
        self._tool_call_count = 0
        self._error_count = 0
        
        # Create or use provided agent
        self._agent: Optional[DQAgent] = agent
        self._agent_kwargs = kwargs
        
        logger.info(f"AgentSession {self.session_id}: Created (type={agent_type})")
    
    @property
    def agent(self) -> DQAgent:
        """Get or create the agent instance."""
        if self._agent is None:
            with self._lock:
                # Double-check after acquiring lock
                if self._agent is None:
                    factory = DQAgentFactory()
                    if self.agent_type == "connector":
                        self._agent = factory.create_connector_agent(
                            session_id=self.session_id,
                            **self._agent_kwargs
                        )
                    elif self.agent_type == "rule":
                        self._agent = factory.create_rule_agent(
                            session_id=self.session_id,
                            **self._agent_kwargs
                        )
                    elif self.agent_type == "steward":
                        self._agent = factory.create_steward_agent(
                            session_id=self.session_id,
                            **self._agent_kwargs
                        )
                    else:
                        self._agent = factory.create_agent(
                            agent_type="general",
                            session_id=self.session_id,
                            **self._agent_kwargs
                        )
        return self._agent
    
    @property
    def is_active(self) -> bool:
        """Check if session is still active (not expired)."""
        cutoff = datetime.utcnow() - timedelta(seconds=self.timeout_seconds)
        return self._last_activity_at >= cutoff
    
    @property
    def is_exhausted(self) -> bool:
        """Check if session has exceeded max tool calls."""
        return self._tool_call_count >= self.max_tool_calls
    
    @property
    def status(self) -> AgentStatus:
        """Get the current agent status."""
        return self.agent.status
    
    async def run(self, prompt: str, **kwargs: Any) -> Any:
        """
        Run the agent with a prompt.
        
        Args:
            prompt: The user prompt
            **kwargs: Additional arguments passed to agent.run()
            
        Returns:
            The agent's response
            
        Raises:
            DQAgentError: If session is expired or exhausted
        """
        if not self.is_active:
            raise DQAgentError(
                message=f"Session {self.session_id} has expired",
                error_type="session_expired",
                details={"session_id": self.session_id, "timeout": self.timeout_seconds}
            )
        
        if self.is_exhausted:
            raise DQAgentError(
                message=f"Session {self.session_id} has exceeded maximum tool calls",
                error_type="session_exhausted",
                details={
                    "session_id": self.session_id,
                    "max_tool_calls": self.max_tool_calls,
                    "tool_call_count": self._tool_call_count
                }
            )
        
        # Update last activity
        self._last_activity_at = datetime.utcnow()
        
        # Run the agent
        result = await self.agent.run(prompt=prompt, **kwargs)
        
        # Update tool call count from agent metrics
        self._tool_call_count = self.agent.metrics.tool_calls_total
        self._error_count = self.agent.metrics.tool_errors_total
        
        # Persist session state
        await self._save_state()
        
        return result
    
    async def interact(self, prompt: str, **kwargs: Any) -> Any:
        """
        Send a message to the agent in an existing conversation.
        
        This is an alias for run() for conversational interfaces.
        
        Args:
            prompt: The user message
            **kwargs: Additional arguments
            
        Returns:
            The agent's response
        """
        return await self.run(prompt=prompt, **kwargs)
    
    async def _save_state(self) -> None:
        """Save the session state to the store."""
        try:
            state = SessionState.from_agent(self.agent)
            # Update with session-level info
            state.session_id = self.session_id
            state.agent_type = self.agent_type
            state.created_at = self._created_at.isoformat()
            state.last_activity_at = self._last_activity_at.isoformat()
            state.tool_call_count = self._tool_call_count
            state.error_count = self._error_count
            
            await self.store.save_session(self.session_id, state)
            logger.debug(f"Session {self.session_id}: State saved")
        except Exception as e:
            logger.error(f"Session {self.session_id}: Failed to save state: {e}")
    
    async def load_state(self) -> Optional[SessionState]:
        """Load the session state from the store."""
        return await self.store.load_session(self.session_id)
    
    async def reset(self) -> None:
        """Reset the agent and session state."""
        self._agent = None
        self._created_at = datetime.utcnow()
        self._last_activity_at = self._created_at
        self._tool_call_count = 0
        self._error_count = 0
        logger.info(f"Session {self.session_id}: Reset")
    
    async def destroy(self) -> None:
        """Destroy the session and clean up resources."""
        # Delete from store
        await self.store.delete_session(self.session_id)
        
        # Clear agent reference
        self._agent = None
        
        logger.info(f"Session {self.session_id}: Destroyed")
    
    def get_state(self) -> Dict[str, Any]:
        """Get the current session state as a dictionary."""
        agent_state = self.agent.get_state() if self._agent else {}
        return {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "is_active": self.is_active,
            "is_exhausted": self.is_exhausted,
            "created_at": self._created_at.isoformat(),
            "last_activity_at": self._last_activity_at.isoformat(),
            "timeout_seconds": self.timeout_seconds,
            "max_tool_calls": self.max_tool_calls,
            "tool_call_count": self._tool_call_count,
            "error_count": self._error_count,
            "agent": agent_state,
        }
    
    @asynccontextmanager
    async def use(self):
        """
        Context manager for session lifecycle.
        
        Usage:
            async with session.use():
                result = await session.run("Do something")
        
        Ensures proper cleanup on exit.
        """
        try:
            yield self
        except Exception as e:
            logger.error(f"Session {self.session_id}: Error in context: {e}")
            raise


class AgentSessionManager:
    """
    Manages multiple agent sessions with cleanup and lifecycle.
    
    This is the main interface for creating, retrieving, and managing
    agent sessions in the DQ-RuleBuilder application.
    
    Usage:
        manager = AgentSessionManager()
        
        # Create a new session
        session = await manager.create_session(agent_type="connector")
        
        # Interact with the session
        result = await session.run("Onboard a database")
        
        # Get an existing session
        session = manager.get_session(session_id)
        
        # Clean up
        await manager.destroy_session(session_id)
    """
    
    def __init__(self, store: Optional[SessionStore] = None):
        """
        Initialize the session manager.
        
        Args:
            store: SessionStore for persistence
        """
        self.config = get_agent_config()
        self.store = store or FileSessionStore()
        self._sessions: Dict[str, AgentSession] = {}
        self._lock = Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        
        logger.info("AgentSessionManager initialized")
    
    async def create_session(
        self,
        agent_type: str = "general",
        session_id: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
        **kwargs: Any
    ) -> AgentSession:
        """
        Create a new agent session.
        
        Args:
            agent_type: Type of agent ("general", "connector", "rule", "steward")
            session_id: Session identifier (generated if None)
            timeout_seconds: Session timeout (uses config default if None)
            max_tool_calls: Maximum tool calls (uses config default if None)
            **kwargs: Additional arguments passed to DQAgent
            
        Returns:
            AgentSession instance
        """
        session_id = session_id or str(uuid.uuid4())
        
        session = AgentSession(
            session_id=session_id,
            agent_type=agent_type,
            store=self.store,
            timeout_seconds=timeout_seconds,
            max_tool_calls=max_tool_calls,
            **kwargs
        )
        
        with self._lock:
            self._sessions[session_id] = session
        
        logger.info(f"Created session {session_id} (type={agent_type})")
        
        return session
    
    def get_session(self, session_id: str) -> Optional[AgentSession]:
        """
        Get an existing session by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            AgentSession instance or None if not found
        """
        with self._lock:
            session = self._sessions.get(session_id)
        
        # Check if session exists in store but not in memory
        # (this can happen after restart)
        if session is None:
            # Try to restore from store
            session = self._restore_session(session_id)
        
        return session
    
    def _restore_session(self, session_id: str) -> Optional[AgentSession]:
        """Restore a session from the store."""
        import asyncio
        
        async def _async_restore():
            state = await self.store.load_session(session_id)
            if state is None:
                return None
            
            # Create a new session with the restored state
            session = AgentSession(
                session_id=state.session_id,
                agent_type=state.agent_type,
                store=self.store,
            )
            
            # Update session timestamps
            session._created_at = datetime.fromisoformat(state.created_at)
            session._last_activity_at = datetime.fromisoformat(state.last_activity_at)
            session._tool_call_count = state.tool_call_count
            session._error_count = state.error_count
            
            with self._lock:
                self._sessions[session_id] = session
            
            logger.info(f"Restored session {session_id} from store")
            return session
        
        # Run the async restoration
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(_async_restore())
        except RuntimeError:
            # No event loop running, create new session
            return None
    
    async def destroy_session(self, session_id: str) -> bool:
        """
        Destroy a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session was destroyed, False if not found
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)
        
        if session is not None:
            await session.destroy()
            logger.info(f"Destroyed session {session_id}")
            return True
        
        # Try to destroy from store even if not in memory
        deleted = await self.store.delete_session(session_id)
        if deleted:
            logger.info(f"Destroyed session {session_id} from store")
        
        return deleted
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all active sessions.
        
        Returns:
            List of session state dictionaries
        """
        states = []
        
        with self._lock:
            for session_id, session in self._sessions.items():
                states.append(session.get_state())
        
        # Also include sessions from store that aren't in memory
        try:
            stored_sessions = await self.store.list_sessions()
            for state in stored_sessions:
                if state.session_id not in [s["session_id"] for s in states]:
                    states.append({
                        "session_id": state.session_id,
                        "agent_type": state.agent_type,
                        "is_active": True,  # Assume active if in store
                        "created_at": state.created_at,
                        "last_activity_at": state.last_activity_at,
                    })
        except Exception as e:
            logger.warning(f"Failed to list stored sessions: {e}")
        
        return states
    
    async def cleanup_expired(self) -> int:
        """
        Clean up all expired sessions.
        
        Returns:
            Count of sessions destroyed
        """
        deleted_count = 0
        
        # Clean up from memory
        with self._lock:
            expired_sessions = [
                sid for sid, session in self._sessions.items()
                if not session.is_active
            ]
            
            for session_id in expired_sessions:
                session = self._sessions.pop(session_id)
                deleted_count += 1
                logger.info(f"Cleaned up expired session {session_id} from memory")
        
        # Clean up from store
        deleted_count += await self.store.cleanup_expired(self.config.session_timeout_seconds)
        
        logger.info(f"Total expired sessions cleaned up: {deleted_count}")
        return deleted_count
    
    async def cleanup_all(self) -> int:
        """
        Clean up all sessions.
        
        Returns:
            Count of sessions destroyed
        """
        deleted_count = 0
        
        # Clean up from memory
        with self._lock:
            for session_id, session in list(self._sessions.items()):
                await session.destroy()
                self._sessions.pop(session_id)
                deleted_count += 1
        
        # Clean up from store
        deleted_count += await self.store.cleanup_expired(0)  # 0 = delete all
        
        logger.info(f"Total sessions cleaned up: {deleted_count}")
        return deleted_count
    
    async def start_cleanup_task(self, interval_seconds: int = 300) -> None:
        """
        Start a background task to periodically clean up expired sessions.
        
        Args:
            interval_seconds: How often to run cleanup (default: 5 minutes)
        """
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
        
        async def _cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                    await self.cleanup_expired()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Cleanup task error: {e}")
        
        self._cleanup_task = asyncio.create_task(_cleanup_loop())
        logger.info(f"Started cleanup task (interval={interval_seconds}s)")
    
    async def stop_cleanup_task(self) -> None:
        """Stop the background cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Stopped cleanup task")


# Global session manager instance
_session_manager: Optional[AgentSessionManager] = None


def get_session_manager() -> AgentSessionManager:
    """
    Get the global session manager instance.
    
    Returns:
        AgentSessionManager: The singleton instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = AgentSessionManager()
    return _session_manager


def reset_session_manager() -> AgentSessionManager:
    """
    Reset the global session manager instance.
    
    Returns:
        AgentSessionManager: The new singleton instance
    """
    global _session_manager
    _session_manager = AgentSessionManager()
    return _session_manager
