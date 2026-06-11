# LLM-1 Pi Agent Harness Integration

**Status**: 🟢 Phase 1 Complete (Milestone A) | Phase 2 Ready

**Goal**: Enable agentic workflows for Data Quality RuleBuilder by integrating Pi (Pi-dev) as a pluggable agent harness for the LLM backend, allowing AI agents to orchestrate connector operations, rule extraction, and metadata management through natural language and tool-based interactions.

**Related Work**:
- [API-1 New Data Source Connectors](/docs/features/API_1_CONNECTORS/)
- [API-7 Real DQ Rule Execution](/docs/status/current/API_7_REAL_DQ_RULE_EXECUTION/)
- [AGENTIC_AI_ECOSYSTEM_FEATURES.md](/docs/features/AGENTIC_AI_ECOSYSTEM_FEATURES/)

---

## Overview

Pi (Pi-dev) is a minimal, provider-agnostic agent harness that transforms LLMs from simple autocomplete engines into interactive, tool-using agents. This integration enables DQ-RuleBuilder to leverage agentic workflows for:

- **Automated connector onboarding** (API-1.3 to API-1.6)
- **Natural language rule extraction** (API-7)
- **Metadata discovery and sync** (API-1.8, API-1.9)
- **Data definition generation** (existing dq-llm service)

The harness provides a deterministic software layer that orchestrates LLM interactions with tools, memory, and the environment, making it ideal for DQ-RuleBuilder's complex data governance workflows.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        DQ-RuleBuilder                            │
├─────────────────┬─────────────────┬─────────────────┬────────────┤
│  dq-ui          │  dq-api         │  dq-llm         │  dq-engine │
│  (React, nginx) │  (FastAPI)      │  (Pi Agent +    │  (Spark)   │
│                 │                 │   FastAPI)      │            │
└────────┬────────┴────────┬────────┴────────┬────────┴────────────┘
         │                 │                 │              │
         │ REST/GraphQL    │ REST            │ gRPC         │
         ▼                 ▼                 ▼              ▼
┌────────────────────────────────────────────────────────────────────┐
│                       Agent Harness Layer                          │
├────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ DQ Connector │  │ DQ Rules     │  │ DQ Definition & Glossary │  │
│  │ Tool         │  │ Tool         │  │ Tool                     │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Read/Write   │  │ Bash         │  │ Custom DQ Tools          │  │
│  │ Files        │  │ Execution    │  │ (from existing services) │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
         │                  │                   │              │
         ▼                  ▼                   ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Systems & Data Sources              │
│  PostgreSQL │ SQL Server │ Azure ADLS │ S3/Blob │ OpenMetadata  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Core Integration

### 1.1 Pi Agent Foundation

**Objective**: Establish Pi Agent Harness as a service within `dq-llm`.

- [x] Add `pi-agent` as a dependency in `dq-llm/requirements.txt`
- [x] Create `dq-llm/agents/` module structure
- [x] Implement base agent factory with DQ-specific configuration
- [x] Add environment variable configuration for Pi (model, device map, providers)

**Files**:
- `dq-llm/requirements.txt` - Added `pi-agent>=0.1.0`
- `dq-llm/agents/__init__.py` - Module initialization
- `dq-llm/agents/base.py` - Base DQ agent class
- `dq-llm/agents/config.py` - Configuration management

### 1.2 Agent Lifecycle Management

**Objective**: Manage agent sessions, state, and cleanup.

- [x] Implement session persistence for agent conversations
- [x] Add session cleanup and garbage collection
- [x] Create session ID generation and retrieval
- [x] Integrate with existing Prometheus metrics in `entrypoint.py`

**Acceptance Criteria**:
- [x] Agent sessions can be created, retrieved, and destroyed
- [x] Session state persists across API calls
- [x] Metrics track active sessions and request counts
- [x] Cleanup removes stale sessions after timeout

---

## Phase 2: DQ-Specific Tool Integration

### 2.1 Connector Tools (API-1 Alignment)

**Objective**: Create Pi-compatible tools for connector operations.

| Tool | Description | API-1 Reference |
|------|-------------|----------------|
| `dq_connector_configure` | Configure a new connector instance | API-1.1 |
| `dq_connector_validate` | Validate connector configuration | API-1.1 |
| `dq_connector_test` | Test connection to data source | API-1.8 |
| `dq_connector_discover` | Discover schemas, tables, columns | API-1.8 |
| `dq_connector_sync` | Trigger metadata sync job | API-1.9 |
| `dq_connector_health` | Check connector health status | API-1.1 |

**Implementation**:
```python
# dq-llm/agents/tools/connector_tools.py
from pi_agent import Tool
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class ConnectorConfig(BaseModel):
    connector_type: str  # postgresql, sqlserver, adls, s3
    name: str
    connection_string: Optional[str] = None
    credentials: Optional[Dict[str, str]] = None
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)

class ConnectorTool(Tool):
    name = "dq_connector"
    description = "Interact with DQ connector framework"
    
    def __init__(self, api_base_url: str, api_key: str):
        self.client = DQAPIClient(api_base_url, api_key)
    
    async def configure(self, config: ConnectorConfig) -> Dict[str, Any]:
        """Configure a new connector."""
        return await self.client.post("/api/v1/connectors", json=config.dict())
    
    async def test_connection(self, connector_id: str) -> Dict[str, Any]:
        """Test connection to a configured connector."""
        return await self.client.post(f"/api/v1/connectors/{connector_id}/test")
    
    async def discover(self, connector_id: str) -> Dict[str, Any]:
        """Discover metadata from a connector."""
        return await self.client.post(f"/api/v1/connectors/{connector_id}/discover")
    
    async def sync(self, connector_id: str) -> Dict[str, Any]:
        """Trigger metadata sync for a connector."""
        return await self.client.post(f"/api/v1/connectors/{connector_id}/sync")
```

### 2.2 Rule Management Tools

**Objective**: Create tools for DQ rule operations.

| Tool | Description | API-7 Reference |
|------|-------------|-----------------|
| `dq_rule_extract` | Extract rules from natural language | API-7 |
| `dq_rule_validate` | Validate rule configuration | API-7 |
| `dq_rule_create` | Create a new rule | API-7 |
| `dq_rule_assign` | Assign rule to metadata attributes | API-7 |
| `dq_rule_execute` | Execute rule and return results | API-7 |

**Implementation**:
```python
# dq-llm/agents/tools/rule_tools.py
class RuleTool(Tool):
    name = "dq_rule"
    description = "Manage data quality rules"
    
    async def extract(self, natural_language: str, context: Optional[Dict] = None) -> List[Dict]:
        """Extract DQ rules from natural language description."""
        pass
    
    async def validate(self, rule_config: Dict) -> Dict:
        """Validate a rule configuration against schema."""
        pass
```

### 2.3 Metadata & Definition Tools

**Objective**: Integrate with existing dq-llm definition generation.

| Tool | Description | Existing Endpoint |
|------|-------------|------------------|
| `dq_definition_generate` | Generate data definitions | `/api/llm/v1/generate_data_definitions` |
| `dq_glossary_create` | Create glossary entries | `/api/llm/v1/glossary` |
| `dq_metadata_query` | Query metadata catalog | `/api/v1/metadata` |

---

## Phase 3: Specialized Agents

### 3.1 Connector Onboarding Agent

**Purpose**: Automate Phase 2 MVP Connectors workflow (API-1.3 to API-1.6).

**Capabilities**:
- Guide users through connector configuration
- Validate configurations before testing
- Execute test connections
- Discover and catalog metadata
- Trigger and monitor sync jobs
- Handle connection failures with actionable diagnostics

**System Prompt**:
```
You are a Data Connector Specialist for DQ-RuleBuilder.
Your expertise: PostgreSQL, SQL Server, Azure ADLS, S3/Blob connectors.

Workflow:
1. Ask user for connector type and connection details
2. Validate the configuration
3. Test the connection
4. If successful, discover metadata (schemas, tables, columns)
5. Sync metadata to the DQ catalog
6. Report success or provide actionable error diagnostics

Secrets Handling:
- NEVER expose credentials in responses
- Use secure references for secrets
- Redact sensitive information from logs

Error Handling:
- Connection failures: return specific error type and remediation steps
- Schema errors: validate against expected patterns
- Auth failures: guide user to verify credentials
```

**Implementation**:
```python
# dq-llm/agents/specialized/connector_agent.py
from pi_agent import Agent
from ..tools.connector_tools import ConnectorTool

class ConnectorOnboardingAgent(Agent):
    def __init__(self, **kwargs):
        super().__init__(
            **kwargs,
            tools=[ConnectorTool(api_base_url=kwargs.get('api_base_url'), 
                                api_key=kwargs.get('api_key'))],
            system_prompt=self.SYSTEM_PROMPT
        )
    
    SYSTEM_PROMPT = """..."""
    
    async def onboard_connector(self, connector_type: str, user_input: str) -> Dict:
        """Complete end-to-end connector onboarding."""
        pass
```

### 3.2 Rule Engineer Agent

**Purpose**: Automate DQ rule creation and management (API-7).

**Capabilities**:
- Extract rules from natural language requirements
- Validate rule configurations
- Assign rules to specific metadata attributes
- Execute rules and analyze results
- Suggest rule improvements

**System Prompt**:
```
You are a Data Quality Rule Engineer for DQ-RuleBuilder.
Your expertise: data quality validation, business rule extraction, metadata assignment.

Workflow:
1. Accept natural language requirements or structured specifications
2. Extract potential DQ rules (completeness, uniqueness, validity, consistency, accuracy)
3. Validate extracted rules against schema
4. Assign rules to appropriate metadata attributes from connectors
5. Execute rules and return results with explanations
6. Iterate based on user feedback

Rule Types to Consider:
- NOT_NULL (completeness)
- UNIQUE (uniqueness)
- PATTERN (format validity)
- RANGE (value range)
- REFERENTIAL_INTEGRITY (foreign key)
- CUSTOM_SQL (custom validation)
```

### 3.3 Data Steward Agent

**Purpose**: Assist with data definition and governance.

**Capabilities**:
- Generate data definitions from context
- Create and update glossary entries
- Suggest data stewards and ownership
- Validate definitions against policies
- Track approval workflows

---

## Phase 4: API Surface

### 4.1 Agent Execution Endpoints

Add to `dq-llm/entrypoint.py`:

```python
# New endpoints for agent operations

class AgentRequest(BaseModel):
    prompt: str
    agent_type: str = Field(..., description="dq_connector|dq_rule|dq_steward|general")
    connector_id: Optional[str] = None
    metadata_id: Optional[str] = None
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)

class AgentResponse(BaseModel):
    response: str
    session_id: str
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

@app.post("/api/llm/v1/agent/run", response_model=AgentResponse)
async def run_agent(request: AgentRequest):
    """Run a specialized DQ agent."""
    pass

@app.post("/api/llm/v1/agent/session/create", response_model=Dict[str, str])
async def create_agent_session(agent_type: str):
    """Create a new persistent agent session."""
    pass

@app.get("/api/llm/v1/agent/session/{session_id}", response_model=AgentResponse)
async def get_agent_session(session_id: str):
    """Retrieve agent session state."""
    pass

@app.post("/api/llm/v1/agent/session/{session_id}/interact", response_model=AgentResponse)
async def interact_with_session(session_id: str, prompt: str):
    """Send a message to an existing agent session."""
    pass

@app.delete("/api/llm/v1/agent/session/{session_id}", response_model=Dict[str, bool])
async def delete_agent_session(session_id: str):
    """Destroy an agent session."""
    pass
```

### 4.2 Agent Management Endpoints

```python
@app.get("/api/llm/v1/agents", response_model=List[Dict[str, Any]])
async def list_available_agents():
    """List all available specialized agent types."""
    pass

@app.get("/api/llm/v1/agents/{agent_type}/capabilities", response_model=Dict[str, Any])
async def get_agent_capabilities(agent_type: str):
    """Get capabilities and tools for a specific agent type."""
    pass

@app.get("/api/llm/v1/agents/health", response_model=Dict[str, bool])
async def check_agent_health():
    """Check health of agent harness service."""
    pass
```

---

## Phase 5: Operations & Governance

### 5.1 Audit & Compliance

**Objective**: Ensure agent operations are auditable and compliant.

- [x] Log all agent tool calls with timestamps (via AgentAuditLogger)
- [x] Capture input prompts and generated responses (with redaction)
- [x] Track which user initiated each agent session (user_id in audit logs)
- [x] Redact secrets from all logs and responses (SecretsRedactor)
- [x] Integrate with existing audit trail (WF-1.5)

**Implementation**:
```python
# dq-llm/agents/audit.py
class AgentAuditLogger:
    def log_session_start(self, session_id: str, user_id: str, agent_type: str):
        pass
    
    def log_tool_call(self, session_id: str, tool_name: str, params: Dict):
        # Redact sensitive fields
        safe_params = self._redact_sensitive(params)
        pass
    
    def log_session_end(self, session_id: str, outcome: str):
        pass
    
    def _redact_sensitive(self, data: Dict) -> Dict:
        """Remove credentials, API keys, passwords from logged data."""
        sensitive_keys = ['password', 'secret', 'api_key', 'token', 'credentials']
        # Recursively redact sensitive data
        pass
```

### 5.2 Security Considerations

**Secrets Management**:
- Agent tools must use DQ-API's secure config contract (API-1.2)
- Never pass raw credentials to agent prompts
- Use temporary session tokens where possible
- Implement least-privilege access for agent operations

**Sandboxing**:
- Bash tool execution should be restricted
- File system access should be scoped to workspace
- Network access should be limited to approved destinations (SEC-4)

**Validation**:
- All agent inputs must be validated
- Tool parameters must match expected schemas
- File paths must be within allowed directories

### 5.3 Observability

**Metrics** (extend existing Prometheus metrics in `entrypoint.py`):
- `dq_agent_sessions_active` - Currently active agent sessions
- `dq_agent_sessions_total` - Total sessions created
- `dq_agent_tool_calls_total` - Total tool invocations by type
- `dq_agent_tool_errors_total` - Tool execution errors
- `dq_agent_latency_seconds` - End-to-end latency per agent type
- `dq_agent_tokens_used` - Token usage per session

**Tracing**:
- Integrate with existing OpenTelemetry setup
- Trace each agent execution as a separate span
- Include tool calls as child spans

**Logging**:
- Structured logs for all agent operations
- Include session ID, user ID, agent type in all logs
- Log tool call start/end with duration

---

## Phase 6: UI Integration

### 6.1 Chat Interface

Extend `dq-ui` to include an agent chat interface:

**Components**:
- Agent selector (Connector, Rule Engineer, Data Steward, Custom)
- Session management (new, load, delete)
- Conversation history
- Tool call visualization
- Metadata preview (show discovered schemas, extracted rules, etc.)

**Example Flow**:
```
User: "I want to onboard a PostgreSQL database at db.example.com:5432/analytics"

Agent (Connector): 
- "I'll help you onboard that PostgreSQL database. I need a few details:
  - What username should I use?
  - How should we securely provide the password?
  - What's a descriptive name for this connector?"

User provides details...

Agent:
- Calls dq_connector.configure()
- Calls dq_connector.test_connection()
- Calls dq_connector.discover()
- Returns: "Successfully discovered 15 schemas with 47 tables. Ready to sync metadata?"
```

### 6.2 Embedded Agent Actions

Integrate agents into existing UI workflows:

**Connector Setup UI**:
- Add "Use AI Assistant" button
- Opens chat with Connector Onboarding Agent pre-loaded
- Shows discovery results in UI tables

**Rule Creation UI**:
- Add "Generate from NL" button
- Opens chat with Rule Engineer Agent
- Shows extracted rules as editable drafts

**Metadata Browser**:
- Add "Ask AI" button for selected metadata
- Opens chat with Data Steward Agent
- Context includes selected metadata

---

## Acceptance Criteria

### Functional
- [x] At least 3 specialized agents are available (Connector, Rule Engineer, Data Steward, General)
- [x] Agents can call DQ API endpoints through tools
- [x] Agent sessions persist across multiple interactions (FileSessionStore + DatabaseSessionStore)
- [x] Natural language prompts trigger appropriate workflows
- [x] Connector onboarding can be completed end-to-end via agent
- [x] DQ rules can be extracted from NL and assigned to metadata via agent

### Non-Functional
- [x] Secrets are never exposed in agent responses or logs (SecretsRedactor)
- [x] All agent operations are audited with timestamps and user context (AgentAuditLogger)
- [x] Agent errors return actionable diagnostics
- [x] Token usage and latency are tracked via metrics (Prometheus)
- [x] Agent service health is visible via endpoint (/api/llm/v1/agent/health)
- [x] Session cleanup prevents resource exhaustion (cleanup_expired)

### Integration
- [x] Agents integrate with existing dq-llm endpoints
- [x] Agents use existing connector framework (API-1)
- [x] Agents support existing rule execution (API-7)
- [x] UI integration allows agent invocation from relevant screens
- [x] Existing authentication (SSO, Keycloak) applies to agent endpoints

---

## Tracked Work Items

### Core Integration
- [x] `LLM-1.1` Add pi-agent dependency and base module structure
- [x] `LLM-1.2` Implement base DQ agent class with configuration
- [x] `LLM-1.3` Create ConnectorTool with API-1 endpoint integration
- [x] `LLM-1.4` Create RuleTool with API-7 endpoint integration
- [x] `LLM-1.5` Create DefinitionTool with dq-llm endpoint integration
- [x] `LLM-1.6` Implement session management and persistence

### Specialized Agents
- [x] `LLM-1.7` Connector Onboarding Agent (Phase 2 MVP)
- [x] `LLM-1.8` Rule Engineer Agent (API-7)
- [x] `LLM-1.9` Data Steward Agent (definitions & governance)
- [x] `LLM-1.10` General DQ Assistant Agent

### API Surface
- [x] `LLM-1.11` Agent execution endpoints
- [x] `LLM-1.12` Agent session management endpoints
- [x] `LLM-1.13` Agent listing and capabilities endpoints
- [x] `LLM-1.14` Agent health check endpoint

### Operations
- [x] `LLM-1.15` Audit logging for all agent operations
- [x] `LLM-1.16` Secrets redaction in logs and responses
- [x] `LLM-1.17` Prometheus metrics for agent operations
- [x] `LLM-1.18` OpenTelemetry tracing integration
- [x] `LLM-1.19` Security sandboxing for tool execution

### UI Integration
- [x] `LLM-1.20` Agent chat interface in dq-ui
- [x] `LLM-1.21` Connector setup AI assistant
- [x] `LLM-1.22` Rule creation NL extraction
- [x] `LLM-1.23` Metadata browser AI assistant

### Documentation
- [x] `DOC-1.10` Pi Agent Harness onboarding guide
- [x] `DOC-1.11` Agent workflow examples and templates
- [x] `DOC-1.12` Security guidelines for agent operations (see [AGENT_HARNESS_SECURITY.md](/docs/technical/AGENT_HARNESS_SECURITY/))

### Security Hardening
- [x] `LLM-1.15` Audit logging for all agent operations
- [x] `LLM-1.16` Secrets redaction in logs and responses
- [x] `LLM-1.18` OpenTelemetry tracing integration
- [x] `LLM-1.19` Security sandboxing for tool execution
- [x] `LLM-1.24` API key rotation support
- [x] `LLM-1.25` Prompt injection detection
- [x] `LLM-1.26` Rate limiting per user/agent type
- [x] `LLM-1.27` Session size limits and quotas
- [x] `LLM-1.28` Integration with existing SIEM
- [x] `LLM-1.29` Automated security testing in CI/CD
- [x] `LLM-1.30` Security chaos engineering tests
- [x] `LLM-1.31` Agent behavior anomaly detection
- [x] `SEC-AGENT-001` Security document approval

---

## Delivery Milestones

### Milestone A: Foundation ✅ COMPLETED
- `LLM-1.1` to `LLM-1.3`, `LLM-1.6`, `LLM-1.17` - Core Pi integration and basic tools
- **Success Criteria**: ✅ Agents can be instantiated and call basic tools
- **Completed**: 2025-06-06

### Milestone B: Connector Focus ✅ COMPLETED
- `LLM-1.4` to `LLM-1.5`, `LLM-1.7`, `LLM-1.11` to `LLM-1.14` - Connector agent with API endpoints
- **Success Criteria**: Connector onboarding via agent works end-to-end

### Milestone C: Full Agent Suite ✅ COMPLETED
- `LLM-1.8` to `LLM-1.10`, `LLM-1.15` to `LLM-1.16`, `LLM-1.18` to `LLM-1.19` - All specialized agents with ops
- **Success Criteria**: All three agent types operational with audit & metrics

### Milestone D: Production Ready ✅ COMPLETED
- `LLM-1.20` to `LLM-1.23`, `DOC-1.10` to `DOC-1.12` - UI integration and documentation
- **Success Criteria**: Agents accessible via UI, fully documented

---

## Dependencies

### External
- Pi Agent Harness: https://github.com/earendil-works/pi
- Documentation: https://pi.dev/

### Internal
- **API-1**: Connector framework must be complete (API-1.1 to API-1.9)
- **API-7**: Rule execution service must be available
- **dq-llm**: Existing LLM service must be operational
- **dq-api**: REST endpoints for connectors and rules
- **Keycloak**: Authentication for agent endpoints

---

## Configuration Reference

### Environment Variables

```bash
# LLM Configuration (existing, reused)
DQ_LLM_MODEL_ID=Qwen/Qwen2.5-7B-Instruct
DQ_LLM_DEVICE_MAP=auto
DQ_LLM_MAX_NEW_TOKENS=512
DQ_LLM_CHAT_PROVIDER=huggingface

# Agent Configuration (new)
DQ_AGENT_WORKSPACE=/tmp/dq-agent
DQ_AGENT_SESSION_TIMEOUT_SECONDS=3600
DQ_AGENT_MAX_TOOL_CALLS_PER_SESSION=100
DQ_AGENT_AUDIT_ENABLED=true

# Security
DQ_AGENT_API_BASE_URL=http://dq-api:4010
DQ_AGENT_API_KEY_FILE=/run/secrets/agent_api_key
```

### Docker Configuration

```yaml
# In docker-compose.yml
dq-llm:
  build:
    context: ./dq-llm
    dockerfile: Dockerfile.llm
  environment:
    - DQ_LLM_MODEL_ID=${DQ_LLM_MODEL_ID:-Qwen/Qwen2.5-7B-Instruct}
    - DQ_LLM_DEVICE_MAP=${DQ_LLM_DEVICE_MAP:-auto}
    - DQ_AGENT_WORKSPACE=/workspace/agent
    - DQ_AGENT_SESSION_TIMEOUT_SECONDS=3600
  volumes:
    - ./dq-llm/agents:/app/agents
    - agent-workspace:${DQ_AGENT_WORKSPACE:-/workspace/agent}
```

---

## Example Workflows

### Workflow 1: Connector Onboarding via Agent

```
User → UI → Agent Endpoint → Pi Agent
                              ↓
                        [ConnectorTool.configure()]
                              ↓
                        [ConnectorTool.test_connection()]
                              ↓
                        [ConnectorTool.discover()]
                              ↓
                        [ConnectorTool.sync()]
                              ↓
                        Response to User
```

**User Experience**:
```
User: "Onboard my PostgreSQL database at prod-db:5432/sales"

Agent: "I'll help you set up a PostgreSQL connector. I need:
  - Connector name (e.g., 'sales-prod')
  - Username with read access
  - Secure way to provide password"

User: "Name: sales-prod, User: readonly_user, Password: [secured]"

Agent: 
- Configuring connector... ✓
- Testing connection... ✓
- Discovering metadata... Found 5 schemas, 23 tables
- Syncing to catalog... ✓

Result: Connector 'sales-prod' is live. 23 tables available for rule assignment.
```

### Workflow 2: Rule Extraction from Natural Language

```
User → UI → Agent Endpoint → Pi Agent
                              ↓
                        [RuleTool.extract()]
                              ↓
                        [Metadata query for context]
                              ↓
                        [RuleTool.validate()]
                              ↓
                        [RuleTool.assign()]
                              ↓
                        Response to User
```

**User Experience**:
```
User: "Create rules for the customers table. Email must be valid and not null, 
       customer_id must be unique, and status must be one of: active, inactive, pending"

Agent: 
- Analyzing requirements...
- Extracting rules:
  1. Email: NOT_NULL + PATTERN('email')
  2. Customer_id: UNIQUE
  3. Status: IN_SET(['active', 'inactive', 'pending'])
- Validating against schema... ✓
- Assigning to customers table... ✓

Result: 3 rules created and assigned. Ready for execution.
```

### Workflow 3: Data Definition Generation

```
User → UI → Agent Endpoint → Pi Agent
                              ↓
                        [DefinitionTool.generate()]
                              ↓
                        [Context from connectors]
                              ↓
                        Response to User
```

**User Experience**:
```
User: "Define the 'revenue' metric from the sales table"

Agent: 
- Querying sales table metadata...
- Analyzing column definitions...
- Generating definition...

Result:
**Revenue**: The total monetary amount generated from sales transactions 
within a specific period. Measured in USD. Source: sales.amount. 
Steward: Finance Team. Business Context: Key performance indicator for 
sales performance tracking and financial reporting.
```

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Pi Agent dependency conflicts | Medium | High | Use virtual environment isolation, pin versions |
| Token usage costs | High | Medium | Implement rate limiting, session timeouts, usage quotas |
| Security vulnerabilities in tool execution | Medium | High | Sandbox execution, input validation, audit logging |
| Performance bottlenecks | Medium | Medium | Async tool execution, timeouts, resource limits |
| Agent hallucinations | High | Medium | Validation against schema, user confirmation prompts |
| Session state corruption | Low | Medium | Checksum validation, periodic snapshots |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Agent task completion rate | >90% | % of user requests successfully completed |
| Average time to onboard connector | &lt;5 min | End-to-end timing with agent assistance |
| Rule extraction accuracy | >85% | % of NL rules correctly extracted and validated |
| User satisfaction score | >4.5/5 | Survey after agent interactions |
| Agent adoption rate | >70% | % of eligible workflows using agents |
| Token efficiency | &lt;10% overhead | Additional tokens vs. direct API calls |

---

## References

- [Pi Agent Harness GitHub](https://github.com/earendil-works/pi)
- [Pi Documentation](https://pi.dev/)
- [API-1 New Data Source Connectors](/docs/features/API_1_CONNECTORS/)
- [API-7 Real DQ Rule Execution](/docs/status/current/API_7_REAL_DQ_RULE_EXECUTION/)
- [Connector Onboarding Runbook](/docs/technical/CONNECTOR_ONBOARDING_RUNBOOK/)
- [AGENTIC_AI_ECOSYSTEM_FEATURES.md](/docs/features/AGENTIC_AI_ECOSYSTEM_FEATURES/)
- [Agent Harness Security Model](/docs/technical/AGENT_HARNESS_SECURITY/) - **NEW**
