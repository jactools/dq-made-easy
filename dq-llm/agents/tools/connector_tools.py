"""
Connector Tools for DQ Agent Harness.

This module provides Pi-compatible tools for data source connector operations.
These tools integrate with the DQ-RuleBuilder connector framework (API-1).

Implemented Tools:
- ConnectorTool: Main tool for connector operations
  - configure: Configure a new connector instance
  - validate: Validate connector configuration
  - test_connection: Test connection to data source
  - discover: Discover schemas, tables, columns
  - sync: Trigger metadata sync job
  - health: Check connector health status
  - get_status: Get sync job status

Related Work:
- API-1.1: Connector interface + registry
- API-1.2: Secure connector config schema + secrets handling
- API-1.3 to API-1.6: Connector implementations (PostgreSQL, SQL Server, ADLS, S3)
- API-1.8: Connection test + discovery endpoints
- API-1.9: Metadata sync job orchestration + status model

Usage:
    from agents.tools.connector_tools import ConnectorTool, ConnectorConfig
    
    # Create the tool with API client
    connector_tool = ConnectorTool(
        api_base_url="https://kong:8443",
        api_key="your-api-key"
    )
    
    # Add to an agent
    agent = DQAgent(tools=[connector_tool])
    
    # The LLM can now call: dq_connector.configure(...), etc.
"""

from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field
import httpx
import logging

from ..sandbox import validate_tool_invocation

# Placeholder for Pi Agent Tool base class
# This will be replaced with actual import when pi-agent is installed
try:
    from pi_agent import Tool as PiTool
    PI_AGENT_AVAILABLE = True
except ImportError:
    PI_AGENT_AVAILABLE = False
    PiTool = object  # type: ignore

logger = logging.getLogger(__name__)


# Type definitions for connector operations
ConnectorType = str  # "postgresql", "sqlserver", "adls", "s3", "api", etc.
ConnectorId = str
SyncJobId = str


class ConnectorConfig(BaseModel):
    """
    Configuration for a new connector.
    
    This model aligns with the DQ-API connector configuration schema
    (API-1.1 and API-1.2).
    """
    connector_type: ConnectorType = Field(
        ...,
        description="Type of connector: postgresql, sqlserver, adls, s3, api"
    )
    name: str = Field(
        ...,
        description="Human-readable name for the connector",
        min_length=1,
        max_length=255
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional description of the connector's purpose",
        max_length=1000
    )
    connection_string: Optional[str] = Field(
        default=None,
        description="Connection string for the data source"
    )
    credentials: Optional[Dict[str, str]] = Field(
        default=None,
        description="Connection credentials (username, password, etc.)"
    )
    config: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional connector-specific configuration"
    )
    workspace_id: Optional[str] = Field(
        default=None,
        description="Workspace/tenant identifier"
    )
    tags: Optional[List[str]] = Field(
        default_factory=list,
        description="Tags for categorization"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "connector_type": "postgresql",
                "name": "analytics-db",
                "description": "Production analytics database",
                "connection_string": "postgresql://db.example.com:5432/analytics",
                "credentials": {
                    "username": "readonly_user",
                    "password": "***SECRET***"
                },
                "config": {
                    "ssl_mode": "require",
                    "timeout": 30
                },
                "workspace_id": "prod",
                "tags": ["production", "analytics"]
            }
        }


class ConnectorTestResult(BaseModel):
    """Result of a connection test."""
    success: bool = Field(
        ...,
        description="Whether the connection test succeeded"
    )
    connector_id: Optional[str] = Field(
        default=None,
        description="ID of the connector if test succeeded"
    )
    error_type: Optional[str] = Field(
        default=None,
        description="Type of error if test failed"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if test failed"
    )
    latency_ms: float = Field(
        default=0.0,
        description="Connection test latency in milliseconds"
    )


class DiscoveryResult(BaseModel):
    """Result of a metadata discovery operation."""
    connector_id: str = Field(
        ...,
        description="ID of the connector"
    )
    schemas: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Discovered schemas"
    )
    tables: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Discovered tables"
    )
    columns: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Discovered columns"
    )
    relationships: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Discovered relationships (foreign keys, etc.)"
    )
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics"
    )


class SyncJobStatus(BaseModel):
    """Status of a metadata sync job."""
    job_id: SyncJobId = Field(
        ...,
        description="Unique job identifier"
    )
    connector_id: ConnectorId = Field(
        ...,
        description="ID of the connector being synced"
    )
    status: str = Field(
        ...,
        description="Job status: pending, running, completed, failed, cancelled"
    )
    started_at: Optional[str] = Field(
        default=None,
        description="When the job started (ISO timestamp)"
    )
    completed_at: Optional[str] = Field(
        default=None,
        description="When the job completed (ISO timestamp)"
    )
    progress: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Progress information"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if job failed"
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Sync metrics (tables synced, rows processed, etc.)"
    )


class ConnectorHealthStatus(BaseModel):
    """Health status of a connector."""
    connector_id: ConnectorId = Field(
        ...,
        description="ID of the connector"
    )
    status: str = Field(
        ...,
        description="Health status: healthy, degraded, unhealthy, unknown"
    )
    last_check_at: str = Field(
        ...,
        description="When the health check was performed (ISO timestamp)"
    )
    last_success_at: Optional[str] = Field(
        default=None,
        description="When the last successful operation occurred"
    )
    last_error_at: Optional[str] = Field(
        default=None,
        description="When the last error occurred"
    )
    error_count_24h: int = Field(
        default=0,
        description="Number of errors in the last 24 hours"
    )


class DQAPIClient:
    """
    Client for making API calls to DQ-API.
    
    Uses httpx.AsyncClient for async HTTP requests to the DQ-API service.
    Implements proper error handling, timeout configuration, and secrets redaction.
    """
    
    # Sensitive keys that should be redacted from logs
    SENSITIVE_KEYS = {'password', 'secret', 'api_key', 'token', 'credentials', 'connection_string'}
    
    def __init__(self, base_url: str, api_key_provider: Optional[Callable[[], Optional[str]]] = None, timeout: float = 30.0):
        """
        Initialize the API client.
        
        Args:
            base_url: Base URL of the DQ-API service
            api_key_provider: Callable that returns the current API key for authentication
            timeout: Request timeout in seconds (default: 30)
        """
        self.base_url = base_url.rstrip('/')
        self._api_key_provider = api_key_provider
        self.timeout = timeout
        self._base_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        # Create async client (will be used for all requests)
        self._client: Optional[httpx.AsyncClient] = None

    def _build_headers(self) -> Dict[str, str]:
        headers = dict(self._base_headers)
        if self._api_key_provider is not None:
            api_key = str(self._api_key_provider() or "").strip()
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
        return headers
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    def _redact_sensitive(self, data: Any) -> Any:
        """
        Recursively redact sensitive data from dictionaries and lists.
        
        Args:
            data: Data to redact
            
        Returns:
            Data with sensitive values replaced
        """
        if isinstance(data, dict):
            redacted = {}
            for key, value in data.items():
                # Check if key is sensitive (case-insensitive)
                if any(sensitive_key.lower() in key.lower() for sensitive_key in self.SENSITIVE_KEYS):
                    redacted[key] = '***REDACTED***'
                else:
                    redacted[key] = self._redact_sensitive(value)
            return redacted
        elif isinstance(data, list):
            return [self._redact_sensitive(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(self._redact_sensitive(item) for item in data)
        else:
            return data
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Make an API request using httpx.AsyncClient.
        
        Args:
            method: HTTP method (GET, POST, PATCH, DELETE, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments passed to httpx request
            
        Returns:
            JSON response as dictionary
            
        Raises:
            httpx.HTTPStatusError: If the response status indicates an error
            httpx.RequestError: If there was a network/connection error
            ValueError: If the response cannot be parsed as JSON
        """
        url = f"{self.base_url}{endpoint}"
        
        # Log the request (with sensitive data redacted)
        safe_kwargs = self._redact_sensitive(kwargs)
        logger.debug(f"DQAPIClient: {method} {url} - {safe_kwargs}")
        
        client = self._get_client()
        
        try:
            request_headers = self._build_headers()
            request_headers.update(kwargs.pop("headers", {}))
            response = await client.request(
                method,
                url,
                headers=request_headers,
                **kwargs
            )
            
            # Log response status
            logger.debug(f"DQAPIClient response: {response.status_code} - {url}")
            
            # Raise for status to handle HTTP errors
            response.raise_for_status()
            
            # Parse and return JSON response
            return response.json()
            
        except httpx.HTTPStatusError as e:
            # Log the error with redacted details
            logger.error(f"DQAPIClient HTTP error: {method} {url} - {e.response.status_code}")
            # Try to get error details from response
            error_details = {}
            try:
                error_details = e.response.json()
            except (ValueError, TypeError):
                error_details = {"detail": str(e)}
            
            # Redact sensitive info from error details
            safe_error = self._redact_sensitive(error_details)
            logger.error(f"Error response: {safe_error}")
            
            # Re-raise with context
            raise
        except httpx.RequestError as e:
            logger.error(f"DQAPIClient request error: {method} {url} - {str(e)}")
            raise
        except ValueError as e:
            logger.error(f"DQAPIClient JSON parse error: {method} {url} - {str(e)}")
            raise
    
    async def create_connector(self, config: ConnectorConfig) -> Dict[str, Any]:
        """Create a new connector (API-1.1)."""
        return await self._request("POST", "/api/v1/connectors", json=config.model_dump())
    
    async def validate_connector(self, config: ConnectorConfig) -> Dict[str, Any]:
        """Validate a connector configuration (API-1.1)."""
        return await self._request("POST", "/api/v1/connectors/validate", json=config.model_dump())
    
    async def test_connection(self, connector_id: ConnectorId) -> ConnectorTestResult:
        """Test a connector connection (API-1.8)."""
        response = await self._request("POST", f"/api/v1/connectors/{connector_id}/test")
        return ConnectorTestResult(**response)
    
    async def discover(self, connector_id: ConnectorId) -> DiscoveryResult:
        """Discover metadata from a connector (API-1.8)."""
        response = await self._request("POST", f"/api/v1/connectors/{connector_id}/discover")
        return DiscoveryResult(**response)
    
    async def sync_metadata(self, connector_id: ConnectorId) -> Dict[str, Any]:
        """Trigger metadata sync for a connector (API-1.9)."""
        return await self._request("POST", f"/api/v1/connectors/{connector_id}/sync")
    
    async def get_sync_status(self, job_id: SyncJobId) -> SyncJobStatus:
        """Get the status of a sync job (API-1.9)."""
        response = await self._request("GET", f"/api/v1/sync-jobs/{job_id}")
        return SyncJobStatus(**response)
    
    async def get_connector_health(self, connector_id: ConnectorId) -> ConnectorHealthStatus:
        """Get health status of a connector."""
        response = await self._request("GET", f"/api/v1/connectors/{connector_id}/health")
        return ConnectorHealthStatus(**response)
    
    async def list_connectors(self) -> List[Dict[str, Any]]:
        """List all configured connectors."""
        response = await self._request("GET", "/api/v1/connectors")
        return response.get("items", [])
    
    async def get_connector(self, connector_id: ConnectorId) -> Dict[str, Any]:
        """Get details of a specific connector."""
        return await self._request("GET", f"/api/v1/connectors/{connector_id}")
    
    async def update_connector(
        self,
        connector_id: ConnectorId,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a connector configuration."""
        return await self._request(
            "PATCH",
            f"/api/v1/connectors/{connector_id}",
            json=updates
        )
    
    async def delete_connector(self, connector_id: ConnectorId) -> Dict[str, Any]:
        """Delete a connector."""
        return await self._request("DELETE", f"/api/v1/connectors/{connector_id}")


class ConnectorTool(PiTool):
    """
    Pi Agent Tool for data source connector operations.
    
    This tool provides the following functions to the LLM:
    - configure(config: ConnectorConfig) -> Dict: Configure a new connector
    - validate(config: ConnectorConfig) -> Dict: Validate configuration
    - test_connection(connector_id: str) -> ConnectorTestResult: Test connection
    - discover(connector_id: str) -> DiscoveryResult: Discover metadata
    - sync(connector_id: str) -> Dict: Trigger metadata sync
    - get_sync_status(job_id: str) -> SyncJobStatus: Get sync job status
    - health(connector_id: str) -> ConnectorHealthStatus: Check connector health
    - list() -> List: List all connectors
    - get(connector_id: str) -> Dict: Get connector details
    
    Usage:
        connector_tool = ConnectorTool(
            api_base_url="https://kong:8443",
            api_key="your-api-key"
        )
        
        agent = DQAgent(tools=[connector_tool])
        
        # The LLM can now call these functions by name
    """
    
    name = "dq_connector"
    description = """
    Data Source Connector Management Tool for DQ-RuleBuilder.
    
    Use this tool to:
    - Configure new connectors to data sources
    - Validate connector configurations
    - Test connections to data sources
    - Discover metadata (schemas, tables, columns, relationships)
    - Sync metadata to the DQ catalog
    - Check connector health status
    
    Supported connector types:
    - postgresql: PostgreSQL database
    - sqlserver: Microsoft SQL Server
    - adls: Azure Data Lake Storage
    - s3: AWS S3 / S3-compatible storage
    - api: REST API data source
    
    Important:
    - Never include raw credentials in your requests
    - Use secure credential references where possible
    - Always validate configuration before testing connections
    """
    
    def __init__(self, api_base_url: str, api_key_provider: Optional[Callable[[], Optional[str]]] = None, timeout: float = 30.0):
        """
        Initialize the ConnectorTool.
        
        Args:
            api_base_url: Base URL of the DQ-API service
            api_key_provider: Callable that returns the current API key for authentication
            timeout: Request timeout in seconds (default: 30)
        """
        super().__init__()
        self.client = DQAPIClient(base_url=api_base_url, api_key_provider=api_key_provider, timeout=timeout)
        self.api_base_url = api_base_url
        self._initialized = True
        logger.info(f"ConnectorTool initialized: {api_base_url}")
    
    async def close(self):
        """Close the underlying HTTP client."""
        if hasattr(self.client, '_client') and self.client._client:
            await self.client._client.aclose()
            self.client._client = None
            logger.info("ConnectorTool HTTP client closed")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def configure(self, config: ConnectorConfig) -> Dict[str, Any]:
        """
        Configure a new connector.
        
        Args:
            config: Connector configuration
            
        Returns:
            Configuration result with connector_id
        """
        # Enforce the sandbox policy before any tool action is executed.
        validate_tool_invocation("dq_connector.configure", config.model_dump())

        # Redact credentials from config before logging
        safe_config = self.client._redact_sensitive(config.model_dump())
        
        logger.info(f"ConnectorTool.configure: {config.connector_type} - {config.name}")
        
        try:
            result = await self.client.create_connector(config)
            logger.info(f"ConnectorTool.configure: Successfully created connector")
            return result
        except Exception as e:
            logger.error(f"ConnectorTool.configure failed: {str(e)}")
            raise
    
    async def validate(self, config: ConnectorConfig) -> Dict[str, Any]:
        """
        Validate a connector configuration.
        
        Args:
            config: Connector configuration to validate
            
        Returns:
            Validation result with errors if any
        """
        validate_tool_invocation("dq_connector.validate", config.model_dump())
        return await self.client.validate_connector(config)
    
    async def test_connection(self, connector_id: str) -> ConnectorTestResult:
        """
        Test connection to a configured connector.
        
        Args:
            connector_id: ID of the connector to test
            
        Returns:
            Connection test result
        """
        validate_tool_invocation("dq_connector.test_connection", {"connector_id": connector_id})
        return await self.client.test_connection(connector_id)
    
    async def discover(self, connector_id: str) -> DiscoveryResult:
        """
        Discover metadata from a connector.
        
        Args:
            connector_id: ID of the connector
            
        Returns:
            Discovery result with schemas, tables, columns, etc.
        """
        validate_tool_invocation("dq_connector.discover", {"connector_id": connector_id})
        return await self.client.discover(connector_id)
    
    async def sync(self, connector_id: str) -> Dict[str, Any]:
        """
        Trigger metadata sync for a connector.
        
        Args:
            connector_id: ID of the connector to sync
            
        Returns:
            Sync job information
        """
        return await self.client.sync_metadata(connector_id)
    
    async def get_sync_status(self, job_id: str) -> SyncJobStatus:
        """
        Get the status of a metadata sync job.
        
        Args:
            job_id: ID of the sync job
            
        Returns:
            Sync job status
        """
        return await self.client.get_sync_status(job_id)
    
    async def health(self, connector_id: str) -> ConnectorHealthStatus:
        """
        Check the health status of a connector.
        
        Args:
            connector_id: ID of the connector
            
        Returns:
            Health status of the connector
        """
        return await self.client.get_connector_health(connector_id)
    
    async def list(self) -> List[Dict[str, Any]]:
        """
        List all configured connectors.
        
        Returns:
            List of connector summaries
        """
        return await self.client.list_connectors()
    
    async def get(self, connector_id: str) -> Dict[str, Any]:
        """
        Get details of a specific connector.
        
        Args:
            connector_id: ID of the connector
            
        Returns:
            Connector details
        """
        return await self.client.get_connector(connector_id)


if not PI_AGENT_AVAILABLE:
    import warnings
    warnings.warn(
        "pi-agent is not installed. ConnectorTool will not work until pi-agent is installed. "
        "Install with: pip install pi-agent",
        UserWarning
    )
