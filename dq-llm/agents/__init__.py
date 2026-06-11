"""
DQ-RuleBuilder Agent Harness Module

This module integrates Pi Agent Harness (https://pi.dev/) into the DQ-RuleBuilder
LLM backend, enabling agentic workflows for:
- Connector onboarding and management
- Data quality rule extraction and validation
- Metadata discovery and definition generation

Module Structure:
- config.py: Configuration management for agents
- base.py: Base DQ agent classes
- session.py: Session management and persistence
- tools/: DQ-specific tool implementations
  - __init__.py
  - connector_tools.py
  - rule_tools.py
  - definition_tools.py
- specialized/: Specialized agent implementations
  - __init__.py
  - connector_agent.py
  - rule_agent.py
  - steward_agent.py

Related Feature Documentation:
- docs/features/LLM_1_AGENT_HARNESS.md
- docs/features/API_1_CONNECTORS.md
- docs/status/current/API_7_REAL_DQ_RULE_EXECUTION.md
"""

from .config import DQAgentConfig, get_agent_config
from .base import DQAgent, DQAgentFactory, create_dq_agent
from .session import AgentSession, AgentSessionManager, SessionState, SessionStore, FileSessionStore
from .specialized import (
    ConnectorOnboardingAgent,
    RuleEngineerAgent,
    RuleType,
    RuleSeverity,
    RULE_CATEGORIES,
    DataStewardAgent,
    DefinitionStatus,
    DEFINITION_QUALITY_CRITERIA,
    BCBS_239_PRINCIPLES,
    GeneralDQAgent,
)

# Audit and Compliance (LLM-1.15, LLM-1.16)
from .audit import (
    AgentAuditLogger,
    AuditLogEntry,
    SecretsRedactor,
    RedactionConfig,
    get_audit_logger,
    reset_audit_logger,
    get_redactor,
    reset_redactor,
    audit_agent_action,
    DEFAULT_SENSITIVE_KEYS,
    DEFAULT_SENSITIVE_PATTERNS,
)

# Database persistence
from .database import (
    DatabaseConfig,
    get_database_config,
    reset_database_config,
    Base,
    AgentSessionModel,
    AgentAuditLogModel,
    AgentMetricModel,
    DatabaseSessionStore,
)

# Version of the agent harness integration
__version__ = "0.1.0"

__all__ = [
    # Configuration
    "DQAgentConfig",
    "get_agent_config",
    # Base classes
    "DQAgent",
    "DQAgentFactory",
    "create_dq_agent",
    # Session management
    "AgentSession",
    "AgentSessionManager",
    "SessionState",
    "SessionStore",
    "FileSessionStore",
    # Specialized Agents (LLM-1.7, LLM-1.8, LLM-1.9, LLM-1.10)
    "ConnectorOnboardingAgent",
    "RuleEngineerAgent",
    "RuleType",
    "RuleSeverity",
    "RULE_CATEGORIES",
    "DataStewardAgent",
    "DefinitionStatus",
    "DEFINITION_QUALITY_CRITERIA",
    "BCBS_239_PRINCIPLES",
    "GeneralDQAgent",
    # Audit and Compliance (LLM-1.15, LLM-1.16)
    "AgentAuditLogger",
    "AuditLogEntry",
    "SecretsRedactor",
    "RedactionConfig",
    "get_audit_logger",
    "reset_audit_logger",
    "get_redactor",
    "reset_redactor",
    "audit_agent_action",
    "DEFAULT_SENSITIVE_KEYS",
    "DEFAULT_SENSITIVE_PATTERNS",
    # Database persistence
    "DatabaseConfig",
    "get_database_config",
    "reset_database_config",
    "Base",
    "AgentSessionModel",
    "AgentAuditLogModel",
    "AgentMetricModel",
    "DatabaseSessionStore",
    # Version
    "__version__",
]
