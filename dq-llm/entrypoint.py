import base64
import json
import logging
import os
import re
import importlib
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4
from urllib import error as urllib_error
from urllib import request as urllib_request

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import Response, APIRouter, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from starlette.concurrency import run_in_threadpool

from telemetry import configure_telemetry, instrument_app

from agents.audit import get_audit_logger
from agents.sandbox import PromptInjectionDetected, detect_prompt_injection


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [entrypoint] %(levelname)s: %(message)s",
)
logger = logging.getLogger("entrypoint")


class LLMServiceUnavailableError(RuntimeError):
    """Raised when the configured LLM provider/runtime cannot be reached or initialized."""


class LLMServiceResponseError(ValueError):
    """Raised when the LLM returns malformed or contract-invalid payloads."""

PROMPT_DIR = Path(__file__).resolve().parent
EXTRACT_RULES_PROMPT_PATH = PROMPT_DIR / "extract_rules_prompt.jinja2"

MODEL_ID = os.getenv("DQ_LLM_MODEL_ID", "Qwen/Qwen2.5-7B-Instruct")

# Smaller model options for faster startup
SMALL_MODEL_ID = os.getenv("DQ_LLM_SMALL_MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")

DEVICE_MAP = os.getenv("DQ_LLM_DEVICE_MAP", "auto")
MAX_NEW_TOKENS = int(os.getenv("DQ_LLM_MAX_NEW_TOKENS", "512"))
CHAT_PROVIDER = os.getenv("DQ_LLM_CHAT_PROVIDER", "huggingface").strip().lower() or "huggingface"
OLLAMA_BASE_URL = os.getenv("DQ_LLM_OLLAMA_BASE_URL", "").strip().rstrip("/")
OLLAMA_MODEL = os.getenv("DQ_LLM_OLLAMA_MODEL", "").strip()
MAX_RETRIES = max(1, int(os.getenv("DQ_LLM_MAX_RETRIES", "3")))
LOAD_IN_4BIT = os.getenv("DQ_LLM_LOAD_IN_4BIT", "false").strip().lower() in ("1", "true")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("DQ_LLM_OLLAMA_TIMEOUT_SECONDS", "180"))
TLS_CERT_FILE = os.getenv("DQ_LLM_TLS_CERT_FILE", "/etc/dq-llm/certs/tls.crt")
TLS_KEY_FILE = os.getenv("DQ_LLM_TLS_KEY_FILE", "/etc/dq-llm/certs/tls.key")

DEFAULT_APPROVAL_CRITERIA = [
    "Business meaning is unambiguous and aligns with the logical data model.",
    "Value-domain expectations, constraints, and examples are explicit and reviewable.",
    "The definition identifies accountable stewardship and source provenance.",
    "The definition is traceable and governable for BCBS 239 evidence and audit needs.",
]

DEFAULT_POLICY_DOCUMENTS = [
    {
        "name": "Guidelines for Definitions of Business Terms",
        "version": "1.0",
        "source": "Data Definition Board",
    },
    {
        "name": "BCBS 239 Principles for Effective Risk Data Aggregation and Risk Reporting",
        "version": "2013",
        "source": "Basel Committee on Banking Supervision",
    },
]


class TextRequest(BaseModel):
    text: str


class ContextDocument(BaseModel):
    document_type: str
    name: str
    content: str
    source_uri: str | None = None


class DefinitionTarget(BaseModel):
    target_id: str | None = None
    data_set_name: str
    data_object_name: str
    attribute_name: str
    display_name: str | None = None
    data_type: str | None = None
    nullable: bool | None = None
    description: str | None = None
    logical_path: str | None = None
    source_system: str | None = None
    steward_notes: str | None = None
    sample_values: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewFeedback(BaseModel):
    feedback_id: str | None = None
    source_role: str
    comment: str
    author_name: str | None = None
    disposition: str | None = None
    target_ids: list[str] = Field(default_factory=list)


class BoardApproval(BaseModel):
    board_name: str | None = None
    status: str = "pending"
    approver_name: str | None = None
    approval_notes: str | None = None
    approved_at: str | None = None


class DataDefinitionRequest(BaseModel):
    task_id: str
    steward_name: str | None = None
    board_name: str = "Data Definition Board"
    glossary_name: str | None = None
    glossary_display_name: str | None = None
    domain_name: str | None = None
    source_system: str | None = None
    user_input: str | None = None
    policies: list[str] = Field(default_factory=list)
    targets: list[DefinitionTarget]
    context_documents: list[ContextDocument] = Field(default_factory=list)
    feedback_items: list[ReviewFeedback] = Field(default_factory=list)
    board_approval: BoardApproval | None = None


app = FastAPI(title="DQ LLM Service")
configure_telemetry()
instrument_app(app)

_metrics_lock = threading.Lock()
_llm_requests_in_flight = 0
_llm_extract_rules_in_flight = 0
_llm_generate_definitions_in_flight = 0
_llm_extract_rules_requests_total = 0
_llm_extract_rules_failures_total = 0
_llm_generate_definitions_requests_total = 0
_llm_generate_definitions_failures_total = 0

# Agent Harness Metrics (LLM-1.17)
_agent_sessions_active = 0
_agent_sessions_total = 0
_agent_tool_calls_total = 0
_agent_tool_errors_total = 0
_agent_latency_seconds_total = 0.0
_agent_tool_calls_by_type: dict = {}


# ============================================================================
# Agent Harness API Endpoints (Phase 4 - LLM-1.11 to LLM-1.14)
# ============================================================================

security = HTTPBearer(auto_error=False)


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    try:
        parts = str(token).split(".")
        if len(parts) != 3:
            return None

        payload_segment = parts[1].replace("-", "+").replace("_", "/")
        padding = (4 - (len(payload_segment) % 4)) % 4
        decoded = base64.urlsafe_b64decode(payload_segment + ("=" * padding))
        payload = json.loads(decoded.decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def require_agent_auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    if credentials is None or str(credentials.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token")

    payload = _decode_jwt_payload(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    now = time.time()
    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and exp <= now:
        raise HTTPException(status_code=401, detail="Token expired")

    nbf = payload.get("nbf")
    if isinstance(nbf, (int, float)) and nbf > now:
        raise HTTPException(status_code=401, detail="Token is not yet valid")

    subject = next(
        (value for value in (payload.get("sub"), payload.get("preferred_username"), payload.get("email"), payload.get("upn")) if value),
        None,
    )
    if not subject:
        raise HTTPException(status_code=401, detail="Token missing subject")

    return payload


# Create agent router with prefix
agent_router = APIRouter(
    prefix="/api/llm/v1/agent",
    tags=["agent"],
    dependencies=[Depends(require_agent_auth)],
)


# Pydantic models for agent requests/responses
class AgentRequest(BaseModel):
    """Request model for running an agent."""
    prompt: str = Field(..., description="The user prompt for the agent")
    agent_type: str = Field(
        ...,
        description="Type of agent: dq_connector|dq_rule|dq_steward|general"
    )
    connector_id: Optional[str] = Field(
        default=None,
        description="Optional connector ID for context"
    )
    metadata_id: Optional[str] = Field(
        default=None,
        description="Optional metadata ID for context"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session ID for persistent sessions"
    )
    context: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional context for the agent"
    )


class ToolCallResult(BaseModel):
    """Model for a single tool call result."""
    tool_name: str = Field(..., description="Name of the tool called")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters passed to the tool")
    result: Dict[str, Any] = Field(default_factory=dict, description="Result from the tool")
    duration_ms: float = Field(default=0.0, description="Duration of tool execution in milliseconds")
    success: bool = Field(default=True, description="Whether the tool call succeeded")
    error: Optional[str] = Field(default=None, description="Error message if tool call failed")


class AgentResponse(BaseModel):
    """Response model from an agent."""
    response: str = Field(..., description="The agent's response text")
    session_id: str = Field(..., description="Session ID for this interaction")
    tool_calls: List[ToolCallResult] = Field(
        default_factory=list,
        description="List of tool calls made by the agent"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata from the agent"
    )
    error: Optional[str] = Field(default=None, description="Error message if agent execution failed")


class SessionCreateResponse(BaseModel):
    """Response model for session creation."""
    session_id: str = Field(..., description="The created session ID")
    agent_type: str = Field(..., description="Type of agent for this session")
    created_at: str = Field(..., description="ISO timestamp of session creation")


class AgentHealthResponse(BaseModel):
    """Response model for agent health check."""
    status: bool = Field(..., description="Whether the agent service is healthy")
    agents_available: List[str] = Field(
        default_factory=list,
        description="List of available agent types"
    )
    active_sessions: int = Field(default=0, description="Number of active sessions")
    total_requests: int = Field(default=0, description="Total agent requests processed")


def _resolve_agent_subject(auth_payload: dict[str, Any]) -> str | None:
    for field_name in ("sub", "preferred_username", "email", "upn"):
        value = auth_payload.get(field_name)
        if value:
            return str(value)
    return None


async def _record_agent_audit_event(
    *,
    action: str,
    endpoint: str,
    method: str,
    response_type: str,
    status_code: int,
    success: bool,
    session_id: str,
    auth_payload: dict[str, Any],
    agent_type: str,
    prompt: str | None = None,
    response_text: str | None = None,
    tool_calls: list[ToolCallResult] | None = None,
    metadata: dict[str, Any] | None = None,
    error_message: str | None = None,
    duration_ms: float | None = None,
) -> None:
    audit_logger = get_audit_logger()
    user_id = _resolve_agent_subject(auth_payload)
    tool_call_payloads = [call.model_dump(mode="python", by_alias=False) for call in tool_calls or []]
    parameters: dict[str, Any] = {
        "session_id": session_id,
        "agent_type": agent_type,
    }
    if prompt is not None:
        parameters["prompt"] = prompt
    if metadata:
        parameters["metadata"] = metadata
    if tool_call_payloads:
        parameters["tool_calls"] = tool_call_payloads

    result: dict[str, Any] = {}
    if response_text is not None:
        result["response"] = response_text
    if tool_call_payloads:
        result["tool_calls"] = tool_call_payloads
    if metadata:
        result["metadata"] = metadata

    await audit_logger.record_existing_audit_event(
        action=action,
        endpoint=endpoint,
        method=method,
        response_type=response_type,
        status_code=status_code,
        success=success,
        session_id=session_id,
        user_id=user_id,
        agent_type=agent_type,
        agent_source="dq-llm",
        agent_instance_id=session_id,
        request_origin="dq-llm",
        request_id=uuid4().hex,
        correlation_id=session_id,
        prompt=prompt,
        response=response_text,
        parameters=parameters,
        result=result,
        duration_ms=duration_ms,
        error_message=error_message,
        metadata=metadata,
    )


# Helper to get agent factory (lazy import to avoid circular dependencies)
def _get_agent_factory():
    from agents.base import DQAgentFactory
    return DQAgentFactory()


@agent_router.post("/run", response_model=AgentResponse, summary="Run an agent")
async def run_agent(
    request: AgentRequest,
    auth_payload: dict[str, Any] = Depends(require_agent_auth),
):
    """
    Run a specialized DQ agent with the given prompt.
    
    This endpoint creates a new session (if not provided) and runs the specified
    agent type with the user's prompt. The agent can call tools and return
    results through a conversational interface.
    
    Args:
        request: AgentRequest containing prompt, agent type, and optional context
        
    Returns:
        AgentResponse with the agent's response, session ID, and tool calls
    """
    global _agent_latency_seconds_total, _agent_sessions_active, _agent_sessions_total, _agent_tool_calls_total
    
    import time
    from datetime import datetime
    
    factory = _get_agent_factory()
    
    # Generate session ID if not provided
    session_id = request.session_id or f"agent_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    
    try:
        detect_prompt_injection(request.prompt)
    except PromptInjectionDetected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Create the appropriate agent
    agent_type = request.agent_type.lower()
    
    if agent_type == "dq_connector":
        agent = factory.create_connector_agent(session_id=session_id)
    elif agent_type == "dq_rule":
        agent = factory.create_rule_agent(session_id=session_id)
    elif agent_type == "dq_steward":
        agent = factory.create_steward_agent(session_id=session_id)
    elif agent_type == "general":
        agent = factory.create_general_agent(session_id=session_id)
    else:
        available = ["dq_connector", "dq_rule", "dq_steward", "general"]
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent type: {request.agent_type}. Available types: {available}"
        )
    
    # Track session
    with _metrics_lock:
        _agent_sessions_active += 1
        _agent_sessions_total += 1
    
    start_time = time.time()
    
    try:
        # Run the agent with the prompt
        # The agent will automatically use the appropriate tools
        result = await agent.run(
            prompt=request.prompt,
            context=request.context or {}
        )
        
        # Parse the result based on its type
        # Pi Agent returns a dict with 'response' and 'tool_calls' keys
        if isinstance(result, dict):
            response_text = result.get("response", str(result))
            raw_tool_calls = result.get("tool_calls", [])
            metadata = result.get("metadata", {})
        else:
            response_text = str(result)
            raw_tool_calls = []
            metadata = {}
        
        # Update tool call metrics
        with _metrics_lock:
            _agent_tool_calls_total += len(raw_tool_calls)
            for call in raw_tool_calls:
                if isinstance(call, dict):
                    tool_name = call.get("tool_name", call.get("tool", "unknown"))
                    _agent_tool_calls_by_type[tool_name] = _agent_tool_calls_by_type.get(tool_name, 0) + 1
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Update latency metric
        with _metrics_lock:
            _agent_latency_seconds_total += duration
        
        # Convert tool calls to standardized format
        tool_calls = []
        for call in raw_tool_calls:
            if isinstance(call, dict):
                tool_calls.append(ToolCallResult(
                    tool_name=call.get("tool_name", call.get("tool", "unknown")),
                    parameters=call.get("parameters", call.get("args", {})),
                    result=call.get("result", {}),
                    duration_ms=call.get("duration_ms", 0.0),
                    success=call.get("success", True),
                    error=call.get("error")
                ))

        await _record_agent_audit_event(
            action="run_agent",
            endpoint="/api/llm/v1/agent/run",
            method="POST",
            response_type="agent_response",
            status_code=200,
            success=True,
            session_id=session_id,
            auth_payload=auth_payload,
            agent_type=agent_type,
            prompt=request.prompt,
            response_text=response_text,
            tool_calls=tool_calls,
            metadata={
                "connector_id": request.connector_id,
                "metadata_id": request.metadata_id,
                "context": request.context or {},
                "duration_seconds": duration,
                "agent_type": agent_type,
            },
            duration_ms=duration * 1000.0,
        )
        
        return AgentResponse(
            response=response_text,
            session_id=session_id,
            tool_calls=tool_calls,
            metadata={
                "duration_seconds": duration,
                "agent_type": agent_type,
                **metadata
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        with _metrics_lock:
            _agent_tool_errors_total += 1
        logger.error(f"Agent execution failed: {str(e)}", exc_info=True)
        await _record_agent_audit_event(
            action="run_agent",
            endpoint="/api/llm/v1/agent/run",
            method="POST",
            response_type="server_error_response",
            status_code=500,
            success=False,
            session_id=session_id,
            auth_payload=auth_payload,
            agent_type=agent_type,
            prompt=request.prompt,
            metadata={
                "connector_id": request.connector_id,
                "metadata_id": request.metadata_id,
                "context": request.context or {},
                "agent_type": agent_type,
            },
            error_message=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        with _metrics_lock:
            _agent_sessions_active = max(0, _agent_sessions_active - 1)


@agent_router.post("/session/create", response_model=SessionCreateResponse, summary="Create agent session")
async def create_agent_session(
    agent_type: str = Query(..., description="Type of agent to create session for"),
    auth_payload: dict[str, Any] = Depends(require_agent_auth),
):
    """
    Create a new persistent agent session.
    
    Sessions allow maintaining state across multiple interactions with an agent.
    The session ID can be used in subsequent requests to continue the conversation.
    
    Args:
        agent_type: Type of agent (dq_connector, dq_rule, dq_steward, general)
        
    Returns:
        SessionCreateResponse with the new session ID
    """
    global _agent_sessions_active, _agent_sessions_total

    from datetime import datetime
    
    factory = _get_agent_factory()
    
    # Validate agent type
    agent_type = agent_type.lower()
    if agent_type not in ["dq_connector", "dq_rule", "dq_steward", "general"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent type: {agent_type}"
        )
    
    # Generate session ID
    session_id = f"agent_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    
    # Create the agent (this initializes the session)
    if agent_type == "dq_connector":
        agent = factory.create_connector_agent(session_id=session_id)
    elif agent_type == "dq_rule":
        agent = factory.create_rule_agent(session_id=session_id)
    elif agent_type == "dq_steward":
        agent = factory.create_steward_agent(session_id=session_id)
    else:
        agent = factory.create_general_agent(session_id=session_id)
    
    # Track session creation
    with _metrics_lock:
        _agent_sessions_total += 1
        _agent_sessions_active += 1

    await _record_agent_audit_event(
        action="create_session",
        endpoint="/api/llm/v1/agent/session/create",
        method="POST",
        response_type="session_create_response",
        status_code=200,
        success=True,
        session_id=session_id,
        auth_payload=auth_payload,
        agent_type=agent_type,
        metadata={"agent_type": agent_type},
    )
    
    return SessionCreateResponse(
        session_id=session_id,
        agent_type=agent_type,
        created_at=datetime.utcnow().isoformat()
    )


@agent_router.get("/session/{session_id}", response_model=AgentResponse, summary="Get agent session")
async def get_agent_session(session_id: str):
    """
    Retrieve an existing agent session.
    
    This returns the current state of the session, including conversation history
    and any metadata collected during the session.
    
    Args:
        session_id: ID of the session to retrieve
        
    Returns:
        AgentResponse with current session state
    """
    factory = _get_agent_factory()
    
    # Try to get the session - for now, we'll create a simple response
    # In a full implementation, we would retrieve the session from a store
    return AgentResponse(
        response=f"Session {session_id} retrieved. Full session persistence coming soon.",
        session_id=session_id,
        metadata={"status": "active", "session_id": session_id}
    )


@agent_router.post("/session/{session_id}/interact", response_model=AgentResponse, summary="Interact with agent session")
async def interact_with_session(
    session_id: str,
    prompt: str,
    auth_payload: dict[str, Any] = Depends(require_agent_auth),
):
    """
    Send a message to an existing agent session.
    
    This allows continuing a conversation with an agent across multiple
    interactions, maintaining context and state.
    
    Args:
        session_id: ID of the session to interact with
        prompt: The user prompt to send to the agent
        
    Returns:
        AgentResponse with the agent's reply
    """
    factory = _get_agent_factory()
    
    # For now, create a new agent with the session ID
    # Full session persistence would retrieve the existing session
    agent = factory.create_general_agent(session_id=session_id)
    
    try:
        result = await agent.run(prompt=prompt)
        
        # Parse the result based on its type
        if isinstance(result, dict):
            response_text = result.get("response", str(result))
            raw_tool_calls = result.get("tool_calls", [])
            metadata = result.get("metadata", {})
        else:
            response_text = str(result)
            raw_tool_calls = []
            metadata = {}
        
        # Convert tool calls to standardized format
        tool_calls = []
        for call in raw_tool_calls:
            if isinstance(call, dict):
                tool_calls.append(ToolCallResult(
                    tool_name=call.get("tool_name", call.get("tool", "unknown")),
                    parameters=call.get("parameters", call.get("args", {})),
                    result=call.get("result", {}),
                    duration_ms=call.get("duration_ms", 0.0),
                    success=call.get("success", True),
                    error=call.get("error")
                ))

        await _record_agent_audit_event(
            action="interact_session",
            endpoint=f"/api/llm/v1/agent/session/{session_id}/interact",
            method="POST",
            response_type="agent_response",
            status_code=200,
            success=True,
            session_id=session_id,
            auth_payload=auth_payload,
            agent_type="general",
            prompt=prompt,
            response_text=response_text,
            tool_calls=tool_calls,
            metadata={"session_id": session_id, "tool_call_count": len(tool_calls)},
        )
        
        return AgentResponse(
            response=response_text,
            session_id=session_id,
            tool_calls=tool_calls,
            metadata=metadata
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session interaction failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@agent_router.delete("/session/{session_id}", response_model=Dict[str, bool], summary="Delete agent session")
async def delete_agent_session(
    session_id: str,
    auth_payload: dict[str, Any] = Depends(require_agent_auth),
):
    """
    Destroy an agent session.
    
    This cleans up resources associated with a session. Note that session
    state is ephemeral and sessions may automatically expire after timeout.
    
    Args:
        session_id: ID of the session to delete
        
    Returns:
        Dictionary with deletion confirmation
    """
    global _agent_sessions_active

    await _record_agent_audit_event(
        action="delete_session",
        endpoint=f"/api/llm/v1/agent/session/{session_id}",
        method="DELETE",
        response_type="delete_response",
        status_code=200,
        success=True,
        session_id=session_id,
        auth_payload=auth_payload,
        agent_type="general",
        metadata={"session_id": session_id},
    )

    # Clean up session tracking
    with _metrics_lock:
        _agent_sessions_active = max(0, _agent_sessions_active - 1)
    
    return {"deleted": True, "session_id": session_id}


@agent_router.get("/agents", response_model=List[Dict[str, Any]], summary="List available agents")
async def list_available_agents():
    """
    List all available specialized agent types.
    
    Returns:
        List of agent type descriptions
    """
    return [
        {
            "id": "dq_connector",
            "name": "Connector Onboarding Agent",
            "description": "Automate end-to-end connector onboarding for PostgreSQL, SQL Server, ADLS, S3, and API data sources",
            "capabilities": [
                "Configure connectors",
                "Validate configurations", 
                "Test connections",
                "Discover metadata",
                "Sync metadata to catalog"
            ],
            "tools": ["dq_connector"],
            "status": "available"
        },
        {
            "id": "dq_rule",
            "name": "Rule Engineer Agent",
            "description": "Extract, validate, and manage data quality rules from natural language",
            "capabilities": [
                "Extract rules from NL",
                "Validate rule configurations",
                "Create and update rules",
                "Assign rules to metadata",
                "Execute rules"
            ],
            "tools": ["dq_rule"],
            "status": "available"
        },
        {
            "id": "dq_steward",
            "name": "Data Steward Agent",
            "description": "Generate data definitions, manage glossary entries, and ensure data governance",
            "capabilities": [
                "Generate data definitions",
                "Create glossary entries",
                "Query metadata catalog",
                "Validate definitions"
            ],
            "tools": ["dq_definition"],
            "status": "available"
        },
        {
            "id": "general",
            "name": "General DQ Assistant",
            "description": "General-purpose DQ assistant for all data quality tasks",
            "capabilities": [
                "Answer DQ questions",
                "Route to specialized agents",
                "Provide best practices"
            ],
            "tools": ["dq_connector", "dq_rule", "dq_definition"],
            "status": "available"
        }
    ]


@agent_router.get("/agents/{agent_type}/capabilities", response_model=Dict[str, Any], summary="Get agent capabilities")
async def get_agent_capabilities(agent_type: str):
    """
    Get detailed capabilities and tools for a specific agent type.
    
    Args:
        agent_type: ID of the agent type
        
    Returns:
        Dictionary with agent capabilities, tools, and configuration
    """
    factory = _get_agent_factory()
    
    # Validate agent type
    if agent_type not in ["dq_connector", "dq_rule", "dq_steward", "general"]:
        raise HTTPException(status_code=404, detail=f"Unknown agent type: {agent_type}")
    
    # Return capabilities based on agent type
    if agent_type == "dq_connector":
        return {
            "agent_type": "dq_connector",
            "name": "Connector Onboarding Agent",
            "description": "Specialized agent for data source connector onboarding",
            "version": "1.0.0",
            "tools": [
                {
                    "name": "dq_connector",
                    "description": "Data Source Connector Management Tool",
                    "functions": [
                        "configure", "validate", "test_connection", 
                        "discover", "sync", "get_sync_status", 
                        "health", "list", "get", "update", "delete"
                    ]
                }
            ],
            "supported_connectors": ["postgresql", "sqlserver", "adls", "s3", "blob", "api"],
            "features": ["secure_credentials", "metadata_discovery", "sync_monitoring"]
        }
    elif agent_type == "dq_rule":
        return {
            "agent_type": "dq_rule",
            "name": "Rule Engineer Agent", 
            "description": "Specialized agent for DQ rule management",
            "version": "1.0.0",
            "tools": [
                {
                    "name": "dq_rule",
                    "description": "Data Quality Rule Management Tool",
                    "functions": [
                        "extract", "validate", "create", "get", "update", 
                        "delete", "list", "assign", "unassign", "execute"
                    ]
                }
            ],
            "supported_rule_types": [
                "NOT_NULL", "UNIQUE", "PATTERN", "RANGE", "IN_SET",
                "REFERENTIAL_INTEGRITY", "CUSTOM_SQL", "ACCURACY", "CONSISTENCY"
            ],
            "features": ["natural_language_extraction", "rule_validation", "execution"]
        }
    elif agent_type == "dq_steward":
        return {
            "agent_type": "dq_steward",
            "name": "Data Steward Agent",
            "description": "Specialized agent for data definition and governance",
            "version": "1.0.0",
            "tools": [
                {
                    "name": "dq_definition",
                    "description": "Data Definition and Glossary Management Tool",
                    "functions": [
                        "generate", "create_glossary_entry", "update_glossary_entry",
                        "query_metadata", "search_definitions", "get_definition"
                    ]
                }
            ],
            "features": ["definition_generation", "glossary_management", "metadata_query"]
        }
    else:
        return {
            "agent_type": "general",
            "name": "General DQ Assistant",
            "description": "General-purpose DQ assistant",
            "version": "1.0.0",
            "tools": [
                {"name": "dq_connector"},
                {"name": "dq_rule"},
                {"name": "dq_definition"}
            ],
            "features": ["general_knowledge", "agent_routing", "best_practices"]
        }


@agent_router.get("/health", response_model=AgentHealthResponse, summary="Agent health check")
async def check_agent_health():
    """
    Check the health of the agent harness service.
    
    Returns:
        Health status including available agents and metrics
    """
    return AgentHealthResponse(
        status=True,
        agents_available=["dq_connector", "dq_rule", "dq_steward", "general"],
        active_sessions=_agent_sessions_active,
        total_requests=_agent_sessions_total
    )


# Include the agent router in the main app
app.include_router(agent_router)


# ============================================================================
# End of Agent Harness API Endpoints
# ============================================================================


def _mark_request_started(endpoint: str) -> None:
    global _llm_requests_in_flight
    global _llm_extract_rules_in_flight
    global _llm_generate_definitions_in_flight
    global _llm_extract_rules_requests_total
    global _llm_generate_definitions_requests_total

    with _metrics_lock:
        _llm_requests_in_flight += 1
        if endpoint == "extract_rules":
            _llm_extract_rules_in_flight += 1
            _llm_extract_rules_requests_total += 1
        elif endpoint == "generate_data_definitions":
            _llm_generate_definitions_in_flight += 1
            _llm_generate_definitions_requests_total += 1


def _mark_request_failed(endpoint: str) -> None:
    global _llm_extract_rules_failures_total
    global _llm_generate_definitions_failures_total

    with _metrics_lock:
        if endpoint == "extract_rules":
            _llm_extract_rules_failures_total += 1
        elif endpoint == "generate_data_definitions":
            _llm_generate_definitions_failures_total += 1


def _mark_request_finished(endpoint: str) -> None:
    global _llm_requests_in_flight
    global _llm_extract_rules_in_flight
    global _llm_generate_definitions_in_flight

    with _metrics_lock:
        _llm_requests_in_flight = max(0, _llm_requests_in_flight - 1)
        if endpoint == "extract_rules":
            _llm_extract_rules_in_flight = max(0, _llm_extract_rules_in_flight - 1)
        elif endpoint == "generate_data_definitions":
            _llm_generate_definitions_in_flight = max(0, _llm_generate_definitions_in_flight - 1)


def _render_prometheus_metrics() -> str:
    with _metrics_lock:
        lines = [
            "# HELP dq_llm_requests_in_flight Number of dq-llm requests currently being processed.",
            "# TYPE dq_llm_requests_in_flight gauge",
            f"dq_llm_requests_in_flight {_llm_requests_in_flight}",
            "# HELP dq_llm_extract_rules_in_flight Number of extract_rules requests currently being processed.",
            "# TYPE dq_llm_extract_rules_in_flight gauge",
            f"dq_llm_extract_rules_in_flight {_llm_extract_rules_in_flight}",
            "# HELP dq_llm_generate_data_definitions_in_flight Number of generate_data_definitions requests currently being processed.",
            "# TYPE dq_llm_generate_data_definitions_in_flight gauge",
            f"dq_llm_generate_data_definitions_in_flight {_llm_generate_definitions_in_flight}",
            "# HELP dq_llm_extract_rules_requests_total Total extract_rules requests.",
            "# TYPE dq_llm_extract_rules_requests_total counter",
            f"dq_llm_extract_rules_requests_total {_llm_extract_rules_requests_total}",
            "# HELP dq_llm_extract_rules_failures_total Total failed extract_rules requests.",
            "# TYPE dq_llm_extract_rules_failures_total counter",
            f"dq_llm_extract_rules_failures_total {_llm_extract_rules_failures_total}",
            "# HELP dq_llm_generate_data_definitions_requests_total Total generate_data_definitions requests.",
            "# TYPE dq_llm_generate_data_definitions_requests_total counter",
            f"dq_llm_generate_data_definitions_requests_total {_llm_generate_definitions_requests_total}",
            "# HELP dq_llm_generate_data_definitions_failures_total Total failed generate_data_definitions requests.",
            "# TYPE dq_llm_generate_data_definitions_failures_total counter",
            f"dq_llm_generate_data_definitions_failures_total {_llm_generate_definitions_failures_total}",
            "",
            # Agent Harness Metrics (LLM-1.17)
            "# HELP dq_agent_sessions_active Number of active agent sessions.",
            "# TYPE dq_agent_sessions_active gauge",
            f"dq_agent_sessions_active {_agent_sessions_active}",
            "# HELP dq_agent_sessions_total Total agent sessions created.",
            "# TYPE dq_agent_sessions_total counter",
            f"dq_agent_sessions_total {_agent_sessions_total}",
            "# HELP dq_agent_tool_calls_total Total tool invocations by agents.",
            "# TYPE dq_agent_tool_calls_total counter",
            f"dq_agent_tool_calls_total {_agent_tool_calls_total}",
            "# HELP dq_agent_tool_errors_total Total tool execution errors by agents.",
            "# TYPE dq_agent_tool_errors_total counter",
            f"dq_agent_tool_errors_total {_agent_tool_errors_total}",
            "# HELP dq_agent_latency_seconds_total Total latency of agent operations in seconds.",
            "# TYPE dq_agent_latency_seconds_total counter",
            f"dq_agent_latency_seconds_total {_agent_latency_seconds_total}",
        ]
        
        # Add tool calls by type metrics
        for tool_type, count in _agent_tool_calls_by_type.items():
            lines.append(f"# HELP dq_agent_tool_calls_total{{type=\"{tool_type}\"}} Total tool invocations of type {tool_type}.")
            lines.append(f"# TYPE dq_agent_tool_calls_total{{type=\"{tool_type}\"}} counter")
            lines.append(f"dq_agent_tool_calls_total{{type=\"{tool_type}\"}} {count}")
        
        lines.append("")
    return "\n".join(lines)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HuggingFaceChatClient:
    def __init__(self, *, model_id: str, device_map: str, max_new_tokens: int, load_in_4bit: bool = False) -> None:
        self._model_id = model_id
        self._device_map = device_map
        self._max_new_tokens = max_new_tokens
        self._load_in_4bit = load_in_4bit
        self._tokenizer = None
        self._model = None
        self._generation_config = None

    def _ensure_loaded(self) -> None:
        if self._tokenizer is not None and self._model is not None:
            return

        try:
            transformers = importlib.import_module("transformers")
        except ImportError as exc:
            raise LLMServiceUnavailableError(
                "transformers is required for DQ_LLM_CHAT_PROVIDER=huggingface but is not installed in this runtime."
            ) from exc
        AutoModelForCausalLM = transformers.AutoModelForCausalLM
        AutoTokenizer = transformers.AutoTokenizer
        GenerationConfig = transformers.GenerationConfig

        from_pretrained_kwargs: dict[str, Any] = {
            "device_map": self._device_map,
            "resume_download": True,
        }
        if self._load_in_4bit:
            try:
                torch = importlib.import_module("torch")
                BitsAndBytesConfig = transformers.BitsAndBytesConfig
            except (ImportError, AttributeError) as exc:
                raise LLMServiceUnavailableError(
                    "4-bit quantization requires torch and bitsandbytes; one or both are unavailable."
                ) from exc
            from_pretrained_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
            logger.info(
                "Loading Hugging Face model=%s device_map=%s with 4-bit NF4 quantization",
                self._model_id,
                self._device_map,
            )
        else:
            logger.info("Loading Hugging Face model=%s device_map=%s", self._model_id, self._device_map)

        self._generation_config = GenerationConfig(max_new_tokens=self._max_new_tokens)
        self._tokenizer = AutoTokenizer.from_pretrained(self._model_id)
        self._model = AutoModelForCausalLM.from_pretrained(self._model_id, **from_pretrained_kwargs)
        logger.info("Hugging Face model loaded successfully.")

    def generate(self, prompt: str, *, max_new_tokens: int | None = None) -> str:
        self._ensure_loaded()
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._generation_config is not None

        chat_template = getattr(self._tokenizer, "apply_chat_template", None)
        if callable(chat_template):
            prompt_text = chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            prompt_text = prompt

        encoding = self._tokenizer(
            prompt_text,
            return_tensors="pt",
            return_attention_mask=True,
        )
        input_ids = encoding.input_ids.to(self._model.device)
        attention_mask = encoding.attention_mask.to(self._model.device)
        generation_kwargs: dict[str, Any] = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        if max_new_tokens is None:
            generation_kwargs["generation_config"] = self._generation_config
        else:
            generation_kwargs["max_new_tokens"] = max_new_tokens

        generated = self._model.generate(**generation_kwargs)
        return self._tokenizer.decode(
            generated[:, input_ids.shape[1] :][0],
            skip_special_tokens=True,
        )


class LlamaCppChatClient:
    """Inference provider backed by llama-cpp-python (GGUF model files).

    Requires DQ_LLM_LLAMA_CPP_MODEL_PATH to point to a local GGUF file.
    Optional env vars:
        DQ_LLM_LLAMA_CPP_N_CTX  — context window size (default: 4096)
        DQ_LLM_LLAMA_CPP_N_GPU_LAYERS — layers offloaded to GPU (default: 0)
    """

    def __init__(self, *, model_path: str, n_ctx: int, n_gpu_layers: int, max_new_tokens: int) -> None:
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._max_new_tokens = max_new_tokens
        self._model = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            llama_cpp = importlib.import_module("llama_cpp")
        except ImportError as exc:
            raise LLMServiceUnavailableError(
                "llama-cpp-python is required for DQ_LLM_CHAT_PROVIDER=llama_cpp but is not installed in this runtime."
            ) from exc
        logger.info(
            "Loading llama.cpp GGUF model path=%s n_ctx=%d n_gpu_layers=%d",
            self._model_path,
            self._n_ctx,
            self._n_gpu_layers,
        )
        self._model = llama_cpp.Llama(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            n_gpu_layers=self._n_gpu_layers,
            verbose=False,
        )
        logger.info("llama.cpp model loaded successfully.")

    def generate(self, prompt: str, *, max_new_tokens: int | None = None) -> str:
        self._ensure_loaded()
        assert self._model is not None
        response = self._model.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_new_tokens or self._max_new_tokens,
        )
        content = str((response["choices"][0]["message"].get("content") or "")).strip()
        if not content:
            raise LLMServiceResponseError("llama.cpp returned an empty response payload.")
        return content


class OllamaChatClient:
    def __init__(self, *, base_url: str, model: str, timeout_seconds: int, max_new_tokens: int) -> None:
        if not base_url:
            raise LLMServiceUnavailableError(
                "DQ_LLM_OLLAMA_BASE_URL must be configured when DQ_LLM_CHAT_PROVIDER=ollama."
            )
        if not model:
            raise LLMServiceUnavailableError(
                "DQ_LLM_OLLAMA_MODEL must be configured when DQ_LLM_CHAT_PROVIDER=ollama."
            )

        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_new_tokens = max_new_tokens

    def generate(self, prompt: str, *, max_new_tokens: int | None = None) -> str:
        body = json.dumps(
            {
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": max_new_tokens or self._max_new_tokens},
            }
        ).encode("utf-8")
        http_request = urllib_request.Request(
            f"{self._base_url}/api/generate",
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )

        try:
            with urllib_request.urlopen(http_request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise LLMServiceResponseError(
                f"Ollama returned HTTP {exc.code}: {body_text[:400]}"
            ) from exc
        except urllib_error.URLError as exc:
            raise LLMServiceUnavailableError(
                f"Failed to reach Ollama at {self._base_url}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise LLMServiceResponseError("Ollama returned a non-JSON response.") from exc

        response_text = str(payload.get("response") or "").strip()
        if not response_text:
            raise LLMServiceResponseError("Ollama returned an empty response payload.")
        return response_text


@lru_cache(maxsize=1)
def get_chat_client() -> Any:
    provider = os.getenv("DQ_LLM_CHAT_PROVIDER", CHAT_PROVIDER).strip().lower() or "huggingface"
    if provider == "ollama":
        return OllamaChatClient(
            base_url=os.getenv("DQ_LLM_OLLAMA_BASE_URL", OLLAMA_BASE_URL).strip().rstrip("/"),
            model=os.getenv("DQ_LLM_OLLAMA_MODEL", OLLAMA_MODEL).strip(),
            timeout_seconds=int(os.getenv("DQ_LLM_OLLAMA_TIMEOUT_SECONDS", str(OLLAMA_TIMEOUT_SECONDS))),
            max_new_tokens=int(os.getenv("DQ_LLM_MAX_NEW_TOKENS", str(MAX_NEW_TOKENS))),
        )
    if provider == "llama_cpp":
        model_path = os.getenv("DQ_LLM_LLAMA_CPP_MODEL_PATH", "").strip()
        if not model_path:
            raise LLMServiceUnavailableError(
                "DQ_LLM_LLAMA_CPP_MODEL_PATH must be set when DQ_LLM_CHAT_PROVIDER=llama_cpp."
            )
        return LlamaCppChatClient(
            model_path=model_path,
            n_ctx=int(os.getenv("DQ_LLM_LLAMA_CPP_N_CTX", "4096")),
            n_gpu_layers=int(os.getenv("DQ_LLM_LLAMA_CPP_N_GPU_LAYERS", "0")),
            max_new_tokens=int(os.getenv("DQ_LLM_MAX_NEW_TOKENS", str(MAX_NEW_TOKENS))),
        )
    if provider != "huggingface":
        raise LLMServiceUnavailableError(f"Unsupported DQ_LLM_CHAT_PROVIDER '{provider}'.")
    # Use smaller model if requested
    effective_model_id = os.getenv("DQ_LLM_SMALL_MODEL_ID", SMALL_MODEL_ID)
    model_id = effective_model_id if effective_model_id else os.getenv("DQ_LLM_MODEL_ID", MODEL_ID)
    return HuggingFaceChatClient(
        model_id=model_id,
        device_map=os.getenv("DQ_LLM_DEVICE_MAP", DEVICE_MAP),
        max_new_tokens=int(os.getenv("DQ_LLM_MAX_NEW_TOKENS", str(MAX_NEW_TOKENS))),
        load_in_4bit=os.getenv("DQ_LLM_LOAD_IN_4BIT", str(LOAD_IN_4BIT)).strip().lower() in ("1", "true"),
    )


@lru_cache(maxsize=8)
def _load_prompt_template(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _render_simple_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{ {key} }}}}", value)
    return rendered


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return normalized.strip("_") or "unknown"


def _titleize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("_", " ").strip()).title()


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _data_definition_max_new_tokens(target_count: int) -> int:
    if target_count <= 0:
        return MAX_NEW_TOKENS
    return max(MAX_NEW_TOKENS, 2048, target_count * 512)


def _extract_json_text(raw_text: str) -> str:
    stripped = str(raw_text or "").strip()
    if not stripped:
        raise LLMServiceResponseError("LLM returned an empty response.")

    def balanced_json_text(value: str, start_index: int) -> str:
        opening = value[start_index]
        closing = "}" if opening == "{" else "]"
        pairs = {"{": "}", "[": "]"}
        stack = [closing]
        in_string = False
        escaped = False

        for index in range(start_index + 1, len(value)):
            character = value[index]
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
                continue

            if character == '"':
                in_string = True
                continue
            if character in pairs:
                stack.append(pairs[character])
                continue
            if stack and character == stack[-1]:
                stack.pop()
                if not stack:
                    return value[start_index : index + 1]

        return value[start_index:]

    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, re.DOTALL)
    if fenced_match:
        fenced_text = fenced_match.group(1).strip()
        fenced_object_start = fenced_text.find("{")
        fenced_array_start = fenced_text.find("[")
        if fenced_object_start == -1 and fenced_array_start == -1:
            return fenced_text
        if fenced_object_start == -1:
            return balanced_json_text(fenced_text, fenced_array_start).strip()
        if fenced_array_start == -1:
            return balanced_json_text(fenced_text, fenced_object_start).strip()
        return balanced_json_text(fenced_text, min(fenced_object_start, fenced_array_start)).strip()

    json_object_start = stripped.find("{")
    json_array_start = stripped.find("[")
    if json_object_start == -1 and json_array_start == -1:
        return stripped

    if json_object_start == -1:
        return balanced_json_text(stripped, json_array_start).strip()
    if json_array_start == -1:
        return balanced_json_text(stripped, json_object_start).strip()
    return balanced_json_text(stripped, min(json_object_start, json_array_start)).strip()


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    json_text = _extract_json_text(raw_text)
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "LLM returned invalid JSON: message=%s position=%s excerpt=%r",
            exc.msg,
            exc.pos,
            json_text[:1000],
        )
        raise LLMServiceResponseError("LLM returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise LLMServiceResponseError("LLM response must be a JSON object.")
    return payload


def _normalize_rule_output(raw_text: str) -> list[str] | str:
    stripped = str(raw_text or "").strip()
    if not stripped:
        raise LLMServiceResponseError("LLM returned an empty rules payload.")
    try:
        parsed = json.loads(_extract_json_text(stripped))
    except (json.JSONDecodeError, LLMServiceResponseError):
        return stripped

    if isinstance(parsed, list):
        normalized_rules = [str(item).strip() for item in parsed if str(item).strip()]
        if not normalized_rules:
            raise LLMServiceResponseError("LLM returned an empty rules list.")
        return normalized_rules
    return stripped


def _normalize_target(target: DefinitionTarget) -> dict[str, Any]:
    data_set_slug = _slugify(target.data_set_name)
    data_object_slug = _slugify(target.data_object_name)
    attribute_slug = _slugify(target.attribute_name)
    normalized_target_id = _clean_string(target.target_id) or f"attr.{data_set_slug}.{data_object_slug}.{attribute_slug}"
    return {
        "target_id": normalized_target_id,
        "data_set_name": target.data_set_name,
        "data_set_slug": data_set_slug,
        "data_object_name": target.data_object_name,
        "data_object_slug": data_object_slug,
        "attribute_name": target.attribute_name,
        "attribute_slug": attribute_slug,
        "display_name": _clean_string(target.display_name) or _titleize(target.attribute_name),
        "data_type": _clean_string(target.data_type),
        "nullable": target.nullable,
        "description": _clean_string(target.description),
        "logical_path": _clean_string(target.logical_path),
        "source_system": _clean_string(target.source_system),
        "steward_notes": _clean_string(target.steward_notes),
        "sample_values": _coerce_string_list(target.sample_values),
        "metadata": dict(target.metadata or {}),
    }


def _derive_review_status(request_model: DataDefinitionRequest) -> str:
    approval_status = _slugify(request_model.board_approval.status) if request_model.board_approval else "pending"
    if approval_status == "approved":
        return "approved"

    feedback_roles = {_slugify(item.source_role) for item in request_model.feedback_items}
    if "data_definition_board" in feedback_roles:
        return "board_feedback_incorporated"
    if "data_steward" in feedback_roles:
        return "steward_feedback_incorporated"
    return "pending_board_review"


def _derive_definition_status(review_status: str) -> str:
    if review_status == "approved":
        return "approved"
    if review_status in {"board_feedback_incorporated", "steward_feedback_incorporated"}:
        return "reviewed"
    return "draft"


def _derive_representation_term(attribute_name: str, data_type: str, provided_value: str) -> str:
    explicit = _clean_string(provided_value)
    if explicit:
        return explicit
    lowered_name = _clean_string(attribute_name).lower()
    lowered_type = _clean_string(data_type).lower()
    if "date" in lowered_name or "time" in lowered_name or "date" in lowered_type or "time" in lowered_type:
        return "timestamp"
    if any(token in lowered_name for token in ("id", "identifier", "key")):
        return "identifier"
    if any(token in lowered_name for token in ("amount", "balance", "exposure", "value", "price")):
        return "amount"
    if "code" in lowered_name:
        return "code"
    return "attribute"


def _build_context_payload(request_model: DataDefinitionRequest, normalized_targets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "task_id": request_model.task_id,
        "steward_name": request_model.steward_name,
        "board_name": request_model.board_name,
        "domain_name": request_model.domain_name,
        "source_system": request_model.source_system,
        "user_input": request_model.user_input,
        "policies": request_model.policies,
        "targets": normalized_targets,
        "context_documents": [item.model_dump(mode="json") for item in request_model.context_documents],
        "feedback_items": [item.model_dump(mode="json") for item in request_model.feedback_items],
        "board_approval": request_model.board_approval.model_dump(mode="json") if request_model.board_approval else None,
    }


def _build_generation_prompt(request_model: DataDefinitionRequest, normalized_targets: list[dict[str, Any]]) -> str:
    context_payload = _build_context_payload(request_model, normalized_targets)
    instructions = {
        "objective": (
            "Draft governed, board-review-ready data definitions aligned to ISO 11179 and BCBS 239. "
            "Use metadata, policies, logical-model context, templates, norms-and-forms, steward input, and any profiling context."
        ),
        "requirements": [
            "Return JSON only.",
            "Produce exactly one definition object per draft_key supplied in the request.",
            "Copy each draft_key exactly as supplied; draft_key values are opaque identifiers for matching drafts to targets.",
            "Do not invent technical context that is not supported by the input.",
            "If context is incomplete, keep the draft reviewable and record the gap in open_questions.",
            "Write business definitions for review by a Data Definition Board.",
            "Apply Guidelines for Definitions of Business Terms v1.0: business_definition must start with 'A' or 'An', express the essence of the term, avoid circular wording, avoid embedded business rules, and avoid purpose/function language such as 'used for'.",
            "Support one entry per concept using the supplied draft_key; do not combine multiple business concepts into one definition.",
            "Make homonym context explicit by tying the definition to its primary domain, data object, attribute, and logical path.",
            "Preserve source references, definition owner, primary domain, and governing policy linkage for board approval evidence.",
            "Reflect BCBS 239 themes: traceability, accuracy, completeness, timeliness, governance, and auditability.",
        ],
        "response_schema": {
            "definitions": [
                {
                    "draft_key": "string",
                    "definition_name": "string",
                    "business_definition": "string",
                    "synonyms": ["string"],
                    "representation_term": "string",
                    "value_domain": {
                        "data_type": "string",
                        "nullable": "boolean",
                        "format": "string",
                        "allowed_values": ["string"],
                        "unit": "string",
                    },
                    "examples": ["string"],
                    "constraints": ["string"],
                    "open_questions": ["string"],
                    "board_notes": "string",
                }
            ],
            "board_review_summary": "string",
            "approval_criteria": ["string"],
        },
    }
    return (
        "You are the dq-made-easy data-definition drafting agent.\n\n"
        f"Instructions:\n{json.dumps(instructions, indent=2, sort_keys=True)}\n\n"
        f"Context:\n{json.dumps(context_payload, indent=2, sort_keys=True)}\n"
    )


def _build_feedback_prompt(
    request_model: DataDefinitionRequest,
    normalized_targets: list[dict[str, Any]],
    prior_payload: dict[str, Any],
) -> str:
    feedback_payload = {
        "task_id": request_model.task_id,
        "board_name": request_model.board_name,
        "feedback_items": [item.model_dump(mode="json") for item in request_model.feedback_items],
        "board_approval": request_model.board_approval.model_dump(mode="json") if request_model.board_approval else None,
        "targets": normalized_targets,
        "prior_draft": prior_payload,
    }
    return (
        "Revise the existing data-definition draft. Return JSON only. "
        "Incorporate steward and board feedback, preserve unresolved gaps in open_questions, "
        "and keep exactly one definition object per target_id.\n\n"
        f"Feedback context:\n{json.dumps(feedback_payload, indent=2, sort_keys=True)}\n"
    )


def _relevant_feedback_items(request_model: DataDefinitionRequest, target_id: str) -> list[ReviewFeedback]:
    relevant_items: list[ReviewFeedback] = []
    for item in request_model.feedback_items:
        if not item.target_ids or target_id in item.target_ids:
            relevant_items.append(item)
    return relevant_items


def _request_model_for_target(
    request_model: DataDefinitionRequest,
    target: dict[str, Any],
) -> DataDefinitionRequest:
    return request_model.model_copy(
        update={
            "targets": [DefinitionTarget.model_validate(target)],
            "feedback_items": _relevant_feedback_items(request_model, target["target_id"]),
        }
    )


def _generate_draft_payload_for_target(
    request_model: DataDefinitionRequest,
    target: dict[str, Any],
    chat_client: Any,
    *,
    max_new_tokens: int,
) -> dict[str, Any]:
    target_request_model = _request_model_for_target(request_model, target)

    last_exc: LLMServiceResponseError | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            target_payload = _parse_json_object(
                chat_client.generate(
                    _build_generation_prompt(target_request_model, [target]),
                    max_new_tokens=max_new_tokens,
                )
            )
        except LLMServiceResponseError as exc:
            last_exc = exc
            logger.warning(
                "Draft generation attempt %d/%d failed for target %s: %s",
                attempt,
                MAX_RETRIES,
                target.get("target_id", "?"),
                exc,
            )
            continue
        break
    else:
        raise last_exc  # type: ignore[misc]

    if target_request_model.feedback_items:
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                target_payload = _parse_json_object(
                    chat_client.generate(
                        _build_feedback_prompt(target_request_model, [target], target_payload),
                        max_new_tokens=max_new_tokens,
                    )
                )
            except LLMServiceResponseError as exc:
                last_exc = exc
                logger.warning(
                    "Feedback revision attempt %d/%d failed for target %s: %s",
                    attempt,
                    MAX_RETRIES,
                    target.get("target_id", "?"),
                    exc,
                )
                continue
            break
        else:
            raise last_exc  # type: ignore[misc]

    return target_payload


def _validate_draft_payload(payload: dict[str, Any], normalized_targets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    raw_definitions = payload.get("definitions")
    if not isinstance(raw_definitions, list) or not raw_definitions:
        raise LLMServiceResponseError("Data-definition draft must include a non-empty definitions list.")

    expected_draft_keys = {target["draft_key"] for target in normalized_targets}
    definitions_missing_draft_key = [
        definition
        for definition in raw_definitions
        if isinstance(definition, dict) and not _clean_string(definition.get("draft_key"))
    ]
    if len(definitions_missing_draft_key) == len(raw_definitions) == len(normalized_targets):
        for definition, target in zip(raw_definitions, normalized_targets, strict=False):
            if isinstance(definition, dict):
                definition["draft_key"] = target["draft_key"]

    draft_by_draft_key: dict[str, dict[str, Any]] = {}
    for definition in raw_definitions:
        if not isinstance(definition, dict):
            raise LLMServiceResponseError("Each drafted definition must be a JSON object.")
        draft_key = _clean_string(definition.get("draft_key"))
        if not draft_key:
            raise LLMServiceResponseError("Each drafted definition must include draft_key.")
        if draft_key in draft_by_draft_key:
            raise LLMServiceResponseError(f"Drafted definitions contain duplicate draft_key '{draft_key}'.")
        draft_by_draft_key[draft_key] = definition

    missing_draft_keys = sorted(expected_draft_keys.difference(draft_by_draft_key))
    if missing_draft_keys:
        raise LLMServiceResponseError(
            f"Drafted definitions are missing required draft_keys: {', '.join(missing_draft_keys)}"
        )
    unexpected_draft_keys = sorted(set(draft_by_draft_key).difference(expected_draft_keys))
    if unexpected_draft_keys:
        raise LLMServiceResponseError(
            f"Drafted definitions contain unexpected draft_keys: {', '.join(unexpected_draft_keys)}"
        )
    return draft_by_draft_key


def _build_glossary_contract(request_model: DataDefinitionRequest) -> dict[str, str]:
    glossary_name = _clean_string(request_model.glossary_name)
    if not glossary_name:
        glossary_name = f"bcbs239_{_slugify(request_model.domain_name or request_model.board_name or 'definitions')}"
    glossary_display_name = _clean_string(request_model.glossary_display_name) or _titleize(glossary_name)
    glossary_description = (
        f"Generated data-definition draft bundle for task {request_model.task_id} "
        f"supporting steward review and {request_model.board_name}."
    )
    return {
        "name": glossary_name,
        "display_name": glossary_display_name,
        "description": glossary_description,
    }


def _build_openmetadata_term_payload(definition: dict[str, Any], glossary_name: str) -> dict[str, Any]:
    extension = {
        "concept_key": definition["concept_key"],
        "definition_id": definition["definition_id"],
        "definition_type": definition["definition_type"],
        "definition_name": definition["definition_name"],
        "primary_domain": definition["primary_domain"],
        "definition_owner": definition["definition_owner"],
        "object_class": definition["object_class"],
        "property": definition["property"],
        "representation_term": definition["representation_term"],
        "status": definition["status"],
        "owner": definition["owner"],
        "version": definition["version"],
        "source_system": definition["source_system"],
        "source_references": json.dumps(definition["source_references"], separators=(",", ":"), sort_keys=True),
        "policy_documents": json.dumps(definition["policy_documents"], separators=(",", ":"), sort_keys=True),
        "homonym_context": json.dumps(definition["homonym_context"], separators=(",", ":"), sort_keys=True),
        "value_domain": json.dumps(definition["value_domain"], separators=(",", ":"), sort_keys=True),
        "provenance": json.dumps(definition["provenance"], separators=(",", ":"), sort_keys=True),
        "applies_to": json.dumps(definition["applies_to"], separators=(",", ":"), sort_keys=True),
        "examples": json.dumps(definition["examples"], separators=(",", ":"), sort_keys=True),
        "constraints": json.dumps(definition["constraints"], separators=(",", ":"), sort_keys=True),
        "regulatory_tags": json.dumps(definition["regulatory_tags"], separators=(",", ":"), sort_keys=True),
        "board_review_status": definition["board_review_status"],
    }
    return {
        "name": definition["term_name"],
        "displayName": definition["display_name"],
        "description": definition["business_definition"],
        "glossary": glossary_name,
        "mutuallyExclusive": False,
        "extension": extension,
    }


def _merge_definition(
    request_model: DataDefinitionRequest,
    target: dict[str, Any],
    draft: dict[str, Any],
    review_status: str,
) -> dict[str, Any]:
    definition_id = f"def.attribute.{target['data_set_slug']}.{target['data_object_slug']}.{target['attribute_slug']}"
    definition_name = _clean_string(draft.get("definition_name")) or target["display_name"]
    business_definition = _clean_string(draft.get("business_definition")) or target["description"]
    if not business_definition:
        raise LLMServiceResponseError(
            f"Drafted definition for target_id '{target['target_id']}' is missing business_definition."
        )

    value_domain = draft.get("value_domain") if isinstance(draft.get("value_domain"), dict) else {}
    allowed_values = _coerce_string_list(value_domain.get("allowed_values"))
    constraints = _coerce_string_list(draft.get("constraints"))
    if target["nullable"] is False:
        constraints = [*constraints, "Value is required and cannot be null."]

    value_domain_payload = {
        "data_type": _clean_string(value_domain.get("data_type")) or target["data_type"],
        "nullable": target["nullable"],
        "format": _clean_string(value_domain.get("format")),
        "allowed_values": allowed_values,
        "unit": _clean_string(value_domain.get("unit")),
    }

    source_system = _clean_string(target["source_system"]) or _clean_string(request_model.source_system) or "dq-made-easy"
    primary_domain = _clean_string(request_model.domain_name)
    if not primary_domain:
        raise LLMServiceResponseError("Data-definition generation requires domain_name for primary_domain governance.")
    definition_owner = _clean_string(request_model.steward_name)
    if not definition_owner:
        raise LLMServiceResponseError("Data-definition generation requires steward_name for definition_owner governance.")
    logical_path = _clean_string(target["logical_path"]) or "/".join(
        [primary_domain, target["data_set_name"], target["data_object_name"], target["attribute_name"]]
    )

    source_references = [
        {
            "source_system": source_system,
            "data_set_name": target["data_set_name"],
            "data_object_name": target["data_object_name"],
            "attribute_name": target["attribute_name"],
            "logical_path": logical_path,
        }
    ]
    for document in request_model.context_documents:
        source_references.append(
            {
                "document_type": document.document_type,
                "name": document.name,
                "source_uri": _clean_string(document.source_uri),
            }
        )

    policy_documents = [dict(policy_document) for policy_document in DEFAULT_POLICY_DOCUMENTS]
    for policy in request_model.policies:
        policy_documents.append({"name": policy, "source": "data_definition_task"})

    homonym_context = {
        "primary_domain": primary_domain,
        "object_class": target["data_object_name"],
        "property": target["attribute_name"],
        "logical_path": logical_path,
    }
    provenance = {
        "generated_by": "dq-llm",
        "task_id": request_model.task_id,
        "steward_name": _clean_string(request_model.steward_name),
        "board_name": _clean_string(request_model.board_name),
        "primary_domain": primary_domain,
        "definition_owner": definition_owner,
        "source_references": source_references,
        "policy_documents": policy_documents,
        "homonym_context": homonym_context,
        "approval_status": _clean_string(request_model.board_approval.status) if request_model.board_approval else "pending",
        "approver_name": _clean_string(request_model.board_approval.approver_name) if request_model.board_approval else "",
        "approval_notes": _clean_string(request_model.board_approval.approval_notes) if request_model.board_approval else "",
        "feedback_ids": [
            _clean_string(item.feedback_id) or f"feedback_{index + 1}"
            for index, item in enumerate(request_model.feedback_items)
            if not item.target_ids or target["target_id"] in item.target_ids
        ],
    }

    return {
        "concept_key": definition_id,
        "definition_id": definition_id,
        "definition_type": "attribute",
        "definition_name": definition_name,
        "term_name": definition_id.replace(".", "_"),
        "display_name": definition_name,
        "business_definition": business_definition,
        "object_class": target["data_object_name"],
        "property": target["attribute_name"],
        "representation_term": _derive_representation_term(
            target["attribute_name"],
            target["data_type"],
            _clean_string(draft.get("representation_term")),
        ),
        "primary_domain": primary_domain,
        "definition_owner": definition_owner,
        "source_references": source_references,
        "policy_documents": policy_documents,
        "homonym_context": homonym_context,
        "value_domain": value_domain_payload,
        "status": _derive_definition_status(review_status),
        "owner": definition_owner,
        "source_system": source_system,
        "version": "v1",
        "provenance": provenance,
        "applies_to": [
            {
                "task_id": request_model.task_id,
                "target_id": target["target_id"],
                "data_set_name": target["data_set_name"],
                "data_object_name": target["data_object_name"],
                "attribute_name": target["attribute_name"],
                "logical_path": logical_path,
            }
        ],
        "synonyms": _coerce_string_list(draft.get("synonyms")),
        "examples": _coerce_string_list(draft.get("examples")) or target["sample_values"],
        "constraints": constraints,
        "sensitivity": _clean_string(target["metadata"].get("sensitivity")),
        "retention_class": _clean_string(target["metadata"].get("retention_class")),
        "regulatory_tags": ["bcbs239", *sorted({tag for tag in _coerce_string_list(target["metadata"].get("regulatory_tags"))})],
        "lineage_refs": _coerce_string_list(target["metadata"].get("lineage_refs")),
        "compatibility_notes": _clean_string(target["metadata"].get("compatibility_notes")),
        "board_review_status": review_status,
        "open_questions": _coerce_string_list(draft.get("open_questions")),
        "board_notes": _clean_string(draft.get("board_notes")),
        "target_id": target["target_id"],
    }


def generate_data_definitions_bundle(
    request_model: DataDefinitionRequest,
    chat_client: Any,
    *,
    provider_name: str,
    model_name: str,
) -> dict[str, Any]:
    if not request_model.targets:
        raise ValueError("At least one target is required to generate data definitions.")

    normalized_targets = [_normalize_target(target) for target in request_model.targets]
    for index, target in enumerate(normalized_targets, start=1):
        target["draft_key"] = f"target_{index}"
    max_new_tokens = _data_definition_max_new_tokens(len(normalized_targets))
    orchestration_trace = [
        {
            "step_id": "DD-STEP-001",
            "name": "collect_context",
            "status": "completed",
            "detail": f"Prepared {len(normalized_targets)} targets with {len(request_model.context_documents)} context documents.",
        }
    ]

    draft_payloads: list[dict[str, Any]] = []
    for target in normalized_targets:
        draft_payloads.append(
            _generate_draft_payload_for_target(
                request_model,
                target,
                chat_client,
                max_new_tokens=max_new_tokens,
            )
        )

    draft_payload = {
        "definitions": [
            definition
            for payload in draft_payloads
            for definition in payload.get("definitions", [])
            if isinstance(definition, dict)
        ],
        "board_review_summary": next(
            (
                _clean_string(payload.get("board_review_summary"))
                for payload in draft_payloads
                if _clean_string(payload.get("board_review_summary"))
            ),
            "",
        ),
        "approval_criteria": next(
            (
                _coerce_string_list(payload.get("approval_criteria"))
                for payload in draft_payloads
                if _coerce_string_list(payload.get("approval_criteria"))
            ),
            [],
        ),
    }
    orchestration_trace.append(
        {
            "step_id": "DD-STEP-002",
            "name": "draft_definitions",
            "status": "completed",
            "detail": f"Received draft responses for {len(normalized_targets)} targets in task {request_model.task_id}.",
        }
    )

    if request_model.feedback_items:
        orchestration_trace.append(
            {
                "step_id": "DD-STEP-003",
                "name": "incorporate_feedback",
                "status": "completed",
                "detail": f"Applied {len(request_model.feedback_items)} feedback items across {len(normalized_targets)} targets.",
            }
        )
    else:
        orchestration_trace.append(
            {
                "step_id": "DD-STEP-003",
                "name": "incorporate_feedback",
                "status": "skipped",
                "detail": "No steward or board feedback was supplied.",
            }
        )

    draft_by_draft_key = _validate_draft_payload(draft_payload, normalized_targets)
    review_status = _derive_review_status(request_model)
    glossary_contract = _build_glossary_contract(request_model)
    definitions = [
        _merge_definition(request_model, target, draft_by_draft_key[target["draft_key"]], review_status)
        for target in normalized_targets
    ]
    glossary_terms = [_build_openmetadata_term_payload(definition, glossary_contract["name"]) for definition in definitions]

    board_review_packet = {
        "board_name": _clean_string(request_model.board_approval.board_name)
        if request_model.board_approval and _clean_string(request_model.board_approval.board_name)
        else request_model.board_name,
        "review_status": review_status,
        "decision_required": review_status != "approved",
        "review_summary": _clean_string(draft_payload.get("board_review_summary"))
        or f"Review generated definitions for task {request_model.task_id} before approval.",
        "approval_criteria": _coerce_string_list(draft_payload.get("approval_criteria")) or list(DEFAULT_APPROVAL_CRITERIA),
        "open_questions": [
            {
                "definition_id": definition["definition_id"],
                "questions": definition["open_questions"],
            }
            for definition in definitions
            if definition["open_questions"]
        ],
        "approval": request_model.board_approval.model_dump(mode="json") if request_model.board_approval else None,
    }

    orchestration_trace.append(
        {
            "step_id": "DD-STEP-004",
            "name": "render_openmetadata_contract",
            "status": "completed",
            "detail": f"Rendered OpenMetadata import contract with {len(glossary_terms)} glossary term payloads.",
        }
    )

    return {
        "task_id": request_model.task_id,
        "provider": provider_name,
        "model_name": model_name,
        "review_status": review_status,
        "feedback_applied": [item.model_dump(mode="json") for item in request_model.feedback_items],
        "orchestration_trace": orchestration_trace,
        "registry_contract": {
            "glossary": glossary_contract,
            "definitions": definitions,
        },
        "openmetadata_import_contract": {
            "glossary": glossary_contract,
            "definitions_manifest": {
                "glossary": glossary_contract,
                "definitions": definitions,
            },
            "glossary_terms": glossary_terms,
        },
        "board_review_packet": board_review_packet,
    }


@app.post("/extract_rules")
async def extract_rules(request: TextRequest):
    _mark_request_started("extract_rules")
    prompt_template = _load_prompt_template(str(EXTRACT_RULES_PROMPT_PATH))
    prompt = _render_simple_template(prompt_template, {"text": request.text})
    try:
        rules = await run_in_threadpool(lambda: _normalize_rule_output(get_chat_client().generate(prompt)))
    except LLMServiceUnavailableError as exc:
        _mark_request_failed("extract_rules")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMServiceResponseError as exc:
        _mark_request_failed("extract_rules")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        _mark_request_finished("extract_rules")
    return {"rules": rules}


@app.post("/generate_data_definitions")
async def generate_data_definitions(request: DataDefinitionRequest):
    _mark_request_started("generate_data_definitions")
    client = get_chat_client()
    provider_name = os.getenv("DQ_LLM_CHAT_PROVIDER", CHAT_PROVIDER).strip().lower() or "huggingface"
    model_name = (
        os.getenv("DQ_LLM_OLLAMA_MODEL", OLLAMA_MODEL).strip()
        if provider_name == "ollama"
        else os.getenv("DQ_LLM_MODEL_ID", MODEL_ID)
    )
    try:
        return await run_in_threadpool(
            lambda: generate_data_definitions_bundle(
                request,
                client,
                provider_name=provider_name,
                model_name=model_name,
            )
        )
    except ValueError as exc:
        _mark_request_failed("generate_data_definitions")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMServiceUnavailableError as exc:
        _mark_request_failed("generate_data_definitions")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMServiceResponseError as exc:
        _mark_request_failed("generate_data_definitions")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        _mark_request_finished("generate_data_definitions")


@app.get("/health")
async def health():
    provider_name = os.getenv("DQ_LLM_CHAT_PROVIDER", CHAT_PROVIDER).strip().lower() or "huggingface"
    # Use smaller model if requested
    effective_model_id = os.getenv("DQ_LLM_SMALL_MODEL_ID", SMALL_MODEL_ID)
    if provider_name == "ollama":
        model_name = os.getenv("DQ_LLM_OLLAMA_MODEL", OLLAMA_MODEL).strip()
    elif effective_model_id:
        model_name = effective_model_id
    else:
        model_name = os.getenv("DQ_LLM_MODEL_ID", MODEL_ID)
    return {
        "status": "ok",
        "provider": provider_name,
        "model": model_name,
        "features": ["extract_rules", "generate_data_definitions", "agent_execution"],
        "in_flight_requests": {
            "total": _llm_requests_in_flight,
            "extract_rules": _llm_extract_rules_in_flight,
            "generate_data_definitions": _llm_generate_definitions_in_flight,
        },
        "agent_metrics": {
            "active_sessions": _agent_sessions_active,
            "total_sessions": _agent_sessions_total,
            "total_tool_calls": _agent_tool_calls_total,
            "tool_errors": _agent_tool_errors_total,
        },
    }


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=_render_prometheus_metrics(), media_type="text/plain; version=0.0.4")


if __name__ == "__main__":
    logger.info("Starting FastAPI server on 0.0.0.0:8000 with TLS...")
    uvicorn.run(
        "entrypoint:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_config=None,
        ssl_certfile=TLS_CERT_FILE,
        ssl_keyfile=TLS_KEY_FILE,
    )