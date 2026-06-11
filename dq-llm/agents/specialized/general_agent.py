"""
General DQ Assistant Agent for DQ-RuleBuilder Pi Agent Harness.

This specialized agent provides a general-purpose AI assistant for DQ-RuleBuilder
that can handle a variety of data quality tasks and orchestrate across multiple
specialized agents when needed.

Purpose:
    Provide a versatile AI assistant that can help with any DQ-related task,
    including those that span multiple domains (connectors, rules, definitions).

Capabilities:
    - Answer general questions about DQ-RuleBuilder
    - Provide guidance on best practices
    - Help troubleshoot issues
    - Orchestrate multi-step workflows
    - Delegate to specialized agents when appropriate
    - Provide educational information about data quality concepts

Tracked Work Item: LLM-1.10
Milestone: C (Full Agent Suite)
"""

import logging
from typing import Any, Dict, List, Optional

# Try to import Pi Agent classes, with graceful fallback for development
try:
    from pi_agent import Agent as PiAgent
    from pi_agent import Tool as PiTool
    PI_AGENT_AVAILABLE = True
except ImportError:
    PI_AGENT_AVAILABLE = False
    # Create placeholder for PiTool when pi-agent is not installed
    class PiTool:
        """Placeholder for Tool when pi-agent is not installed."""
        name = "placeholder_tool"
        description = "Placeholder tool - pi-agent not installed"
        
        def __init__(self, **kwargs):
            pass

from ..base import DQAgent, DQAgentError, AgentStatus
from ..config import DQAgentConfig, get_agent_config

logger = logging.getLogger(__name__)


class GeneralDQAgent(DQAgent):
    """
    General-purpose DQ Assistant Agent.
    
    This agent serves as a versatile assistant for DQ-RuleBuilder users.
    It can handle general inquiries, provide guidance, troubleshoot issues,
    and delegate to specialized agents when needed.
    
    Unlike the specialized agents (Connector, Rule, Steward), this agent
    doesn't have a narrow focus and can assist with any DQ-related task.
    
    Attributes:
        available_tools: All available tools for general assistance
        knowledge_base: Internal knowledge about DQ-RuleBuilder
    """
    
    # System prompt for general DQ assistant
    SYSTEM_PROMPT = """
    You are a General Data Quality Assistant for DQ-RuleBuilder.
    Your expertise: data quality management, data governance, DQ-RuleBuilder platform.
    
    Primary Tasks:
    1. Answer general questions about DQ-RuleBuilder
    2. Provide guidance on data quality best practices
    3. Help troubleshoot DQ issues
    4. Explain data quality concepts
    5. Assist with platform navigation
    6. Delegate to specialized agents when appropriate
    
    DQ-RuleBuilder Knowledge:
    - DQ-RuleBuilder is a data quality management platform
    - Key components: dq-ui (React/Vite), dq-api (FastAPI), dq-llm (LLM service), dq-engine (Spark)
    - Core features: Connector management, Rule execution, Metadata management, Definition generation
    - Specialized agents available: Connector Onboarding, Rule Engineer, Data Steward
    
    Data Quality Concepts:
    - Completeness: All required data is present (NOT_NULL rules)
    - Uniqueness: No duplicate values where uniqueness is required (UNIQUE rules)
    - Validity: Data conforms to expected formats and values (PATTERN, IN_SET, RANGE rules)
    - Consistency: Data is consistent across related fields and tables (REFERENTIAL_INTEGRITY, CONSISTENCY rules)
    - Accuracy: Data correctly represents real-world values (ACCURACY rules)
    - Timeliness: Data is available when needed
    
    Guidelines:
    - Always provide clear, actionable advice
    - Explain concepts in simple terms
    - Offer to connect users with specialized agents for specific tasks
    - Be transparent about limitations
    - Suggest relevant documentation and resources
    - Prioritize user needs and context
    
    Response Format:
    - Use clear, professional language
    - Structure responses with headings and bullet points
    - Include examples when helpful
    - Provide next steps and recommendations
    - Cite sources and references where applicable
    
    When to Delegate:
    - Connector-specific questions → Suggest Connector Onboarding Agent
    - Rule creation/extraction questions → Suggest Rule Engineer Agent
    - Definition/glossary questions → Suggest Data Steward Agent
    - Multi-step workflows → Offer to orchestrate across agents
    
    Best Practices for Data Quality:
    - Start with critical data elements (primary keys, foreign keys)
    - Define clear business rules before implementation
    - Test rules with sample data before production
    - Monitor rule performance and exceptions
    - Document all data quality decisions
    - Establish clear ownership and accountability
    """
    
    # Knowledge base of DQ-RuleBuilder features
    KNOWLEDGE_BASE = {
        "platform": {
            "description": "DQ-RuleBuilder is an enterprise data quality management platform",
            "components": {
                "dq-ui": "React/Vite-based user interface for managing DQ rules and connectors",
                "dq-api": "FastAPI-based REST API for platform operations",
                "dq-llm": "LLM service with Pi Agent Harness for AI-assisted workflows",
                "dq-engine": "Spark-based execution engine for running DQ rules",
            },
            "features": [
                "Connector onboarding for PostgreSQL, SQL Server, ADLS, S3, and API sources",
                "Data quality rule definition and execution",
                "Metadata discovery and catalog management",
                "Data definition and glossary management",
                "Exception tracking and analysis",
                "Audit trails and compliance reporting",
            ],
        },
        "agents": {
            "connector": {
                "name": "Connector Onboarding Agent",
                "purpose": "Automate connector configuration and onboarding",
                "capabilities": [
                    "Configure new connectors",
                    "Validate configurations",
                    "Test connections",
                    "Discover metadata",
                    "Sync metadata to catalog",
                    "Diagnose connection issues",
                ],
                "when_to_use": [
                    "Setting up new data sources",
                    "Troubleshooting connection problems",
                    "Discovering database schemas",
                    "Syncing metadata from external systems",
                ],
            },
            "rule": {
                "name": "Rule Engineer Agent",
                "purpose": "Create and manage data quality rules",
                "capabilities": [
                    "Extract rules from natural language",
                    "Validate rule configurations",
                    "Assign rules to metadata",
                    "Execute rules and analyze results",
                    "Suggest rule improvements",
                ],
                "when_to_use": [
                    "Creating new DQ rules",
                    "Validating rule logic",
                    "Analyzing rule execution results",
                    "Getting rule recommendations",
                ],
            },
            "steward": {
                "name": "Data Steward Agent",
                "purpose": "Manage data definitions and governance",
                "capabilities": [
                    "Generate data definitions",
                    "Create glossary entries",
                    "Suggest data stewards",
                    "Validate against policies",
                    "Track approval workflows",
                ],
                "when_to_use": [
                    "Defining business terms",
                    "Creating data dictionaries",
                    "Establishing data ownership",
                    "Ensuring compliance",
                ],
            },
        },
        "rule_types": {
            "NOT_NULL": {
                "category": "Completeness",
                "description": "Ensures a field is not null or empty",
                "example": "Customer email must not be null",
                "use_case": "Critical fields that must always have values",
            },
            "UNIQUE": {
                "category": "Uniqueness",
                "description": "Ensures values are unique across the dataset",
                "example": "Customer ID must be unique",
                "use_case": "Primary keys and unique constraints",
            },
            "PATTERN": {
                "category": "Validity",
                "description": "Validates field format against a regex pattern",
                "example": "Email must match email format pattern",
                "use_case": "Standardized fields like email, phone, dates",
            },
            "RANGE": {
                "category": "Validity",
                "description": "Validates numeric value is within a range",
                "example": "Age must be between 0 and 120",
                "use_case": "Numeric fields with minimum/maximum values",
            },
            "IN_SET": {
                "category": "Validity",
                "description": "Validates value is in a set of allowed values",
                "example": "Status must be one of: active, inactive, pending",
                "use_case": "Categorical fields with limited valid values",
            },
            "REFERENTIAL_INTEGRITY": {
                "category": "Consistency",
                "description": "Validates foreign key relationships",
                "example": "Department ID must reference valid department",
                "use_case": "Foreign key relationships between tables",
            },
            "CUSTOM_SQL": {
                "category": "Custom",
                "description": "Executes custom SQL validation logic",
                "example": "SELECT COUNT(*) FROM orders WHERE amount > 1000",
                "use_case": "Complex validation logic that can't be expressed with standard rules",
            },
            "ACCURACY": {
                "category": "Accuracy",
                "description": "Checks data accuracy against reference data",
                "example": "Revenue must match source system within tolerance",
                "use_case": "Critical business metrics that must be accurate",
            },
            "CONSISTENCY": {
                "category": "Consistency",
                "description": "Validates cross-field consistency rules",
                "example": "If status=active then end_date must be null",
                "use_case": "Business logic that spans multiple fields",
            },
        },
    }
    
    def __init__(
        self,
        name: str = "dq_general_agent",
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        config: Optional[DQAgentConfig] = None,
        session_id: Optional[str] = None,
        tools: Optional[List[PiTool]] = None,
        **kwargs: Any
    ):
        """
        Initialize the General DQ Assistant Agent.
        
        Args:
            name: Agent name
            api_base_url: Base URL for DQ-API (overrides config)
            api_key: API key for authentication (overrides config)
            config: DQAgentConfig instance
            session_id: Session identifier
            tools: List of tools for the agent
            **kwargs: Additional arguments passed to DQAgent
        """
        # Get configuration
        self.agent_config = config or get_agent_config()
        
        # Initialize with general tools (can be extended with specialized tools)
        # By default, this agent has no specialized tools but can use the LLM's knowledge
        self.available_tools = tools or []
        
        # Track conversation context
        self.conversation_context: Dict[str, Any] = {}
        self.referenced_agents: List[str] = []
        
        # Initialize parent
        super().__init__(
            name=name,
            session_id=session_id,
            config=self.agent_config,
            tools=self.available_tools,
            system_prompt=self.SYSTEM_PROMPT,
            **kwargs
        )
        
        logger.info(f"GeneralDQAgent '{name}' initialized with session {self.session_id}")
    
    async def assist(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Provide general assistance with DQ-RuleBuilder tasks.
        
        This is the primary entry point for the general agent. It:
        1. Analyzes the user's query
        2. Determines the appropriate response or action
        3. May delegate to specialized agents if needed
        4. Returns helpful information and next steps
        
        Args:
            query: User's question or request
            context: Optional context (current task, user info, etc.)
            **kwargs: Additional parameters
            
        Returns:
            Dictionary with response, suggestions, and metadata
        """
        try:
            # Analyze the query to determine intent
            intent = self._analyze_intent(query)
            
            # Update conversation context
            if context:
                self.conversation_context.update(context)
            self.conversation_context["last_query"] = query
            self.conversation_context["last_intent"] = intent
            
            # Generate response based on intent
            response = self._generate_response(query, intent)
            
            return {
                "success": True,
                "response": response.get("text", ""),
                "intent": intent,
                "suggestions": response.get("suggestions", []),
                "next_steps": response.get("next_steps", []),
                "referenced_agents": response.get("referenced_agents", []),
                "context_updated": True,
            }
            
        except Exception as e:
            logger.error(f"Assistance failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "response": "Sorry, I encountered an error processing your request.",
            }
    
    async def explain_concept(
        self,
        concept: str,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Explain a data quality or DQ-RuleBuilder concept.
        
        Args:
            concept: Concept to explain (e.g., "NOT_NULL rule", "connector onboarding")
            **kwargs: Additional parameters
            
        Returns:
            Explanation of the concept with examples
        """
        try:
            # Check knowledge base first
            if concept.lower() in {k.lower(): v for k, v in self.KNOWLEDGE_BASE.get("rule_types", {}).items()}:
                rule_type = concept.upper()
                info = self.KNOWLEDGE_BASE["rule_types"].get(rule_type, {})
                return {
                    "success": True,
                    "concept": concept,
                    "category": info.get("category"),
                    "description": info.get("description"),
                    "example": info.get("example"),
                    "use_case": info.get("use_case"),
                    "type": "rule_type",
                }
            
            # Check for agent types
            if concept.lower() in {k.lower(): v for k, v in self.KNOWLEDGE_BASE.get("agents", {}).items()}:
                agent_type = concept.lower()
                info = self.KNOWLEDGE_BASE["agents"].get(agent_type, {})
                return {
                    "success": True,
                    "concept": concept,
                    "name": info.get("name"),
                    "purpose": info.get("purpose"),
                    "capabilities": info.get("capabilities"),
                    "when_to_use": info.get("when_to_use"),
                    "type": "agent",
                }
            
            # Check platform information
            if concept.lower() in self.KNOWLEDGE_BASE.get("platform", {}):
                info = self.KNOWLEDGE_BASE["platform"]
                return {
                    "success": True,
                    "concept": concept,
                    "description": info.get("description"),
                    "components": info.get("components"),
                    "features": info.get("features"),
                    "type": "platform",
                }
            
            # Fall back to general explanation
            return {
                "success": True,
                "concept": concept,
                "explanation": self._generate_general_explanation(concept),
                "type": "general",
            }
            
        except Exception as e:
            logger.error(f"Concept explanation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "concept": concept,
            }
    
    async def suggest_workflow(
        self,
        task: str,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Suggest a workflow for completing a DQ task.
        
        Args:
            task: Description of the task to accomplish
            **kwargs: Additional parameters
            
        Returns:
            Suggested workflow with steps and recommendations
        """
        try:
            task_lower = task.lower()
            workflow = {
                "task": task,
                "steps": [],
                "estimated_time": None,
                "recommended_agents": [],
                "prerequisites": [],
            }
            
            # Onboard connector workflow
            if any(word in task_lower for word in ["onboard", "connect", "setup", "configure"]) and \
               any(word in task_lower for word in ["connector", "database", "data source", "adls", "s3"]):
                workflow["steps"] = [
                    {"step": 1, "action": "Identify connector type", "agent": None},
                    {"step": 2, "action": "Gather connection details", "agent": None},
                    {"step": 3, "action": "Configure connector", "agent": "connector"},
                    {"step": 4, "action": "Validate configuration", "agent": "connector"},
                    {"step": 5, "action": "Test connection", "agent": "connector"},
                    {"step": 6, "action": "Discover metadata", "agent": "connector"},
                    {"step": 7, "action": "Sync to catalog", "agent": "connector"},
                    {"step": 8, "action": "Create DQ rules", "agent": "rule"},
                    {"step": 9, "action": "Assign rules to metadata", "agent": "rule"},
                ]
                workflow["recommended_agents"] = ["connector", "rule"]
                workflow["estimated_time"] = "10-30 minutes"
                workflow["prerequisites"] = ["Connection details (host, port, credentials)", "Proper network access"]
                
            # Create rules workflow
            elif any(word in task_lower for word in ["create rule", "define rule", "rule for", "validate"]) and \
                 any(word in task_lower for word in ["rule", "data quality", "dq"]):
                workflow["steps"] = [
                    {"step": 1, "action": "Identify data to validate", "agent": None},
                    {"step": 2, "action": "Determine rule type", "agent": "rule"},
                    {"step": 3, "action": "Extract rules from requirements", "agent": "rule"},
                    {"step": 4, "action": "Validate rule configuration", "agent": "rule"},
                    {"step": 5, "action": "Assign rules to metadata", "agent": "rule"},
                    {"step": 6, "action": "Test rule execution", "agent": "rule"},
                    {"step": 7, "action": "Monitor exceptions", "agent": None},
                ]
                workflow["recommended_agents"] = ["rule"]
                workflow["estimated_time"] = "5-15 minutes"
                workflow["prerequisites"] = ["Metadata available in catalog", "Clear business requirements"]
                
            # Define data workflow
            elif any(word in task_lower for word in ["define", "definition", "glossary", "term"]) and \
                 any(word in task_lower for word in ["data", "business", "meaning"]):
                workflow["steps"] = [
                    {"step": 1, "action": "Identify term to define", "agent": None},
                    {"step": 2, "action": "Gather context and requirements", "agent": "steward"},
                    {"step": 3, "action": "Generate draft definition", "agent": "steward"},
                    {"step": 4, "action": "Validate against quality criteria", "agent": "steward"},
                    {"step": 5, "action": "Create glossary entry", "agent": "steward"},
                    {"step": 6, "action": "Submit for approval", "agent": "steward"},
                    {"step": 7, "action": "Track approval workflow", "agent": "steward"},
                ]
                workflow["recommended_agents"] = ["steward"]
                workflow["estimated_time"] = "15-45 minutes"
                workflow["prerequisites"] = ["Stakeholder input", "Source system information"]
                
            # General DQ assessment workflow
            else:
                workflow["steps"] = [
                    {"step": 1, "action": "Identify data sources", "agent": "connector"},
                    {"step": 2, "action": "Onboard connectors", "agent": "connector"},
                    {"step": 3, "action": "Discover and catalog metadata", "agent": "connector"},
                    {"step": 4, "action": "Define business terms", "agent": "steward"},
                    {"step": 5, "action": "Create data quality rules", "agent": "rule"},
                    {"step": 6, "action": "Execute rules and analyze results", "agent": "rule"},
                    {"step": 7, "action": "Monitor and improve", "agent": None},
                ]
                workflow["recommended_agents"] = ["connector", "steward", "rule"]
                workflow["estimated_time"] = "1-4 hours"
                workflow["prerequisites"] = ["Access to data sources", "Stakeholder availability"]
            
            return {
                "success": True,
                "workflow": workflow,
            }
            
        except Exception as e:
            logger.error(f"Workflow suggestion failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "task": task,
            }
    
    async def get_recommendations(
        self,
        context: Dict[str, Any],
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Get personalized recommendations based on context.
        
        Args:
            context: Current context (metadata, rules, user preferences, etc.)
            **kwargs: Additional parameters
            
        Returns:
            Personalized recommendations for the user
        """
        try:
            recommendations = []
            
            # Analyze context and generate recommendations
            if "metadata" in context:
                metadata = context["metadata"]
                recommendations.extend(self._recommend_for_metadata(metadata))
            
            if "rules" in context:
                rules = context["rules"]
                recommendations.extend(self._recommend_for_rules(rules))
            
            if "connectors" in context:
                connectors = context["connectors"]
                recommendations.extend(self._recommend_for_connectors(connectors))
            
            # Deduplicate recommendations
            unique_recommendations = []
            seen = set()
            for rec in recommendations:
                key = rec.get("id") or rec.get("title", "")
                if key not in seen:
                    seen.add(key)
                    unique_recommendations.append(rec)
            
            return {
                "success": True,
                "recommendations": unique_recommendations,
                "count": len(unique_recommendations),
            }
            
        except Exception as e:
            logger.error(f"Recommendation generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "recommendations": [],
            }
    
    # ==================== Internal Methods ====================
    
    def _analyze_intent(self, query: str) -> Dict[str, Any]:
        """Analyze user query to determine intent."""
        query_lower = query.lower()
        
        intent = {
            "category": "general",
            "confidence": 0.5,
            "keywords": [],
        }
        
        # Categorize based on keywords
        connector_keywords = ["connector", "database", "postgresql", "sql server", "adls", "s3", 
                             "blob", "api", "connection", "onboard", "setup", "configure"]
        rule_keywords = ["rule", "data quality", "validation", "dq", "not null", "unique", 
                       "pattern", "range", "in set", "referential", "custom sql", "accuracy"]
        definition_keywords = ["define", "definition", "glossary", "term", "business meaning",
                              "data dictionary", "steward", "ownership", "bcbs 239"]
        general_keywords = ["how", "what", "why", "explain", "help", "troubleshoot", "issue", "problem"]
        
        # Check categories
        for keyword in connector_keywords:
            if keyword in query_lower:
                intent["category"] = "connector"
                intent["keywords"].append(keyword)
                intent["confidence"] = max(intent["confidence"], 0.8)
        
        for keyword in rule_keywords:
            if keyword in query_lower:
                if intent["category"] == "connector":
                    intent["category"] = "mixed"
                else:
                    intent["category"] = "rule"
                intent["keywords"].append(keyword)
                intent["confidence"] = max(intent["confidence"], 0.8)
        
        for keyword in definition_keywords:
            if keyword in query_lower:
                if intent["category"] == "general":
                    intent["category"] = "definition"
                else:
                    intent["category"] = "mixed"
                intent["keywords"].append(keyword)
                intent["confidence"] = max(intent["confidence"], 0.8)
        
        for keyword in general_keywords:
            if keyword in query_lower:
                intent["keywords"].append(keyword)
        
        return intent
    
    def _generate_response(self, query: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a response based on query and intent."""
        response: Dict[str, Any] = {
            "text": "",
            "suggestions": [],
            "next_steps": [],
            "referenced_agents": [],
        }
        
        category = intent.get("category", "general")
        
        if category == "connector":
            response = self._generate_connector_response(query, intent)
        elif category == "rule":
            response = self._generate_rule_response(query, intent)
        elif category == "definition":
            response = self._generate_definition_response(query, intent)
        else:
            # General response
            response["text"] = self._generate_general_response(query)
        
        return response
    
    def _generate_connector_response(self, query: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Generate response for connector-related queries."""
        query_lower = query.lower()
        
        response: Dict[str, Any] = {
            "text": "",
            "suggestions": [],
            "next_steps": [],
            "referenced_agents": ["connector"],
        }
        
        if any(word in query_lower for word in ["how to", "how do i", "steps", "process"]):
            response["text"] = """
            # Connector Onboarding Process
            
            To onboard a new connector in DQ-RuleBuilder:
            
            ## Steps:
            1. **Identify Connector Type** - Determine which type of connector you need:
               - PostgreSQL - For PostgreSQL databases
               - SQL Server - For Microsoft SQL Server databases
               - ADLS - For Azure Data Lake Storage
               - S3 - For AWS S3 or S3-compatible storage
               - Blob - For Azure Blob Storage
               - API - For REST API data sources
            
            2. **Gather Connection Details** - Collect the necessary information:
               - Hostname or endpoint URL
               - Port number (if not default)
               - Database name or container/bucket name
               - Credentials (username/password or access keys)
            
            3. **Use the Connector Onboarding Agent** - I can help you with this!
               The Connector Onboarding Agent will guide you through:
               - Configuration
               - Validation
               - Connection testing
               - Metadata discovery
               - Syncing to the DQ catalog
            
            ## Need Help?
            Would you like me to connect you with the Connector Onboarding Agent to complete this process?
            """
            response["suggestions"].append(
                "Use the Connector Onboarding Agent for step-by-step guidance"
            )
            response["next_steps"].append(
                {"action": "Start connector onboarding", "agent": "connector"}
            )
            
        elif any(word in query_lower for word in ["error", "problem", "issue", "not working", "failed"]):
            response["text"] = """
            # Connector Troubleshooting
            
            Common connector issues and solutions:
            
            ## Connection Failures:
            - **Connection refused** - Verify server is running and port is correct
            - **Authentication failed** - Check username/password and permissions
            - **Timeout** - Check network connectivity and firewall rules
            - **Network error** - Verify DNS resolution and network access
            
            ## Configuration Issues:
            - **Invalid configuration** - Review connection string format and required parameters
            - **Missing parameters** - Ensure all required fields are provided
            - **Unsupported type** - Verify the connector type is supported
            
            ## Discovery Issues:
            - **No metadata found** - Check permissions for metadata access
            - **Partial discovery** - May need to adjust discovery settings
            
            ## Need Help?
            The Connector Onboarding Agent can help diagnose and fix connection issues.
            """
            response["suggestions"].append(
                "Use the Connector Onboarding Agent to diagnose connection issues"
            )
            
        else:
            response["text"] = """
            I can help you with connector-related tasks! The Connector Onboarding Agent 
            is specifically designed to assist with:
            
            - Configuring new connectors
            - Validating connector configurations
            - Testing connections to data sources
            - Discovering metadata (schemas, tables, columns)
            - Syncing metadata to the DQ catalog
            
            Would you like me to connect you with the Connector Onboarding Agent?
            """
        
        return response
    
    def _generate_rule_response(self, query: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Generate response for rule-related queries."""
        query_lower = query.lower()
        
        response: Dict[str, Any] = {
            "text": "",
            "suggestions": [],
            "next_steps": [],
            "referenced_agents": ["rule"],
        }
        
        if any(word in query_lower for word in ["how to", "how do i", "steps", "process"]):
            response["text"] = """
            # Creating Data Quality Rules
            
            To create data quality rules in DQ-RuleBuilder:
            
            ## Steps:
            1. **Identify Data to Validate** - Determine which tables and columns need validation
            2. **Define Business Rules** - Document the business requirements
            3. **Extract Rules** - Use the Rule Engineer Agent to extract rules from natural language
            4. **Validate Rules** - Ensure rules are properly configured
            5. **Assign to Metadata** - Associate rules with specific metadata elements
            6. **Execute and Monitor** - Run rules and analyze results
            
            ## Rule Types Available:
            - NOT_NULL - Check for null values (completeness)
            - UNIQUE - Ensure unique values (uniqueness)
            - PATTERN - Validate format with regex (validity)
            - RANGE - Check numeric ranges (validity)
            - IN_SET - Validate against allowed values (validity)
            - REFERENTIAL_INTEGRITY - Validate foreign keys (consistency)
            - CUSTOM_SQL - Custom SQL validation (custom)
            - ACCURACY - Check data accuracy (accuracy)
            - CONSISTENCY - Cross-field validation (consistency)
            
            ## Need Help?
            The Rule Engineer Agent can help you extract and create rules from natural language!
            """
            response["suggestions"].append(
                "Use the Rule Engineer Agent to extract rules from natural language"
            )
            
        elif any(word in query_lower for word in ["example", "sample", "show me"]):
            response["text"] = """
            # Rule Examples
            
            Here are some examples of data quality rules:
            
            ## Completeness Rules (NOT_NULL):
            - Customer email must not be null
            - Order date must not be null
            - Product name must not be null
            
            ## Uniqueness Rules (UNIQUE):
            - Customer ID must be unique
            - Order number must be unique
            - Email address must be unique
            
            ## Validity Rules (PATTERN):
            - Email must match email format: ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$
            - Phone must match phone format: ^\\+?[\\d\\s\\-\\(\\)]{10,15}$
            - Date must match ISO 8601 format: ^\\d{4}-\\d{2}-\\d{2}$
            
            ## Validity Rules (IN_SET):
            - Status must be one of: active, inactive, pending
            - Priority must be one of: high, medium, low
            - Region must be one of: north, south, east, west
            
            ## Validity Rules (RANGE):
            - Age must be between 0 and 120
            - Price must be between 0 and 10000
            - Quantity must be between 1 and 1000
            
            The Rule Engineer Agent can help you create these rules from natural language!
            """
        
        else:
            response["text"] = """
            I can help you with data quality rules! The Rule Engineer Agent is 
            specifically designed to assist with:
            
            - Extracting rules from natural language requirements
            - Validating rule configurations against schema
            - Assigning rules to metadata attributes
            - Executing rules and analyzing results
            - Suggesting rule improvements
            
            Would you like me to connect you with the Rule Engineer Agent?
            """
        
        return response
    
    def _generate_definition_response(self, query: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Generate response for definition-related queries."""
        response: Dict[str, Any] = {
            "text": "",
            "suggestions": [],
            "next_steps": [],
            "referenced_agents": ["steward"],
        }
        
        response["text"] = """
        I can help you with data definitions and governance! The Data Steward Agent 
        is specifically designed to assist with:
        
        - Generating data definitions from context
        - Creating and updating glossary entries
        - Suggesting data stewards and ownership
        - Validating definitions against policies (including BCBS 239)
        - Tracking approval workflows
        - Ensuring traceability and auditability
        
        ## Definition Quality Criteria:
        - Business definition must start with 'A' or 'An'
        - Express the essence of the term
        - Avoid circular wording
        - Avoid embedded business rules
        - Avoid purpose/function language ('used for')
        - Value-domain expectations should be explicit
        - Identify accountable stewardship and source provenance
        - Traceable and governable for audit needs
        
        Would you like me to connect you with the Data Steward Agent?
        """
        
        response["suggestions"].append(
            "Use the Data Steward Agent for definition and governance tasks"
        )
        
        return response
    
    def _generate_general_response(self, query: str) -> str:
        """Generate a general response for unclassified queries."""
        return f"""
        Welcome to DQ-RuleBuilder! I'm here to help you with all your data quality needs.
        
        ## What is DQ-RuleBuilder?
        DQ-RuleBuilder is an enterprise data quality management platform that helps 
        organizations ensure their data is complete, accurate, consistent, and reliable.
        
        ## Available Specialized Agents:
        
        ### 🔌 Connector Onboarding Agent
        - **Purpose**: Automate connector configuration and onboarding
        - **Use for**: Setting up new data sources, troubleshooting connections
        - **Supported**: PostgreSQL, SQL Server, ADLS, S3, Blob, API
        
        ### 📊 Rule Engineer Agent
        - **Purpose**: Create and manage data quality rules
        - **Use for**: Extracting rules from requirements, validating configurations
        - **Supported**: NOT_NULL, UNIQUE, PATTERN, RANGE, IN_SET, REFERENTIAL_INTEGRITY, CUSTOM_SQL, ACCURACY, CONSISTENCY
        
        ### 👤 Data Steward Agent
        - **Purpose**: Manage data definitions and governance
        - **Use for**: Creating definitions, managing glossaries, ensuring compliance
        - **Supported**: BCBS 239 alignment, definition quality validation, approval workflows
        
        ## How Can I Help?
        
        You can ask me about:
        - Platform features and capabilities
        - Data quality concepts and best practices
        - Troubleshooting issues
        - Recommended workflows for your tasks
        - Which specialized agent to use for your specific needs
        
        ## Your Question:
        You asked: "{query}"
        
        Please let me know how I can assist you further!
        """
    
    def _generate_general_explanation(self, concept: str) -> str:
        """Generate a general explanation for a concept."""
        return f"""
        ## {concept}
        
        I don't have specific information about "{concept}" in my knowledge base, 
        but I can provide general guidance on data quality topics.
        
        Data Quality is the measure of how well data meets the needs of its intended use. 
        The six dimensions of data quality are:
        
        1. **Completeness** - All required data is present
        2. **Uniqueness** - No duplicate values where not allowed
        3. **Validity** - Data conforms to expected formats and values
        4. **Consistency** - Data is consistent across related fields and tables
        5. **Accuracy** - Data correctly represents real-world values
        6. **Timeliness** - Data is available when needed
        
        If "{concept}" is related to a specific aspect of data quality or DQ-RuleBuilder,
        please let me know and I can provide more targeted information.
        """
    
    def _recommend_for_metadata(self, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate recommendations based on metadata."""
        recommendations = []
        
        tables = metadata.get("tables", [])
        if len(tables) == 0:
            recommendations.append({
                "id": "no_metadata",
                "title": "No metadata available",
                "description": "Consider onboardeding connectors to discover metadata",
                "priority": "high",
                "agent": "connector",
            })
        else:
            # Check for tables without rules
            recommendations.append({
                "id": "add_rules",
                "title": "Add data quality rules",
                "description": f"Define rules for {len(tables)} tables to ensure data quality",
                "priority": "high",
                "agent": "rule",
            })
            
            # Check for tables without definitions
            recommendations.append({
                "id": "add_definitions",
                "title": "Add business definitions",
                "description": "Define business terms for key data elements",
                "priority": "medium",
                "agent": "steward",
            })
        
        return recommendations
    
    def _recommend_for_rules(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate recommendations based on existing rules."""
        recommendations = []
        
        if len(rules) == 0:
            recommendations.append({
                "id": "no_rules",
                "title": "No rules defined",
                "description": "Consider adding at least NOT_NULL rules for primary keys",
                "priority": "high",
                "agent": "rule",
            })
        else:
            # Check rule coverage
            rule_types = {r.get("rule_type") for r in rules if isinstance(r, dict)}
            
            if "NOT_NULL" not in rule_types:
                recommendations.append({
                    "id": "add_not_null",
                    "title": "Add NOT_NULL rules",
                    "description": "Ensure critical fields are not null",
                    "priority": "high",
                    "agent": "rule",
                })
            
            if "UNIQUE" not in rule_types:
                recommendations.append({
                    "id": "add_unique",
                    "title": "Add UNIQUE rules",
                    "description": "Ensure primary keys and unique fields have unique values",
                    "priority": "high",
                    "agent": "rule",
                })
        
        return recommendations
    
    def _recommend_for_connectors(self, connectors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate recommendations based on connectors."""
        recommendations = []
        
        if len(connectors) == 0:
            recommendations.append({
                "id": "no_connectors",
                "title": "No connectors configured",
                "description": "Start by onboarding connectors to your data sources",
                "priority": "high",
                "agent": "connector",
            })
        else:
            # Check for connectors that haven't been synced
            unsynced = [c for c in connectors if not c.get("last_sync") or c.get("needs_sync")]
            if unsynced:
                recommendations.append({
                    "id": "sync_connectors",
                    "title": "Sync connector metadata",
                    "description": f"{len(unsynced)} connectors need metadata synchronization",
                    "priority": "high",
                    "agent": "connector",
                })
        
        return recommendations
    
    def get_state(self) -> Dict[str, Any]:
        """Get the current agent state including conversation context."""
        base_state = super().get_state()
        return {
            **base_state,
            "agent_type": "general",
            "conversation_context": self.conversation_context,
            "referenced_agents": self.referenced_agents,
        }
    
    def reset_state(self) -> None:
        """Reset the conversation state."""
        self.conversation_context.clear()
        self.referenced_agents.clear()
        logger.info(f"GeneralDQAgent {self.session_id}: State reset")
