"""
DQ Specialized Agents Module.

This module contains specialized agent implementations for specific DQ workflows.

Available Agents:
- connector_agent.py: Connector Onboarding Agent (LLM-1.7, Milestone B)
- rule_agent.py: Rule Engineer Agent (LLM-1.8, Milestone C)
- steward_agent.py: Data Steward Agent (LLM-1.9, Milestone C)
- general_agent.py: General DQ Assistant Agent (LLM-1.10)

Each specialized agent extends DQAgent with:
- Custom system prompts tailored to the domain
- Pre-configured tool sets
- Domain-specific helper methods
- Workflow automation

Usage:
    from agents.specialized.connector_agent import ConnectorOnboardingAgent
    from agents.specialized.rule_agent import RuleEngineerAgent
    from agents.specialized.steward_agent import DataStewardAgent
    
    # Create agents directly
    connector_agent = ConnectorOnboardingAgent(session_id="abc123")
    rule_agent = RuleEngineerAgent(session_id="def456")
    steward_agent = DataStewardAgent(session_id="ghi789")
    
    # Or use the factory (recommended)
    from agents.base import DQAgentFactory
    factory = DQAgentFactory()
    connector_agent = factory.create_connector_agent(session_id="abc123")
    rule_agent = factory.create_rule_agent(session_id="def456")
    steward_agent = factory.create_steward_agent(session_id="ghi789")

Related Feature Documentation:
- docs/features/LLM_1_AGENT_HARNESS.md
- docs/features/API_1_CONNECTORS.md
- docs/status/current/API_7_REAL_DQ_RULE_EXECUTION.md
"""

from .connector_agent import ConnectorOnboardingAgent
from .rule_agent import RuleEngineerAgent, RuleType, RuleSeverity, RULE_CATEGORIES
from .steward_agent import DataStewardAgent, DefinitionStatus, DEFINITION_QUALITY_CRITERIA, BCBS_239_PRINCIPLES
from .general_agent import GeneralDQAgent

__all__ = [
    # Connector Agent (LLM-1.7, Milestone B)
    "ConnectorOnboardingAgent",
    
    # Rule Agent (LLM-1.8, Milestone C)
    "RuleEngineerAgent",
    "RuleType",
    "RuleSeverity",
    "RULE_CATEGORIES",
    
    # Steward Agent (LLM-1.9, Milestone C)
    "DataStewardAgent",
    "DefinitionStatus",
    "DEFINITION_QUALITY_CRITERIA",
    "BCBS_239_PRINCIPLES",
    
    # General Agent (LLM-1.10, Milestone C)
    "GeneralDQAgent",
]
