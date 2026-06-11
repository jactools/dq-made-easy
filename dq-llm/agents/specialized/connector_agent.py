"""
Connector Onboarding Agent for DQ-RuleBuilder Pi Agent Harness.

This specialized agent automates Phase 2 MVP Connectors workflow (API-1.3 to API-1.6).

Purpose:
    Automate end-to-end connector onboarding, including configuration, validation,
    connection testing, metadata discovery, and sync job orchestration.

Capabilities:
    - Guide users through connector configuration
    - Validate configurations before testing
    - Execute test connections
    - Discover and catalog metadata (schemas, tables, columns, relationships)
    - Trigger and monitor sync jobs
    - Handle connection failures with actionable diagnostics
    - Provide secure credential handling

Related Work:
    - API-1.1: Connector interface + registry
    - API-1.2: Secure connector config schema + secrets handling
    - API-1.3 to API-1.6: Connector implementations (PostgreSQL, SQL Server, ADLS, S3)
    - API-1.8: Connection test + discovery endpoints
    - API-1.9: Metadata sync job orchestration + status model

Tracked Work Item: LLM-1.7
Milestone: B (Connector Focus)
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

from ..base import DQAgent, DQAgentError, AgentStatus
from ..config import DQAgentConfig, get_agent_config
from ..tools.connector_tools import (
    ConnectorTool,
    ConnectorConfig,
    ConnectorTestResult,
    DiscoveryResult,
    SyncJobStatus,
)

logger = logging.getLogger(__name__)


class ConnectorOnboardingAgent(DQAgent):
    """
    Specialized agent for data source connector onboarding.
    
    This agent guides users through the complete connector lifecycle:
    1. Collect connection details
    2. Validate configuration
    3. Test connection
    4. Discover metadata
    5. Sync to catalog
    6. Handle errors with actionable diagnostics
    
    The agent is designed to work with PostgreSQL, SQL Server, Azure ADLS, 
    S3/Blob, and other connector types defined in API-1.
    
    Attributes:
        connector_tool: The ConnectorTool instance for API-1 operations
        current_connector_id: Tracks the connector being onboarded
        onboarding_state: Tracks progress through the onboarding workflow
    """
    
    # Supported connector types (API-1.3 to API-1.6)
    SUPPORTED_CONNECTOR_TYPES = [
        "postgresql",
        "sqlserver", 
        "adls",  # Azure Data Lake Storage
        "s3",     # AWS S3 / S3-compatible
        "blob",   # Azure Blob Storage
        "api",    # REST API
    ]
    
    # System prompt from feature specification (Phase 3.1)
    SYSTEM_PROMPT = """
    You are a Data Connector Specialist for DQ-RuleBuilder.
    Your expertise: PostgreSQL, SQL Server, Azure ADLS, S3/Blob connectors.
    
    Primary Tasks:
    1. Guide users through connector configuration
    2. Validate configurations before testing
    3. Execute test connections
    4. Discover metadata (schemas, tables, columns, relationships)
    5. Sync metadata to the DQ catalog
    6. Handle connection failures with actionable diagnostics
    
    Workflow:
    - Ask user for connector type and connection details
    - Validate the configuration before attempting connection
    - Test the connection and report results
    - If successful, discover metadata (schemas, tables, columns)
    - Sync metadata to the DQ catalog
    - Report success or provide actionable error diagnostics
    
    Secrets Handling:
    - NEVER expose credentials in responses
    - NEVER log credentials or sensitive connection strings
    - Use secure credential references where possible
    - Redact sensitive information from all outputs
    - If credentials are provided in plain text, immediately prompt for secure storage
    
    Error Handling:
    - Connection failures: Return specific error type and remediation steps
    - Schema errors: Validate against expected patterns
    - Authentication failures: Guide user to verify credentials and permissions
    - Network errors: Check connectivity and firewall rules
    - Configuration errors: Provide clear validation messages
    
    Supported Connector Types:
    - postgresql: PostgreSQL database connections
    - sqlserver: Microsoft SQL Server connections
    - adls: Azure Data Lake Storage Gen2
    - s3: AWS S3 or S3-compatible storage
    - blob: Azure Blob Storage
    - api: REST API data sources
    
    Response Guidelines:
    - Always confirm before taking destructive actions
    - Provide progress updates at each workflow step
    - Include estimated time for long-running operations
    - Format technical details in code blocks for readability
    - Use bullet points for action items and requirements
    """
    
    def __init__(
        self,
        name: str = "dq_connector_agent",
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        config: Optional[DQAgentConfig] = None,
        session_id: Optional[str] = None,
        **kwargs: Any
    ):
        """
        Initialize the Connector Onboarding Agent.
        
        Args:
            name: Agent name
            api_base_url: Base URL for DQ-API (overrides config)
            api_key: API key for authentication (overrides config)
            config: DQAgentConfig instance
            session_id: Session identifier
            **kwargs: Additional arguments passed to DQAgent
        """
        # Get configuration
        self.agent_config = config or get_agent_config()
        
        # Use provided API config or fall back to global config
        effective_api_base_url = api_base_url or self.agent_config.api_base_url
        effective_api_key_provider = self.agent_config.get_api_key_provider(api_key)
        
        # Initialize connector tool
        self.connector_tool = ConnectorTool(
            api_base_url=effective_api_base_url,
            api_key_provider=effective_api_key_provider
        )
        
        # Track onboarding state
        self.current_connector_id: Optional[str] = None
        self.current_connector_type: Optional[str] = None
        self.onboarding_state: Dict[str, Any] = {}
        self.discovered_metadata: Optional[DiscoveryResult] = None
        self.sync_job_id: Optional[str] = None
        
        # Initialize parent with connector tool
        super().__init__(
            name=name,
            session_id=session_id,
            config=self.agent_config,
            tools=[self.connector_tool],
            system_prompt=self.SYSTEM_PROMPT,
            **kwargs
        )
        
        logger.info(f"ConnectorOnboardingAgent '{name}' initialized with session {self.session_id}")
    
    async def onboard_connector(
        self,
        connector_type: str,
        user_input: str,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Complete end-to-end connector onboarding workflow.
        
        This method orchestrates the full onboarding process:
        1. Parse user input for connection details
        2. Create and validate configuration
        3. Configure the connector
        4. Test the connection
        5. Discover metadata
        6. Sync to catalog
        
        Args:
            connector_type: Type of connector (postgresql, sqlserver, adls, s3, blob, api)
            user_input: Natural language input with connection details
            **kwargs: Additional context or overrides
            
        Returns:
            Dictionary with onboarding results including:
            - success: bool
            - connector_id: str or None
            - messages: List of status messages
            - metadata: Discovered metadata summary
            - errors: List of error messages
            
        Raises:
            DQAgentError: If onboarding fails at any step
        """
        self.onboarding_state = {
            "connector_type": connector_type,
            "step": "starting",
            "messages": [],
            "errors": [],
            "warnings": [],
        }
        
        self.current_connector_type = connector_type
        self.current_connector_id = None
        self.discovered_metadata = None
        self.sync_job_id = None
        
        # Validate connector type
        if connector_type.lower() not in self.SUPPORTED_CONNECTOR_TYPES:
            supported = ", ".join(self.SUPPORTED_CONNECTOR_TYPES)
            error_msg = f"Unsupported connector type: {connector_type}. Supported types: {supported}"
            logger.error(error_msg)
            self.onboarding_state["errors"].append(error_msg)
            return {
                **self.onboarding_state,
                "success": False,
                "connector_id": None,
            }
        
        try:
            # Step 1: Parse input and create configuration
            self.onboarding_state["step"] = "parsing_input"
            config = self._parse_connector_input(connector_type, user_input, **kwargs)
            if not config:
                return {
                    **self.onboarding_state,
                    "success": False,
                    "connector_id": None,
                }
            
            # Step 2: Validate configuration
            self.onboarding_state["step"] = "validating"
            validation = await self._validate_configuration(config)
            if not validation.get("valid", False):
                self.onboarding_state["errors"].extend(validation.get("errors", []))
                return {
                    **self.onboarding_state,
                    "success": False,
                    "connector_id": None,
                }
            
            # Step 3: Configure connector
            self.onboarding_state["step"] = "configuring"
            configure_result = await self._configure_connector(config)
            if not configure_result.get("success", False):
                self.onboarding_state["errors"].append(configure_result.get("error", "Configuration failed"))
                return {
                    **self.onboarding_state,
                    "success": False,
                    "connector_id": None,
                }
            
            self.current_connector_id = configure_result.get("connector_id")
            self.onboarding_state["connector_id"] = self.current_connector_id
            
            # Step 4: Test connection
            self.onboarding_state["step"] = "testing_connection"
            test_result = await self._test_connection(self.current_connector_id)
            if not test_result.success:
                error_details = self._format_connection_error(test_result)
                self.onboarding_state["errors"].append(error_details)
                return {
                    **self.onboarding_state,
                    "success": False,
                    "connector_id": self.current_connector_id,
                }
            
            # Step 5: Discover metadata
            self.onboarding_state["step"] = "discovering"
            discovery_result = await self._discover_metadata(self.current_connector_id)
            self.discovered_metadata = discovery_result
            
            # Step 6: Sync metadata
            self.onboarding_state["step"] = "syncing"
            sync_result = await self._sync_metadata(self.current_connector_id)
            self.sync_job_id = sync_result.get("job_id")
            
            # Build success response
            self.onboarding_state["step"] = "completed"
            self.onboarding_state["success"] = True
            self.onboarding_state["messages"].append(
                f"Connector '{self.current_connector_id}' successfully onboarded"
            )
            
            return {
                **self.onboarding_state,
                "connector_id": self.current_connector_id,
                "sync_job_id": self.sync_job_id,
                "metadata_summary": self._summarize_discovery(discovery_result),
            }
            
        except Exception as e:
            error_msg = f"Onboarding failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.onboarding_state["errors"].append(error_msg)
            self.onboarding_state["step"] = "failed"
            return {
                **self.onboarding_state,
                "success": False,
                "connector_id": self.current_connector_id,
            }
    
    async def configure_connector(self, config: ConnectorConfig) -> Dict[str, Any]:
        """
        Configure a new connector (API-1.1).
        
        Args:
            config: Connector configuration
            
        Returns:
            Configuration result with connector_id
        """
        self.onboarding_state["step"] = "configuring"
        
        # Redact sensitive data from logs
        safe_config_dict = config.model_dump()
        if 'credentials' in safe_config_dict:
            safe_config_dict['credentials'] = '***REDACTED***'
        if 'connection_string' in safe_config_dict:
            safe_config_dict['connection_string'] = '***REDACTED***'
        
        logger.info(f"Configuring {config.connector_type} connector: {config.name}")
        
        try:
            result = await self.connector_tool.configure(config)
            connector_id = result.get("id") or result.get("connector_id")
            
            if connector_id:
                self.current_connector_id = connector_id
                self.current_connector_type = config.connector_type
                self.onboarding_state["connector_id"] = connector_id
                self.onboarding_state["messages"].append(
                    f"Connector configured with ID: {connector_id}"
                )
                return {"success": True, "connector_id": connector_id, **result}
            else:
                error_msg = f"Configuration succeeded but no connector_id returned: {result}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg, **result}
                
        except Exception as e:
            error_msg = f"Configuration failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}
    
    async def test_connector(self, connector_id: str) -> Dict[str, Any]:
        """
        Test connection to a configured connector (API-1.8).
        
        Args:
            connector_id: ID of the connector to test
            
        Returns:
            Test result with success status and diagnostics
        """
        self.current_connector_id = connector_id
        result = await self._test_connection(connector_id)
        return result.model_dump() if isinstance(result, ConnectorTestResult) else result
    
    async def discover_connector(self, connector_id: str) -> Dict[str, Any]:
        """
        Discover metadata from a connector (API-1.8).
        
        Args:
            connector_id: ID of the connector
            
        Returns:
            Discovery result with schemas, tables, columns, etc.
        """
        self.current_connector_id = connector_id
        result = await self._discover_metadata(connector_id)
        self.discovered_metadata = result
        return result.model_dump() if isinstance(result, DiscoveryResult) else result
    
    async def sync_connector(self, connector_id: str) -> Dict[str, Any]:
        """
        Trigger metadata sync for a connector (API-1.9).
        
        Args:
            connector_id: ID of the connector to sync
            
        Returns:
            Sync job information
        """
        self.current_connector_id = connector_id
        result = await self._sync_metadata(connector_id)
        self.sync_job_id = result.get("job_id")
        return result
    
    async def get_sync_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get the status of a sync job (API-1.9).
        
        Args:
            job_id: ID of the sync job
            
        Returns:
            Sync job status
        """
        result = await self.connector_tool.get_sync_status(job_id)
        return result.model_dump() if isinstance(result, SyncJobStatus) else result
    
    async def check_health(self, connector_id: str) -> Dict[str, Any]:
        """
        Check the health status of a connector.
        
        Args:
            connector_id: ID of the connector
            
        Returns:
            Health status of the connector
        """
        result = await self.connector_tool.health(connector_id)
        return result.model_dump() if hasattr(result, 'model_dump') else result
    
    # ==================== Internal Methods ====================
    
    def _parse_connector_input(
        self,
        connector_type: str,
        user_input: str,
        **kwargs: Any
    ) -> Optional[ConnectorConfig]:
        """
        Parse user input to extract connector configuration.
        
        This method attempts to extract configuration details from natural language.
        It looks for patterns like:
        - Connection strings
        - Hostnames and ports
        - Database names
        - Credential references
        
        Args:
            connector_type: Type of connector
            user_input: Natural language input
            **kwargs: Override values
            
        Returns:
            ConnectorConfig instance or None if parsing fails
        """
        # Try to use LLM to parse input if available
        # For now, implement basic pattern matching
        
        import re
        
        config_data: Dict[str, Any] = {
            "connector_type": connector_type,
            "config": {},
        }
        
        # Extract name
        name_patterns = [
            rf"name[:\s]+(['\"]?)([^'\"]+)\1",
            rf"connector[\s]+name[:\s]+(['\"]?)([^'\"]+)\1",
            rf"call[\s]+it[\s]+(['\"]?)([^'\"]+)\1",
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                config_data["name"] = match.group(2).strip()
                break
        
        if "name" not in config_data:
            # Default name based on type
            config_data["name"] = f"{connector_type}-connector"
        
        # Extract description
        desc_patterns = [
            rf"description[:\s]+(['\"]?)([^'\"]+)\1",
            rf"for[\s]+(['\"]?)([^'\"]+)\1",
            rf"purpose[:\s]+(['\"]?)([^'\"]+)\1",
        ]
        
        for pattern in desc_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                config_data["description"] = match.group(2).strip()
                break
        
        # Extract connection details based on type
        if connector_type in ["postgresql", "sqlserver"]:
            # Database connectors
            config_data["config"] = self._parse_database_input(user_input, connector_type)
        elif connector_type in ["adls", "s3", "blob"]:
            # Storage connectors
            config_data["config"] = self._parse_storage_input(user_input, connector_type)
        elif connector_type == "api":
            # API connectors
            config_data["config"] = self._parse_api_input(user_input)
        
        # Apply overrides from kwargs
        config_data.update(kwargs)
        
        # Ensure required fields
        if "config" not in config_data:
            config_data["config"] = {}
        
        try:
            return ConnectorConfig(**config_data)
        except Exception as e:
            logger.error(f"Failed to create ConnectorConfig: {e}")
            self.onboarding_state["errors"].append(f"Invalid configuration: {str(e)}")
            return None
    
    def _parse_database_input(self, user_input: str, connector_type: str) -> Dict[str, Any]:
        """Parse database connection details from input."""
        config: Dict[str, Any] = {}
        
        # Extract host
        host_patterns = [
            rf"host[:\s]+(['\"]?)([^'\"\s,:]+)\1",
            rf"server[:\s]+(['\"]?)([^'\"\s,:]+)\1",
            rf"([a-zA-Z0-9][a-zA-Z0-9\-]*\.[a-zA-Z0-9][a-zA-Z0-9\-]*\.[a-zA-Z]{2,})",
            rf"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
        ]
        
        for pattern in host_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                config["host"] = match.group(2) if match.lastindex > 1 else match.group(1)
                break
        
        # Extract port
        port_patterns = [
            rf"port[:\s]+(['\"]?)(\d{1,5})\1",
            rf":(\d{1,5})\s",
        ]
        
        for pattern in port_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                port = match.group(2) if match.lastindex > 1 else match.group(1)
                if port.isdigit():
                    config["port"] = int(port)
                    # Set default port if not specified
                    if connector_type == "postgresql" and config["port"] == 5432:
                        pass  # Default PostgreSQL port
                    elif connector_type == "sqlserver" and config["port"] in [1433, 1434]:
                        pass  # Default SQL Server ports
                    break
        
        # Set default ports
        if "port" not in config:
            if connector_type == "postgresql":
                config["port"] = 5432
            elif connector_type == "sqlserver":
                config["port"] = 1433
        
        # Extract database name
        db_patterns = [
            rf"database[:\s]+(['\"]?)([^'\"\s;,]+)\1",
            rf"db[:\s]+(['\"]?)([^'\"\s;,]+)\1",
            rf"/([^\s;,/?]+)",
        ]
        
        for pattern in db_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                config["database"] = match.group(2) if match.lastindex > 1 else match.group(1)
                break
        
        # Extract username (but don't store actual value - prompt for secure input)
        user_patterns = [
            rf"user[:\s]+(['\"]?)([^'\"\s;,]+)\1",
            rf"username[:\s]+(['\"]?)([^'\"\s;,]+)\1",
        ]
        
        for pattern in user_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                # Don't store actual username - just note that it's needed
                config["_needs_credentials"] = True
                break
        
        # Build connection string (without credentials)
        if "host" in config and "database" in config:
            if connector_type == "postgresql":
                config["connection_string"] = f"postgresql://{config['host']}:{config.get('port', 5432)}/{config['database']}"
            elif connector_type == "sqlserver":
                config["connection_string"] = f"sqlserver://{config['host']}:{config.get('port', 1433)}/{config['database']}"
        
        return config
    
    def _parse_storage_input(self, user_input: str, connector_type: str) -> Dict[str, Any]:
        """Parse storage connection details from input."""
        config: Dict[str, Any] = {}
        
        # Extract endpoint/host
        host_patterns = [
            rf"endpoint[:\s]+(['\"]?)([^'\"\s]+)\1",
            rf"host[:\s]+(['\"]?)([^'\"\s]+)\1",
            rf"([a-zA-Z0-9][a-zA-Z0-9\-]*\.[a-zA-Z0-9][a-zA-Z0-9\-]*\.[a-zA-Z]{2,})",
        ]
        
        for pattern in host_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                config["endpoint"] = match.group(2) if match.lastindex > 1 else match.group(1)
                break
        
        # Extract container/bucket
        container_patterns = [
            rf"container[:\s]+(['\"]?)([^'\"\s]+)\1",
            rf"bucket[:\s]+(['\"]?)([^'\"\s]+)\1",
        ]
        
        for pattern in container_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                if connector_type in ["adls", "blob"]:
                    config["container"] = match.group(2) if match.lastindex > 1 else match.group(1)
                else:  # s3
                    config["bucket"] = match.group(2) if match.lastindex > 1 else match.group(1)
                break
        
        return config
    
    def _parse_api_input(self, user_input: str) -> Dict[str, Any]:
        """Parse API connection details from input."""
        config: Dict[str, Any] = {}
        
        # Extract base URL
        url_patterns = [
            rf"url[:\s]+(['\"]?)([^'\"\s]+)\1",
            rf"endpoint[:\s]+(['\"]?)([^'\"\s]+)\1",
            rf"(https?://[^\s]+)",
        ]
        
        for pattern in url_patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                config["base_url"] = match.group(2) if match.lastindex > 1 else match.group(1)
                break
        
        return config
    
    async def _validate_configuration(self, config: ConnectorConfig) -> Dict[str, Any]:
        """Validate connector configuration (API-1.1)."""
        try:
            result = await self.connector_tool.validate(config)
            
            if result.get("valid", True):
                return {"valid": True, "warnings": result.get("warnings", [])}
            else:
                errors = result.get("errors", [])
                if isinstance(errors, str):
                    errors = [errors]
                return {"valid": False, "errors": errors}
                
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return {"valid": False, "errors": [str(e)]}
    
    async def _configure_connector(self, config: ConnectorConfig) -> Dict[str, Any]:
        """Configure a new connector."""
        try:
            result = await self.connector_tool.configure(config)
            return {"success": True, **result}
        except Exception as e:
            logger.error(f"Configuration failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _test_connection(self, connector_id: str) -> ConnectorTestResult:
        """Test connection to a configured connector."""
        try:
            result = await self.connector_tool.test_connection(connector_id)
            return result
        except Exception as e:
            logger.error(f"Connection test failed for {connector_id}: {e}")
            return ConnectorTestResult(
                success=False,
                connector_id=connector_id,
                error_type="connection_error",
                error_message=str(e),
                latency_ms=0.0
            )
    
    async def _discover_metadata(self, connector_id: str) -> DiscoveryResult:
        """Discover metadata from a connector."""
        try:
            result = await self.connector_tool.discover(connector_id)
            return result
        except Exception as e:
            logger.error(f"Discovery failed for {connector_id}: {e}")
            # Return partial result with error
            return DiscoveryResult(
                connector_id=connector_id,
                schemas=[],
                tables=[],
                columns=[],
                relationships=[],
                summary={"error": str(e)}
            )
    
    async def _sync_metadata(self, connector_id: str) -> Dict[str, Any]:
        """Trigger metadata sync for a connector."""
        try:
            result = await self.connector_tool.sync(connector_id)
            return result
        except Exception as e:
            logger.error(f"Sync failed for {connector_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def _format_connection_error(self, test_result: ConnectorTestResult) -> str:
        """Format connection error for user-friendly output."""
        error_type = test_result.error_type or "unknown"
        error_msg = test_result.error_message or "No error message provided"
        
        # Map error types to remediation steps
        remediation = {
            "connection_refused": (
                "Connection was refused. Please check:"
                "\n- Is the server running?"
                "\n- Is the port correct?"
                "\n- Are there any firewall rules blocking access?"
            ),
            "authentication_failed": (
                "Authentication failed. Please verify:"
                "\n- Username and password are correct"
                "\n- User has sufficient permissions"
                "\n- Password hasn't expired"
            ),
            "timeout": (
                "Connection timed out. Please check:"
                "\n- Network connectivity"
                "\n- Server is not overloaded"
                "\n- Timeout settings are appropriate"
            ),
            "network_error": (
                "Network error occurred. Please check:"
                "\n- Network connectivity to the target"
                "\n- DNS resolution"
                "\n- Proxy settings if applicable"
            ),
            "invalid_configuration": (
                "Configuration is invalid. Please review:"
                "\n- Connection string format"
                "\n- Required parameters are provided"
                "\n- Parameter values are valid"
            ),
        }
        
        remediation_steps = remediation.get(error_type.lower(), 
            "Please check the connection details and try again.")
        
        return f"Connection test failed ({error_type}): {error_msg}\n\n{remediation_steps}"
    
    def _summarize_discovery(self, discovery_result: DiscoveryResult) -> Dict[str, Any]:
        """Summarize discovery results for user-friendly output."""
        return {
            "schema_count": len(discovery_result.schemas),
            "table_count": len(discovery_result.tables),
            "column_count": len(discovery_result.columns),
            "relationship_count": len(discovery_result.relationships),
            "schemas": [s.get("name") for s in discovery_result.schemas if isinstance(s, dict)],
            "summary": discovery_result.summary,
        }
    
    def get_state(self) -> Dict[str, Any]:
        """Get the current agent state including onboarding progress."""
        base_state = super().get_state()
        return {
            **base_state,
            "agent_type": "connector",
            "current_connector_id": self.current_connector_id,
            "current_connector_type": self.current_connector_type,
            "onboarding_state": self.onboarding_state,
            "discovered_metadata_summary": (
                self._summarize_discovery(self.discovered_metadata)
                if self.discovered_metadata else None
            ),
            "sync_job_id": self.sync_job_id,
        }
    
    def reset_onboarding(self) -> None:
        """Reset the onboarding state for a new connector."""
        self.current_connector_id = None
        self.current_connector_type = None
        self.onboarding_state = {}
        self.discovered_metadata = None
        self.sync_job_id = None
        logger.info(f"ConnectorOnboardingAgent {self.session_id}: Onboarding state reset")

