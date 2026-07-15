"""
Rule Tools for DQ Agent Harness.

This module provides Pi-compatible tools for data quality rule operations.
These tools integrate with the DQ-RuleBuilder rule execution framework (API-7).

Implemented Tools:
- RuleTool: Main tool for rule operations
  - extract: Extract rules from natural language (calls dq-llm /extract_rules)
  - validate: Validate rule configuration (calls dq-api /api/v1/rules/validate)
  - create: Create a new rule (calls dq-api /api/v1/rules)
  - update: Update an existing rule (calls dq-api /api/v1/rules/{rule_id})
  - delete: Delete a rule (calls dq-api /api/v1/rules/{rule_id})
  - assign: Assign rule to metadata attributes
  - unassign: Remove rule assignment
  - execute: Execute a rule and return results
  - get: Get rule details (calls dq-api /api/v1/rules/{rule_id})
  - list: List rules (calls dq-api /api/v1/rules)

Related Work:
- API-7: Real DQ Rule Execution
- dq-llm/entrypoint.py: /extract_rules endpoint
- dq-api: /api/v1/rules endpoints

Phase 2 Implementation (LLM-1.4)
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


class RuleAPIClient:
    """
    Client for making API calls to DQ-API and DQ-LLM for rule operations.
    
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
        logger.debug(f"RuleAPIClient: {method} {url} - {safe_kwargs}")
        
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
            logger.debug(f"RuleAPIClient response: {response.status_code} - {url}")
            
            # Raise for status to handle HTTP errors
            response.raise_for_status()
            
            # Parse and return JSON response
            return response.json()
            
        except httpx.HTTPStatusError as e:
            # Log the error with redacted details
            logger.error(f"RuleAPIClient HTTP error: {method} {url} - {e.response.status_code}")
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
            logger.error(f"RuleAPIClient request error: {method} {url} - {str(e)}")
            raise
        except ValueError as e:
            logger.error(f"RuleAPIClient JSON parse error: {method} {url} - {str(e)}")
            raise
    
    async def extract_rules(self, natural_language: str, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Extract rules from natural language using dq-llm endpoint."""
        request_body = {"text": natural_language}
        if context:
            request_body["context"] = context
        
        response = await self._request(
            self.llm_base_url,
            "POST",
            "/extract_rules",
            json=request_body
        )
        return response.get("rules", [])
    
    async def validate_rule(self, rule_config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a rule configuration using dq-api endpoint."""
        return await self._request(
            self.api_base_url,
            "POST",
            "/api/v1/rules/validate",
            json=rule_config
        )
    
    async def create_rule(self, rule_config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new rule using dq-api endpoint."""
        return await self._request(
            self.api_base_url,
            "POST",
            "/api/v1/rules",
            json=rule_config
        )
    
    async def get_rule(self, rule_id: str) -> Dict[str, Any]:
        """Get rule details using dq-api endpoint."""
        return await self._request(
            self.api_base_url,
            "GET",
            f"/api/v1/rules/{rule_id}"
        )
    
    async def update_rule(self, rule_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing rule using dq-api endpoint."""
        return await self._request(
            self.api_base_url,
            "PATCH",
            f"/api/v1/rules/{rule_id}",
            json=updates
        )
    
    async def delete_rule(self, rule_id: str) -> Dict[str, Any]:
        """Delete a rule using dq-api endpoint."""
        return await self._request(
            self.api_base_url,
            "DELETE",
            f"/api/v1/rules/{rule_id}"
        )
    
    async def list_rules(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """List rules using dq-api endpoint."""
        params = filters or {}
        response = await self._request(
            self.api_base_url,
            "GET",
            "/api/v1/rules",
            params=params
        )
        return response.get("items", [])
    
    async def assign_rule_to_metadata(self, rule_id: str, metadata_id: str, threshold_override: Optional[Any] = None) -> Dict[str, Any]:
        """
        Assign a rule to a metadata attribute.
        
        Calls dq-api POST /api/data-catalog/v1/rule-attributes endpoint.
        """
        entry = {
            "ruleId": rule_id,
            "attributeId": metadata_id
        }
        if threshold_override is not None:
            entry["thresholdOverride"] = threshold_override
        
        return await self._request(
            self.api_base_url,
            "POST",
            "/api/data-catalog/v1/rule-attributes",
            json={"entries": [entry]}
        )
    
    async def unassign_rule_from_metadata(self, rule_id: str, metadata_id: str) -> Dict[str, Any]:
        """
        Remove a rule assignment from a metadata attribute.
        
        Note: This endpoint may not be available yet in dq-api.
        As a workaround, this will use a placeholder until the DELETE endpoint is implemented.
        
        Expected endpoint: DELETE /api/data-catalog/v1/rule-attributes/{rule_id}/{metadata_id}
        """
        # Check if the dedicated delete endpoint exists
        try:
            return await self._request(
                self.api_base_url,
                "DELETE",
                f"/api/data-catalog/v1/rule-attributes/{rule_id}/{metadata_id}"
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Endpoint doesn't exist yet - return placeholder
                logger.warning(f"Unassign endpoint not available: DELETE /api/data-catalog/v1/rule-attributes/{{rule_id}}/{{metadata_id}}")
                return {
                    "status": "warning",
                    "message": "Unassign endpoint not yet implemented in dq-api. Rule assignment remains active.",
                    "rule_id": rule_id,
                    "metadata_id": metadata_id
                }
            raise
    
    async def execute_rule(self, rule_id: str, data_object_version_id: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a rule via GX suite and return results.
        
        Calls dq-api POST /gx/runs/adhoc endpoint (API-7).
        """
        payload: Dict[str, Any] = {
            "ruleIds": [rule_id],
            "status": "active",
            "latestOnly": True
        }
        
        if data_object_version_id:
            payload["dataObjectVersionId"] = data_object_version_id
        if data:
            payload["targetDataObjectVersionIds"] = [data_object_version_id] if data_object_version_id else []
        
        # Add source override if data is provided
        if data:
            payload["sourceOverrideUri"] = data.get("uri")
            payload["sourceOverrideFormat"] = data.get("format")
            payload["sourceOverrideOptions"] = data.get("options")
        
        return await self._request(
            self.api_base_url,
            "POST",
            "/gx/runs/adhoc",
            json=payload
        )


class RuleTool(PiTool):
    """
    Pi Agent Tool for data quality rule operations.
    
    This tool provides the following functions to the LLM:
    - extract(natural_language: str, context: dict) -> List[dict]: Extract rules from NL
    - validate(rule_config: dict) -> dict: Validate rule configuration
    - create(rule_config: dict) -> dict: Create a new rule
    - update(rule_id: str, updates: dict) -> dict: Update a rule
    - delete(rule_id: str) -> dict: Delete a rule
    - assign(rule_id: str, metadata_id: str) -> dict: Assign rule to metadata
    - unassign(rule_id: str, metadata_id: str) -> dict: Remove rule assignment
    - execute(rule_id: str, data: dict) -> dict: Execute a rule
    - get(rule_id: str) -> dict: Get rule details
    - list(filters: dict) -> List[dict]: List rules
    
    Phase 2 Implementation (LLM-1.4)
    Integrates with API-7 endpoints in dq-api and dq-llm.
    """
    
    name = "dq_rule"
    description = """
    Data Quality Rule Management Tool for DQ-RuleBuilder.
    
    Use this tool to:
    - Extract data quality rules from natural language requirements
    - Validate rule configurations against schema
    - Create, update, and delete rules
    - Assign rules to metadata attributes
    - Execute rules and analyze results
    
    Supported rule types:
    - NOT_NULL: Check that a field is not null
    - UNIQUE: Ensure values are unique
    - PATTERN: Validate against a regex pattern
    - RANGE: Validate value is within a range
    - IN_SET: Validate value is in a set of allowed values
    - REFERENTIAL_INTEGRITY: Validate foreign key relationships
    - CUSTOM_SQL: Execute custom SQL validation
    - ACCURACY: Check data accuracy against reference
    - CONSISTENCY: Validate cross-field consistency
    
    Note: Full functionality available. Calls actual API endpoints.
    """
    
    def __init__(
        self,
        api_base_url: str = "https://kong:8443",
        llm_base_url: str = "http://dq-llm:4020",
        api_key_provider: Optional[Callable[[], Optional[str]]] = None,
        timeout: float = 30.0
    ):
        """
        Initialize the RuleTool.
        
        Args:
            api_base_url: Base URL of the DQ-API service
            llm_base_url: Base URL of the DQ-LLM service
            api_key_provider: Callable that returns the current API key for authentication
            timeout: Request timeout in seconds (default: 30)
        """
        super().__init__()
        self.client = RuleAPIClient(
            api_base_url=api_base_url,
            llm_base_url=llm_base_url,
            api_key_provider=api_key_provider,
            timeout=timeout
        )
        self.api_base_url = api_base_url
        self.llm_base_url = llm_base_url
        self._initialized = True
        logger.info(f"RuleTool initialized: api={api_base_url}, llm={llm_base_url}")
    
    async def close(self):
        """Close the underlying HTTP client."""
        if hasattr(self.client, '_client') and self.client._client:
            await self.client._client.aclose()
            self.client._client = None
            logger.info("RuleTool HTTP client closed")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def extract(self, natural_language: str, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Extract data quality rules from natural language.
        
        Calls the dq-llm /extract_rules endpoint.
        
        Args:
            natural_language: Natural language description of rules
            context: Optional context (metadata, schema, etc.)
            
        Returns:
            List of extracted rule configurations
        """
        logger.info(f"RuleTool.extract: {natural_language[:100]}...")

        validate_tool_invocation("dq_rule.extract", {"natural_language": natural_language, "context": context})

        try:
            rules = await self.client.extract_rules(natural_language, context)
            logger.info(f"RuleTool.extract: Successfully extracted {len(rules)} rules")
            return rules
        except Exception as e:
            logger.error(f"RuleTool.extract failed: {str(e)}")
            raise
    
    async def validate(self, rule_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a rule configuration.
        
        Calls the dq-api /api/v1/rules/validate endpoint.
        
        Args:
            rule_config: Rule configuration to validate
            
        Returns:
            Validation result
        """
        logger.info(f"RuleTool.validate: validating rule configuration")

        validate_tool_invocation("dq_rule.validate", rule_config)

        try:
            result = await self.client.validate_rule(rule_config)
            logger.info(f"RuleTool.validate: Validation completed")
            return result
        except Exception as e:
            logger.error(f"RuleTool.validate failed: {str(e)}")
            raise
    
    async def create(self, rule_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new data quality rule.
        
        Calls the dq-api /api/v1/rules endpoint.
        
        Args:
            rule_config: Rule configuration
            
        Returns:
            Created rule with ID
        """
        logger.info(f"RuleTool.create: creating new rule")

        validate_tool_invocation("dq_rule.create", rule_config)

        try:
            result = await self.client.create_rule(rule_config)
            logger.info(f"RuleTool.create: Successfully created rule {result.get('id', 'unknown')}")
            return result
        except Exception as e:
            logger.error(f"RuleTool.create failed: {str(e)}")
            raise
    
    async def get(self, rule_id: str) -> Dict[str, Any]:
        """
        Get rule details.
        
        Calls the dq-api /api/v1/rules/{rule_id} endpoint.
        
        Args:
            rule_id: ID of the rule to retrieve
            
        Returns:
            Rule details
        """
        logger.info(f"RuleTool.get: retrieving rule {rule_id}")
        
        try:
            result = await self.client.get_rule(rule_id)
            logger.info(f"RuleTool.get: Successfully retrieved rule {rule_id}")
            return result
        except Exception as e:
            logger.error(f"RuleTool.get failed: {str(e)}")
            raise
    
    async def update(self, rule_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing rule.
        
        Calls the dq-api /api/v1/rules/{rule_id} endpoint with PATCH.
        
        Args:
            rule_id: ID of the rule to update
            updates: Dictionary of updates to apply
            
        Returns:
            Updated rule details
        """
        logger.info(f"RuleTool.update: updating rule {rule_id}")
        
        try:
            result = await self.client.update_rule(rule_id, updates)
            logger.info(f"RuleTool.update: Successfully updated rule {rule_id}")
            return result
        except Exception as e:
            logger.error(f"RuleTool.update failed: {str(e)}")
            raise
    
    async def delete(self, rule_id: str) -> Dict[str, Any]:
        """
        Delete a rule.
        
        Calls the dq-api /api/v1/rules/{rule_id} endpoint with DELETE.
        
        Args:
            rule_id: ID of the rule to delete
            
        Returns:
            Deletion confirmation
        """
        logger.info(f"RuleTool.delete: deleting rule {rule_id}")
        
        try:
            result = await self.client.delete_rule(rule_id)
            logger.info(f"RuleTool.delete: Successfully deleted rule {rule_id}")
            return result
        except Exception as e:
            logger.error(f"RuleTool.delete failed: {str(e)}")
            raise
    
    async def list(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        List rules.
        
        Calls the dq-api /api/v1/rules endpoint.
        
        Args:
            filters: Optional filters to apply
            
        Returns:
            List of rule summaries
        """
        logger.info(f"RuleTool.list: listing rules with filters: {filters}")
        
        try:
            rules = await self.client.list_rules(filters)
            logger.info(f"RuleTool.list: Successfully retrieved {len(rules)} rules")
            return rules
        except Exception as e:
            logger.error(f"RuleTool.list failed: {str(e)}")
            raise
    
    async def assign(self, rule_id: str, metadata_id: str, threshold_override: Optional[Any] = None) -> Dict[str, Any]:
        """
        Assign a rule to a metadata attribute.
        
        Calls dq-api POST /api/data-catalog/v1/rule-attributes endpoint.
        
        Args:
            rule_id: ID of the rule to assign
            metadata_id: ID of the metadata attribute
            threshold_override: Optional threshold override value
            
        Returns:
            Assignment confirmation with count of added assignments
        """
        logger.info(f"RuleTool.assign: assigning rule {rule_id} to metadata {metadata_id}")
        
        try:
            result = await self.client.assign_rule_to_metadata(rule_id, metadata_id, threshold_override)
            logger.info(f"RuleTool.assign: Successfully assigned rule {rule_id} to metadata {metadata_id}")
            return result
        except Exception as e:
            logger.error(f"RuleTool.assign failed: {str(e)}")
            raise
    
    async def unassign(self, rule_id: str, metadata_id: str) -> Dict[str, Any]:
        """
        Remove a rule assignment from a metadata attribute.
        
        Calls dq-api DELETE /api/data-catalog/v1/rule-attributes/{rule_id}/{metadata_id} endpoint.
        Note: This endpoint may not be available yet - falls back to warning message.
        
        Args:
            rule_id: ID of the rule to unassign
            metadata_id: ID of the metadata attribute
            
        Returns:
            Unassignment confirmation
        """
        logger.info(f"RuleTool.unassign: unassigning rule {rule_id} from metadata {metadata_id}")
        
        try:
            result = await self.client.unassign_rule_from_metadata(rule_id, metadata_id)
            logger.info(f"RuleTool.unassign: Successfully unassigned rule {rule_id} from metadata {metadata_id}")
            return result
        except Exception as e:
            logger.error(f"RuleTool.unassign failed: {str(e)}")
            raise
    
    async def execute(self, rule_id: str, data_object_version_id: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a rule and return results.
        
        Calls dq-api POST /gx/runs/adhoc endpoint (API-7).
        
        Args:
            rule_id: ID of the rule to execute
            data_object_version_id: Optional specific data object version to execute against
            data: Optional data execution context (uri, format, options)
            
        Returns:
            Execution run details and results
        """
        logger.info(f"RuleTool.execute: executing rule {rule_id}")

        validate_tool_invocation(
            "dq_rule.execute",
            {"rule_id": rule_id, "data_object_version_id": data_object_version_id, "data": data},
        )

        try:
            result = await self.client.execute_rule(rule_id, data_object_version_id, data)
            logger.info(f"RuleTool.execute: Successfully executed rule {rule_id}")
            return result
        except Exception as e:
            logger.error(f"RuleTool.execute failed: {str(e)}")
            raise


if not PI_AGENT_AVAILABLE:
    import warnings
    warnings.warn(
        "pi-agent is not installed. RuleTool will not work until pi-agent is installed. "
        "Install with: pip install pi-agent",
        UserWarning
    )
