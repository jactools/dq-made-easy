"""
Database Session Store for DQ Agent Harness.

This module provides a database-backed implementation of the SessionStore
abstract class, using SQLAlchemy ORM for persistence to PostgreSQL.

This enables:
- Multi-instance session sharing
- Session persistence across service restarts
- Historical session analysis
- Scalable session management
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..session import SessionState, SessionStore
from .config import get_database_config
from .models import (
    AgentSessionModel,
    AgentTypeEnum,
    SessionStatusEnum,
)


logger = logging.getLogger(__name__)


class DatabaseSessionStore(SessionStore):
    """
    Database-backed implementation of SessionStore.
    
    Uses SQLAlchemy with asyncpg for asynchronous PostgreSQL operations.
    Supports both sync and async usage patterns.
    
    Attributes:
        engine: Async SQLAlchemy engine
        async_session_maker: Async session factory
        config: Database configuration
    """
    
    def __init__(self, config=None):
        """
        Initialize the database session store.
        
        Args:
            config: Optional DatabaseConfig instance. If not provided,
                   uses the global configuration.
        """
        self.config = config or get_database_config()
        self.engine = None
        self.async_session_maker = None
        self._initialized = False
        
        logger.info(f"DatabaseSessionStore initialized with URL: {self.config.async_database_url}")
    
    async def initialize(self) -> None:
        """
        Initialize the database engine and session maker.
        
        This must be called before using the store.
        """
        if self._initialized:
            return
        
        # Create async engine
        self.engine = create_async_engine(
            self.config.async_database_url,
            echo=self.config.echo,
            pool_size=self.config.pool_size,
            max_overflow=self.config.max_overflow,
            pool_timeout=self.config.pool_timeout,
            pool_recycle=self.config.pool_recycle,
            pool_pre_ping=self.config.pool_pre_ping,
        )
        
        # Create async session maker
        self.async_session_maker = sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession
        )
        
        self._initialized = True
        logger.info("DatabaseSessionStore initialized successfully")
    
    async def close(self) -> None:
        """Close the database engine."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self._initialized = False
            logger.info("DatabaseSessionStore closed")
    
    @asynccontextmanager
    async def get_session(self):
        """
        Context manager for getting a database session.
        
        Yields:
            AsyncSession: A database session
        """
        if not self._initialized:
            await self.initialize()
        
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise
    
    # ========================================================================
    # SessionStore Interface Implementation
    # ========================================================================
    
    async def save_session(self, session_id: str, state: SessionState) -> None:
        """
        Save a session state to the database.
        
        Args:
            session_id: Unique session identifier
            state: SessionState to save
        """
        if not self._initialized:
            await self.initialize()
        
        async with self.get_session() as db_session:
            # Check if session exists
            existing = await db_session.get(AgentSessionModel, session_id)
            
            if existing:
                # Update existing session
                existing.agent_type = state.agent_type
                existing.agent_name = state.agent_name
                existing.status = state.status
                existing.last_activity_at = datetime.fromisoformat(state.last_activity_at) if state.last_activity_at else datetime.utcnow()
                existing.expires_at = datetime.fromisoformat(state.expires_at) if state.expires_at else None
                existing.tool_call_count = state.tool_call_count
                existing.error_count = state.error_count
                existing.context = state.context or {}
                existing.extra_metadata = state.metadata or {}
                existing.conversation_history = state.conversation_history or []
                
                logger.debug(f"Session {session_id}: Updated in database")
            else:
                # Create new session
                created_at = datetime.fromisoformat(state.created_at) if state.created_at else datetime.utcnow()
                last_activity_at = datetime.fromisoformat(state.last_activity_at) if state.last_activity_at else datetime.utcnow()
                expires_at = datetime.fromisoformat(state.expires_at) if state.expires_at else None
                
                db_session.add(AgentSessionModel(
                    session_id=session_id,
                    agent_type=state.agent_type,
                    agent_name=state.agent_name,
                    status=state.status,
                    created_at=created_at,
                    last_activity_at=last_activity_at,
                    expires_at=expires_at,
                    tool_call_count=state.tool_call_count,
                    error_count=state.error_count,
                    context=state.context or {},
                    extra_metadata=state.metadata or {},
                    conversation_history=state.conversation_history or [],
                ))
                
                logger.debug(f"Session {session_id}: Saved to database")
            
            await db_session.flush()
    
    async def load_session(self, session_id: str) -> Optional[SessionState]:
        """
        Load a session state from the database.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            SessionState if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()
        
        async with self.get_session() as db_session:
            model = await db_session.get(AgentSessionModel, session_id)
            
            if model is None:
                logger.debug(f"Session {session_id}: Not found in database")
                return None
            
            # Convert model to SessionState
            state = SessionState(
                session_id=model.session_id,
                agent_type=model.agent_type,
                agent_name=model.agent_name,
                status=model.status,
                created_at=model.created_at.isoformat() if model.created_at else None,
                last_activity_at=model.last_activity_at.isoformat() if model.last_activity_at else None,
                expires_at=model.expires_at.isoformat() if model.expires_at else None,
                tool_call_count=model.tool_call_count,
                error_count=model.error_count,
                context=model.context or {},
                metadata=model.extra_metadata or {},
                conversation_history=model.conversation_history or [],
            )
            
            logger.debug(f"Session {session_id}: Loaded from database")
            return state
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session from the database.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            True if session was deleted, False if not found
        """
        if not self._initialized:
            await self.initialize()
        
        async with self.get_session() as db_session:
            model = await db_session.get(AgentSessionModel, session_id)
            
            if model is None:
                logger.debug(f"Session {session_id}: Not found for deletion")
                return False
            
            await db_session.delete(model)
            logger.debug(f"Session {session_id}: Deleted from database")
            return True
    
    async def list_sessions(self) -> List[SessionState]:
        """
        List all sessions from the database.
        
        Returns:
            List of SessionState objects
        """
        if not self._initialized:
            await self.initialize()
        
        async with self.get_session() as db_session:
            result = await db_session.execute(select(AgentSessionModel))
            models = result.scalars().all()
            
            sessions = []
            for model in models:
                state = SessionState(
                    session_id=model.session_id,
                    agent_type=model.agent_type,
                    agent_name=model.agent_name,
                    status=model.status,
                    created_at=model.created_at.isoformat() if model.created_at else None,
                    last_activity_at=model.last_activity_at.isoformat() if model.last_activity_at else None,
                    expires_at=model.expires_at.isoformat() if model.expires_at else None,
                    tool_call_count=model.tool_call_count,
                    error_count=model.error_count,
                    context=model.context or {},
                    metadata=model.extra_metadata or {},
                    conversation_history=model.conversation_history or [],
                )
                sessions.append(state)
            
            # Sort by creation time (newest first)
            sessions.sort(key=lambda s: s.created_at, reverse=True)
            
            logger.debug(f"Listed {len(sessions)} sessions from database")
            return sessions
    
    async def cleanup_expired(self, timeout_seconds: int) -> int:
        """
        Clean up sessions older than timeout_seconds.
        
        Args:
            timeout_seconds: Sessions older than this will be deleted
            
        Returns:
            Count of sessions deleted
        """
        if not self._initialized:
            await self.initialize()
        
        cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
        deleted_count = 0
        
        async with self.get_session() as db_session:
            # Find expired sessions
            stmt = select(AgentSessionModel).where(
                AgentSessionModel.created_at < cutoff
            )
            result = await db_session.execute(stmt)
            expired_models = result.scalars().all()
            
            # Delete them
            for model in expired_models:
                await db_session.delete(model)
                deleted_count += 1
                logger.info(f"Session {model.session_id}: Cleaned up (expired)")
            
            await db_session.flush()
        
        logger.info(f"Cleaned up {deleted_count} expired sessions from database")
        return deleted_count
    
    # ========================================================================
    # Additional Database-Specific Methods
    # ========================================================================
    
    async def get_sessions_by_agent_type(self, agent_type: str) -> List[SessionState]:
        """
        Get all sessions of a specific agent type.
        
        Args:
            agent_type: Type of agent to filter by
            
        Returns:
            List of SessionState objects
        """
        if not self._initialized:
            await self.initialize()
        
        async with self.get_session() as db_session:
            stmt = select(AgentSessionModel).where(
                AgentSessionModel.agent_type == agent_type
            )
            result = await db_session.execute(stmt)
            models = result.scalars().all()
            
            return [
                SessionState(
                    session_id=m.session_id,
                    agent_type=m.agent_type,
                    agent_name=m.agent_name,
                    status=m.status,
                    created_at=m.created_at.isoformat() if m.created_at else None,
                    last_activity_at=m.last_activity_at.isoformat() if m.last_activity_at else None,
                    expires_at=m.expires_at.isoformat() if m.expires_at else None,
                    tool_call_count=m.tool_call_count,
                    error_count=m.error_count,
                    context=m.context or {},
                    metadata=m.metadata or {},
                    conversation_history=m.conversation_history or [],
                )
                for m in models
            ]
    
    async def get_active_sessions(self) -> List[SessionState]:
        """
        Get all active (non-expired) sessions.
        
        Returns:
            List of SessionState objects
        """
        if not self._initialized:
            await self.initialize()
        
        async with self.get_session() as db_session:
            stmt = select(AgentSessionModel).where(
                AgentSessionModel.status != SessionStatusEnum.EXPIRED,
                or_(
                    AgentSessionModel.expires_at > datetime.utcnow(),
                    AgentSessionModel.expires_at.is_(None)
                )
            )
            result = await db_session.execute(stmt)
            models = result.scalars().all()
            
            return [
                SessionState(
                    session_id=m.session_id,
                    agent_type=m.agent_type,
                    agent_name=m.agent_name,
                    status=m.status,
                    created_at=m.created_at.isoformat() if m.created_at else None,
                    last_activity_at=m.last_activity_at.isoformat() if m.last_activity_at else None,
                    expires_at=m.expires_at.isoformat() if m.expires_at else None,
                    tool_call_count=m.tool_call_count,
                    error_count=m.error_count,
                    context=m.context or {},
                    metadata=m.metadata or {},
                    conversation_history=m.conversation_history or [],
                )
                for m in models
            ]
    
    async def update_session_status(
        self, 
        session_id: str, 
        status: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update the status of a session.
        
        Args:
            session_id: Unique session identifier
            status: New status value
            metadata: Optional additional metadata to update
            
        Returns:
            True if session was updated, False if not found
        """
        if not self._initialized:
            await self.initialize()
        
        async with self.get_session() as db_session:
            model = await db_session.get(AgentSessionModel, session_id)
            
            if model is None:
                return False
            
            model.status = status
            if metadata:
                model.extra_metadata.update(metadata)
            
            model.last_activity_at = datetime.utcnow()
            
            logger.debug(f"Session {session_id}: Status updated to {status}")
            return True
    
    async def add_conversation_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add a message to a session's conversation history.
        
        Args:
            session_id: Unique session identifier
            role: Role of the message sender (user, assistant, system, tool)
            content: Message content
            metadata: Optional message metadata
            
        Returns:
            True if message was added, False if session not found
        """
        if not self._initialized:
            await self.initialize()
        
        async with self.get_session() as db_session:
            model = await db_session.get(AgentSessionModel, session_id)
            
            if model is None:
                return False
            
            # Initialize conversation history if empty
            if model.conversation_history is None:
                model.conversation_history = []
            
            # Add new message
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": metadata or {}
            }
            model.conversation_history.append(message)
            model.last_activity_at = datetime.utcnow()
            
            logger.debug(f"Session {session_id}: Added conversation message")
            return True
