"""
Definition Tools for DQ Agent Harness.

This module provides Pi-compatible tools for data definition and glossary operations.
These tools integrate with the existing dq-llm definition generation service.

Implemented Tools:
- DefinitionTool: Main tool for definition operations
  - generate: Generate data definitions (calls dq-llm /generate_data_definitions)
  - create_glossary_entry: Create glossary entry (calls dq-llm /generate_data_definitions)
  - update_glossary_entry: Update glossary entry
  - query_metadata: Query metadata catalog (calls dq-api /api/v1/metadata)
  - search_definitions: Search data definitions
  - get_definition: Get definition details

Related Work:
- dq-llm/entrypoint.py: Existing /generate_data_definitions endpoint
- dq-api: /api/v1/metadata endpoint

Phase 2 Implementation (LLM-1.5)
"""

from typing import Any, Callable, Dict, List, Optional
import httpx
import logging

from ..sandbox import validate_tool_invocation

# Placeholder for Pi Agent Tool base class
try:
    from pi_agent import Tool as PiTool
    PI_AGENT_AVAILABLE = True
except ImportError:
    PI_AGENT_AVAILABLE = False
    PiTool = object  # type: ignore

logger = logging.getLogger(__name__)


class DefinitionAPIClient:
    """
    Client for making API calls to DQ-API and DQ-LLM for definition operations.
    
    Uses httpx.AsyncClient for async HTTP requests.
    Implements proper error handling, timeout configuration, and secrets redaction.
    """
    
    # Sensitive keys that should be redacted from logs
    SENSITIVE_KEYS = {'password', 'secret', 'api_key', 'token', 'credentials', 'connection_string'}
    
    def __init__(self, api_base_url: str, llm_base_url: str, api_key_provider: Optional[Callable[[], Optional[str]]] = None, timeout: float = 30.0):
        """
        Initialize the API client.
        
        Args:
            api_base_url: Base URL of the DQ-API service
            llm_base_url: Base URL of the DQ-LLM service
            api_key_provider: Callable that returns the current API key for authentication
            timeout: Request timeout in seconds (default: 30)
        """
        self.api_base_url = api_base_url.rstrip('/')
        self.llm_base_url = llm_base_url.rstrip('/')
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
        base_url: str,
        method: str,
        endpoint: str,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Make an API request using httpx.AsyncClient.
        
        Args:
            base_url: Base URL (api or llm)
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
        url = f"{base_url}{endpoint}"
        
        # Log the request (with sensitive data redacted)
        safe_kwargs = self._redact_sensitive(kwargs)
        logger.debug(f"DefinitionAPIClient: {method} {url} - {safe_kwargs}")
        
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
            logger.debug(f"DefinitionAPIClient response: {response.status_code} - {url}")
            
            # Raise for status to handle HTTP errors
            response.raise_for_status()
            
            # Parse and return JSON response
            return response.json()
            
        except httpx.HTTPStatusError as e:
            # Log the error with redacted details
            logger.error(f"DefinitionAPIClient HTTP error: {method} {url} - {e.response.status_code}")
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
            logger.error(f"DefinitionAPIClient request error: {method} {url} - {str(e)}")
            raise
        except ValueError as e:
            logger.error(f"DefinitionAPIClient JSON parse error: {method} {url} - {str(e)}")
            raise
    
    async def generate_definitions(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Generate data definitions using dq-llm endpoint."""
        return await self._request(
            self.llm_base_url,
            "POST",
            "/generate_data_definitions",
            json=request
        )
    
    async def query_metadata(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """Query metadata catalog using dq-api endpoint."""
        return await self._request(
            self.api_base_url,
            "POST",
            "/api/v1/metadata/query",
            json=query
        )
    
    async def search_definitions(self, query: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Search definitions using dq-api registry endpoint."""
        params = {"query": query}
        if filters:
            # Convert filters dict to query parameters
            params.update({k: v for k, v in filters.items() if v is not None})
        
        response = await self._request(
            self.api_base_url,
            "GET",
            "/api/v1/registry/definitions",
            params=params
        )
        return response if isinstance(response, list) else response.get("items", [])
    
    async def get_definition(self, definition_id: str) -> Dict[str, Any]:
        """Get a specific definition using dq-api registry endpoint."""
        response = await self._request(
            self.api_base_url,
            "GET",
            f"/api/v1/registry/definitions/{definition_id}"
        )
        return response
    
    async def create_glossary_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Create a glossary entry using dq-llm endpoint."""
        # Use the generate_definitions endpoint which includes glossary term generation
        return await self._request(
            self.llm_base_url,
            "POST",
            "/generate_data_definitions",
            json={"glossary_terms": [entry]}
        )
    
    async def update_glossary_entry(self, entry_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update a glossary entry using dq-llm endpoint."""
        # For now, we'll use the generate_definitions endpoint with update semantics
        # TODO: Implement dedicated glossary update endpoint when available
        return await self._request(
            self.llm_base_url,
            "POST",
            "/generate_data_definitions",
            json={
                "glossary_terms": [{
                    "id": entry_id,
                    **updates
                }]
            }
        )


class DefinitionTool(PiTool):
    """
    Pi Agent Tool for data definition and glossary operations.
    
    This tool provides the following functions to the LLM:
    - generate(request: dict) -> dict: Generate data definitions
    - create_glossary_entry(entry: dict) -> dict: Create glossary entry
    - update_glossary_entry(entry_id: str, updates: dict) -> dict: Update glossary entry
    - query_metadata(query: dict) -> dict: Query metadata catalog
    - search_definitions(query: str) -> List[dict]: Search definitions
    - get_definition(definition_id: str) -> dict: Get definition details
    
    Phase 2 Implementation (LLM-1.5)
    Integrates with dq-llm /generate_data_definitions and dq-api /api/v1/metadata endpoints.
    """
    
    name = "dq_definition"
    description = """
    Data Definition and Glossary Management Tool for DQ-RuleBuilder.
    
    Use this tool to:
    - Generate data definitions from context (calls dq-llm /generate_data_definitions)
    - Create and update glossary entries (calls dq-llm /generate_data_definitions)
    - Query metadata catalog (calls dq-api /api/v1/metadata/query)
    - Search existing definitions (calls dq-api /api/v1/registry/definitions)
    - Get definition details (calls dq-api /api/v1/registry/definitions/{id})
    
    Note: Full functionality available. Calls actual API-7 and dq-api endpoints.
    """
    
    def __init__(
        self,
        api_base_url: str = "http://kong:8000",
        llm_base_url: str = "http://dq-llm:4020",
        api_key_provider: Optional[Callable[[], Optional[str]]] = None,
        timeout: float = 30.0
    ):
        """
        Initialize the DefinitionTool.
        
        Args:
            api_base_url: Base URL of the DQ-API service
            llm_base_url: Base URL of the DQ-LLM service
            api_key_provider: Callable that returns the current API key for authentication
            timeout: Request timeout in seconds (default: 30)
        """
        super().__init__()
        self.client = DefinitionAPIClient(
            api_base_url=api_base_url,
            llm_base_url=llm_base_url,
            api_key_provider=api_key_provider,
            timeout=timeout
        )
        self.api_base_url = api_base_url
        self.llm_base_url = llm_base_url
        self._initialized = True
        logger.info(f"DefinitionTool initialized: api={api_base_url}, llm={llm_base_url}")
    
    async def close(self):
        """Close the underlying HTTP client."""
        if hasattr(self.client, '_client') and self.client._client:
            await self.client._client.aclose()
            self.client._client = None
            logger.info("DefinitionTool HTTP client closed")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def generate(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate data definitions.
        
        Calls the dq-llm /generate_data_definitions endpoint.
        
        Args:
            request: Definition generation request
            
        Returns:
            Generated definitions with glossary terms
        """
        logger.info(f"DefinitionTool.generate: {str(request)[:100]}...")

        validate_tool_invocation("dq_definition.generate", request)

        try:
            result = await self.client.generate_definitions(request)
            logger.info(f"DefinitionTool.generate: Successfully generated definitions")
            return result
        except Exception as e:
            logger.error(f"DefinitionTool.generate failed: {str(e)}")
            raise
    
    async def create_glossary_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a glossary entry.
        
        Calls the dq-llm /generate_data_definitions endpoint with glossary term.
        
        Args:
            entry: Glossary entry configuration
            
        Returns:
            Created glossary entry
        """
        logger.info(f"DefinitionTool.create_glossary_entry: creating glossary entry")

        validate_tool_invocation("dq_definition.create_glossary_entry", entry)

        try:
            result = await self.client.create_glossary_entry(entry)
            logger.info(f"DefinitionTool.create_glossary_entry: Successfully created glossary entry")
            return result
        except Exception as e:
            logger.error(f"DefinitionTool.create_glossary_entry failed: {str(e)}")
            raise
    
    async def update_glossary_entry(self, entry_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a glossary entry.
        
        Calls the dq-llm /generate_data_definitions endpoint with updated glossary term.
        
        Args:
            entry_id: ID of the glossary entry to update
            updates: Dictionary of updates to apply
            
        Returns:
            Updated glossary entry
        """
        logger.info(f"DefinitionTool.update_glossary_entry: updating glossary entry {entry_id}")

        validate_tool_invocation("dq_definition.update_glossary_entry", {"entry_id": entry_id, "updates": updates})

        try:
            result = await self.client.update_glossary_entry(entry_id, updates)
            logger.info(f"DefinitionTool.update_glossary_entry: Successfully updated glossary entry {entry_id}")
            return result
        except Exception as e:
            logger.error(f"DefinitionTool.update_glossary_entry failed: {str(e)}")
            raise
    
    async def query_metadata(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Query the metadata catalog.
        
        Calls the dq-api /api/v1/metadata/query endpoint.
        
        Args:
            query: Metadata query parameters
            
        Returns:
            Query results
        """
        logger.info(f"DefinitionTool.query_metadata: {str(query)[:100]}...")

        validate_tool_invocation("dq_definition.query_metadata", query)

        try:
            result = await self.client.query_metadata(query)
            logger.info(f"DefinitionTool.query_metadata: Successfully queried metadata")
            return result
        except Exception as e:
            logger.error(f"DefinitionTool.query_metadata failed: {str(e)}")
            raise
    
    async def search_definitions(self, query: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search existing definitions.
        
        Calls the dq-api /api/v1/registry/definitions endpoint.
        
        Args:
            query: Search query string
            filters: Optional filters to apply
            
        Returns:
            List of matching definitions
        """
        logger.info(f"DefinitionTool.search_definitions: {query[:100]}...")

        validate_tool_invocation("dq_definition.search_definitions", {"query": query, "filters": filters})

        try:
            result = await self.client.search_definitions(query, filters)
            logger.info(f"DefinitionTool.search_definitions: Found {len(result)} definitions")
            return result
        except Exception as e:
            logger.error(f"DefinitionTool.search_definitions failed: {str(e)}")
            raise
    
    async def get_definition(self, definition_id: str) -> Dict[str, Any]:
        """
        Get a specific definition.
        
        Calls the dq-api /api/v1/registry/definitions/{definition_id} endpoint.
        
        Args:
            definition_id: ID of the definition to retrieve
            
        Returns:
            Definition details
        """
        logger.info(f"DefinitionTool.get_definition: {definition_id}")

        validate_tool_invocation("dq_definition.get_definition", {"definition_id": definition_id})

        try:
            result = await self.client.get_definition(definition_id)
            logger.info(f"DefinitionTool.get_definition: Successfully retrieved definition {definition_id}")
            return result
        except Exception as e:
            logger.error(f"DefinitionTool.get_definition failed: {str(e)}")
            raise


if not PI_AGENT_AVAILABLE:
    import warnings
    warnings.warn(
        "pi-agent is not installed. DefinitionTool will not work until pi-agent is installed. "
        "Install with: pip install pi-agent",
        UserWarning
    )
