"""
Base DQ Agent Classes for Pi Agent Harness Integration.

This module provides the foundational agent classes that extend Pi's Agent
to provide DQ-RuleBuilder specific functionality.

Key Classes:
- DQAgent: Base agent class with DQ-specific enhancements
- DQAgentFactory: Factory for creating specialized DQ agents
- DQAgentError: Custom exception class for agent errors
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

# Try to import Pi Agent classes, with graceful fallback for development
try:
    from pi_agent import Agent as PiAgent
    from pi_agent import Tool as PiTool
    PI_AGENT_AVAILABLE = True
except ImportError:
    # Create placeholder classes when pi-agent is not installed
    # This allows the module to be imported and tested during development
    PI_AGENT_AVAILABLE = False
    
    class PiAgent:
        """Placeholder for PiAgent when pi-agent is not installed."""
        def __init__(self, **kwargs):
            self.name = kwargs.get('name', 'placeholder_agent')
            self.system_prompt = kwargs.get('system_prompt', '')
            self.tools = []
            self.model = kwargs.get('model', 'placeholder')
            
    class PiTool:
        """Placeholder for Tool when pi-agent is not installed."""
        name = "placeholder_tool"
        description = "Placeholder tool - pi-agent not installed"
        
        def __init__(self, **kwargs):
            pass

from pydantic import BaseModel, Field

from telemetry import traced_span

from .config import DQAgentConfig, get_agent_config
from .tools.connector_tools import ConnectorTool
from .tools.rule_tools import RuleTool
from .tools.definition_tools import DefinitionTool


# Type variable for agent subclasses
TAgent = TypeVar('TAgent', bound='DQAgent')


logger = logging.getLogger(__name__)


class DQAgentError(Exception):
    """Base exception for DQ Agent errors."""
    
    def __init__(self, message: str, error_type: str = "agent_error", 
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_type = error_type
        self.details = details or {}
        self.timestamp = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.error_type,
            "message": str(self),
            "details": self.details,
            "timestamp": self.timestamp,
        }


class AgentStatus(str, Enum):
    """Status of an agent."""
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING = "waiting"  # Waiting for user input or tool result
    ERROR = "error"
    COMPLETED = "completed"


class ToolType(str, Enum):
    """Types of DQ-specific tools."""
    CONNECTOR = "connector"
    RULE = "rule"
    DEFINITION = "definition"
    METADATA = "metadata"
    FILE = "file"
    BASH = "bash"
    CUSTOM = "custom"


@dataclass
class ToolCall:
    """Represents a single tool call made by an agent."""
    tool_name: str
    tool_type: ToolType
    parameters: Dict[str, Any]
    session_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: Optional[float] = None
    success: Optional[bool] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tool_name": self.tool_name,
            "tool_type": self.tool_type.value,
            "parameters": self.parameters,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "success": self.success,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class AgentMetrics:
    """Metrics for agent operations."""
    tool_calls_total: int = 0
    tool_calls_by_type: Dict[str, int] = field(default_factory=dict)
    tool_errors_total: int = 0
    tokens_used: int = 0
    latency_ms: float = 0.0
    sessions_created: int = 0
    sessions_active: int = 0
    
    def record_tool_call(self, tool_type: str, success: bool = True) -> None:
        """Record a tool call."""
        self.tool_calls_total += 1
        self.tool_calls_by_type[tool_type] = self.tool_calls_by_type.get(tool_type, 0) + 1
        if not success:
            self.tool_errors_total += 1


class DQAgent(PiAgent):
    """
    Base DQ Agent class extending Pi's Agent with DQ-specific functionality.
    
    This class provides:
    - Integration with DQ configuration
    - Enhanced tool management
    - DQ-specific system prompts
    - Error handling and recovery
    - Metrics collection
    
    Attributes:
        config: DQAgentConfig instance
        session_id: Unique identifier for the current session
        status: Current agent status
        metrics: Metrics for this agent instance
        tool_calls: History of tool calls made
    """
    
    # Class-level system prompt that all DQ agents inherit
    DQ_SYSTEM_PROMPT = """
    You are a Data Quality AI Assistant for DQ-RuleBuilder.
    
    Your capabilities include:
    - Managing data source connectors
    - Creating and validating data quality rules
    - Generating data definitions and glossary entries
    - Querying metadata catalogs
    
    Guidelines:
    - Always validate inputs before taking actions
    - Never expose credentials or sensitive information
    - Provide clear, actionable error messages
    - Ask for clarification if requirements are ambiguous
    - Cite sources and references when providing information
    """
    
    def __init__(
        self,
        name: str = "dq_agent",
        model: Optional[str] = None,
        device_map: Optional[str] = None,
        config: Optional[DQAgentConfig] = None,
        tools: Optional[List[PiTool]] = None,
        system_prompt: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs: Any
    ):
        """
        Initialize a DQ Agent.
        
        Args:
            name: Name of the agent
            model: LLM model identifier (overrides config)
            device_map: Device map for model loading (overrides config)
            config: DQAgentConfig instance (uses global config if None)
            tools: List of PiTool instances
            system_prompt: Custom system prompt (prepends DQ_SYSTEM_PROMPT)
            session_id: Unique session identifier
            **kwargs: Additional arguments passed to PiAgent
        """
        self.config = config or get_agent_config()
        self.session_id = session_id or str(uuid.uuid4())
        self.name = name
        self.status = AgentStatus.IDLE
        self.metrics = AgentMetrics()
        self.tool_calls: List[ToolCall] = []
        self._initialized_at = datetime.utcnow()
        
        # Build model configuration
        model_config = {
            "model": model or self.config.llm_model_id,
            "device_map": device_map or self.config.llm_device_map,
        }
        
        # Build system prompt
        prompts = []
        if system_prompt:
            prompts.append(system_prompt)
        prompts.append(self.DQ_SYSTEM_PROMPT)
        full_system_prompt = "\n\n".join(prompts)
        
        # Initialize parent PiAgent
        super().__init__(
            name=name,
            system_prompt=full_system_prompt,
            tools=tools or [],
            **model_config,
            **kwargs
        )
        
        logger.info(f"DQAgent '{name}' initialized with session {self.session_id}")
    
    def _record_tool_call(
        self,
        tool_name: str,
        tool_type: ToolType,
        parameters: Dict[str, Any],
        start_time: datetime,
        success: bool,
        result: Optional[Any] = None,
        error: Optional[str] = None
    ) -> ToolCall:
        """Record a tool call for metrics and history."""
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        tool_call = ToolCall(
            tool_name=tool_name,
            tool_type=tool_type,
            parameters=parameters,
            session_id=self.session_id,
            timestamp=start_time,
            duration_ms=duration_ms,
            success=success,
            result=result,
            error=error,
        )
        self.tool_calls.append(tool_call)
        self.metrics.record_tool_call(tool_type.value, success=success)
        return tool_call
    
    async def run(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        max_iterations: Optional[int] = None,
        **kwargs: Any
    ) -> Any:
        """
        Run the agent with a prompt.
        
        This method wraps PiAgent.run() with DQ-specific enhancements:
        - Status tracking
        - Error handling
        - Metrics collection
        
        Args:
            prompt: The user prompt
            context: Optional context dictionary
            max_iterations: Maximum number of iterations (overrides config)
            **kwargs: Additional arguments passed to PiAgent.run()
            
        Returns:
            The agent's response
            
        Raises:
            DQAgentError: If agent execution fails
        """
        self.status = AgentStatus.PROCESSING
        start_time = datetime.utcnow()
        
        try:
            # Set max iterations from config if not specified
            if max_iterations is None:
                max_iterations = self.config.max_tool_calls_per_session
            
            # Build context with session info
            run_context = context or {}
            run_context["session_id"] = self.session_id
            run_context["agent_name"] = self.name
            run_context["timestamp"] = start_time.isoformat()
            
            logger.debug(f"Agent {self.session_id}: Running with prompt: {prompt[:100]}...")
            
            # Execute the agent within an explicit tracing span
            with traced_span(
                "dq_agent.run",
                agent_name=self.name,
                session_id=self.session_id,
                model=self.config.llm_model_id,
            ):
                result = await super().run(
                    prompt=prompt,
                    context=run_context,
                    max_iterations=max_iterations,
                    **kwargs
                )
            
            self.status = AgentStatus.COMPLETED
            self.metrics.latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            logger.info(f"Agent {self.session_id}: Completed in {self.metrics.latency_ms:.2f}ms")
            
            return result
            
        except Exception as e:
            self.status = AgentStatus.ERROR
            error_msg = f"Agent {self.session_id} failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise DQAgentError(
                message=error_msg,
                error_type="agent_execution_error",
                details={"session_id": self.session_id, "error_type": type(e).__name__}
            ) from e
    
    async def run_with_tools(
        self,
        prompt: str,
        available_tools: List[PiTool],
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Any:
        """
        Run the agent with a specific set of tools for this execution.
        
        This is useful when you want to provide a custom tool set for a
        specific task without modifying the agent's default tools.
        
        Args:
            prompt: The user prompt
            available_tools: List of tools available for this run
            context: Optional context dictionary
            **kwargs: Additional arguments
            
        Returns:
            The agent's response
        """
        # Save original tools
        original_tools = self.tools
        
        try:
            # Set new tools
            self.tools = available_tools
            
            # Run the agent
            result = await self.run(prompt=prompt, context=context, **kwargs)
            
            return result
            
        finally:
            # Restore original tools
            self.tools = original_tools
    
    def add_tool(self, tool: PiTool) -> None:
        """Add a tool to the agent."""
        if tool not in self.tools:
            self.tools.append(tool)
            logger.debug(f"Agent {self.session_id}: Added tool '{tool.name}'")
    
    def remove_tool(self, tool_name: str) -> bool:
        """Remove a tool from the agent by name."""
        for i, tool in enumerate(self.tools):
            if tool.name == tool_name:
                del self.tools[i]
                logger.debug(f"Agent {self.session_id}: Removed tool '{tool_name}'")
                return True
        return False
    
    def get_tool(self, tool_name: str) -> Optional[PiTool]:
        """Get a tool by name."""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None
    
    def get_tool_calls_by_type(self, tool_type: ToolType) -> List[ToolCall]:
        """Get all tool calls of a specific type."""
        return [tc for tc in self.tool_calls if tc.tool_type == tool_type]
    
    def clear_tool_history(self) -> None:
        """Clear the tool call history."""
        self.tool_calls.clear()
    
    def reset(self) -> None:
        """Reset the agent state."""
        self.status = AgentStatus.IDLE
        self.tool_calls.clear()
        self.metrics = AgentMetrics()
        self._initialized_at = datetime.utcnow()
        logger.info(f"Agent {self.session_id}: State reset")
    
    def get_state(self) -> Dict[str, Any]:
        """Get the current agent state as a dictionary."""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "status": self.status.value,
            "initialized_at": self._initialized_at.isoformat(),
            "metrics": {
                "tool_calls_total": self.metrics.tool_calls_total,
                "tool_calls_by_type": self.metrics.tool_calls_by_type,
                "tool_errors_total": self.metrics.tool_errors_total,
                "tokens_used": self.metrics.tokens_used,
                "latency_ms": self.metrics.latency_ms,
            },
            "tool_call_history": [tc.to_dict() for tc in self.tool_calls[-10:]],  # Last 10
        }


class DQAgentFactory:
    """
    Factory for creating specialized DQ agents.
    
    This factory provides methods to create different types of DQ agents
    with pre-configured tools and system prompts.
    
    Usage:
        factory = DQAgentFactory()
        connector_agent = factory.create_connector_agent(session_id="abc123")
        rule_agent = factory.create_rule_agent(session_id="def456")
    """
    
    def __init__(self, config: Optional[DQAgentConfig] = None):
        """
        Initialize the factory.
        
        Args:
            config: DQAgentConfig instance (uses global config if None)
        """
        self.config = config or get_agent_config()
        self._agents: Dict[str, DQAgent] = {}
        self._specialized_agents: Dict[str, Any] = {}
    
    def create_agent(
        self,
        agent_type: str = "general",
        name: Optional[str] = None,
        session_id: Optional[str] = None,
        tools: Optional[List[PiTool]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> DQAgent:
        """
        Create a DQ agent of a specific type.
        
        Args:
            agent_type: Type of agent ("general", "connector", "rule", "steward")
            name: Custom name for the agent
            session_id: Session identifier
            tools: Additional tools
            system_prompt: Custom system prompt
            **kwargs: Additional arguments passed to DQAgent
            
        Returns:
            DQAgent instance
        """
        agent_name = name or f"dq_{agent_type}_agent"
        
        # Create the base agent
        agent = DQAgent(
            name=agent_name,
            session_id=session_id,
            tools=tools or [],
            system_prompt=system_prompt,
            **kwargs
        )
        
        # Store reference
        if session_id:
            self._agents[session_id] = agent
        
        return agent
    
    def create_connector_agent(
        self,
        session_id: Optional[str] = None,
        **kwargs: Any
    ) -> 'ConnectorOnboardingAgent':
        """
        Create a Connector Onboarding Agent (LLM-1.7).
        
        This agent specializes in managing data source connectors.
        
        Args:
            session_id: Session identifier
            **kwargs: Additional arguments
            
        Returns:
            DQAgent configured for connector operations
        """
        # Import here to avoid circular imports
        from .specialized.connector_agent import ConnectorOnboardingAgent
        
        agent = ConnectorOnboardingAgent(
            session_id=session_id,
            config=self.config,
            **kwargs
        )
        
        # Store reference
        if session_id:
            self._agents[session_id] = agent
            self._specialized_agents[session_id] = agent
        
        return agent
    
    def create_rule_agent(
        self,
        session_id: Optional[str] = None,
        **kwargs: Any
    ) -> 'RuleEngineerAgent':
        """
        Create a Rule Engineer Agent (LLM-1.8).
        
        This agent specializes in data quality rule management.
        
        Args:
            session_id: Session identifier
            **kwargs: Additional arguments
            
        Returns:
            DQAgent configured for rule operations
        """
        # Import here to avoid circular imports
        from .specialized.rule_agent import RuleEngineerAgent
        
        agent = RuleEngineerAgent(
            session_id=session_id,
            config=self.config,
            **kwargs
        )
        
        # Store reference
        if session_id:
            self._agents[session_id] = agent
            self._specialized_agents[session_id] = agent
        
        return agent
    
    def create_steward_agent(
        self,
        session_id: Optional[str] = None,
        **kwargs: Any
    ) -> 'DataStewardAgent':
        """
        Create a Data Steward Agent (LLM-1.9).
        
        This agent specializes in data definition and governance.
        
        Args:
            session_id: Session identifier
            **kwargs: Additional arguments
            
        Returns:
            DQAgent configured for data stewardship
        """
        # Import here to avoid circular imports
        from .specialized.steward_agent import DataStewardAgent
        
        agent = DataStewardAgent(
            session_id=session_id,
            config=self.config,
            **kwargs
        )
        
        # Store reference
        if session_id:
            self._agents[session_id] = agent
            self._specialized_agents[session_id] = agent
        
        return agent
    
    def create_general_agent(
        self,
        session_id: Optional[str] = None,
        **kwargs: Any
    ) -> 'GeneralDQAgent':
        """
        Create a General DQ Assistant Agent (LLM-1.10).

        This agent provides general-purpose assistance for DQ-RuleBuilder.
        It can answer questions, provide guidance, troubleshoot issues, and
        orchestrate across specialized agents.

        Args:
            session_id: Session identifier
            **kwargs: Additional arguments passed to GeneralDQAgent
            
        Returns:
            GeneralDQAgent instance
        """
        # Import here to avoid circular imports
        from .specialized.general_agent import GeneralDQAgent
        
        agent = GeneralDQAgent(
            session_id=session_id,
            config=self.config,
            **kwargs
        )
        
        # Store reference
        if session_id:
            self._agents[session_id] = agent
            self._specialized_agents[session_id] = agent
        
        return agent
    
    def get_agent(self, session_id: str) -> Optional[DQAgent]:
        """Get an agent by session ID."""
        return self._agents.get(session_id)
    
    def destroy_agent(self, session_id: str) -> bool:
        """Destroy an agent by session ID."""
        if session_id in self._agents:
            agent = self._agents.pop(session_id)
            logger.info(f"Agent {session_id}: Destroyed")
            return True
        return False
    
    def cleanup(self) -> int:
        """Clean up all agents and return count of destroyed agents."""
        count = len(self._agents)
        for session_id in list(self._agents.keys()):
            self.destroy_agent(session_id)
        return count


# Convenience function for creating agents
def create_dq_agent(
    agent_type: str = "general",
    session_id: Optional[str] = None,
    **kwargs: Any
) -> DQAgent:
    """
    Convenience function to create a DQ agent.
    
    For specialized agents (connector, rule, steward), returns the actual
    specialized agent class instance. For "general", returns a base DQAgent.
    
    Args:
        agent_type: Type of agent ("general", "connector", "rule", "steward")
        session_id: Session identifier
        **kwargs: Additional arguments
        
    Returns:
        DQAgent instance (or specialized agent instance)
    """
    factory = DQAgentFactory()
    
    if agent_type == "connector":
        return factory.create_connector_agent(session_id=session_id, **kwargs)
    elif agent_type == "rule":
        return factory.create_rule_agent(session_id=session_id, **kwargs)
    elif agent_type == "steward":
        return factory.create_steward_agent(session_id=session_id, **kwargs)
    elif agent_type == "general":
        return factory.create_general_agent(session_id=session_id, **kwargs)
    else:
        # Fallback to base agent for unknown types
        return factory.create_agent(agent_type="general", session_id=session_id, **kwargs)
