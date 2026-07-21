# WS-10 Agentic AI Ecosystem Capabilities

This document summarizes what is already implemented for WS10-A01, WS10-A02, and WS10-A03 so human and autonomous agents can quickly understand which contracts are available and how to use them.

## Scope Status

- WS10-A01: implemented
- WS10-A02: implemented
- WS10-A03: implemented baseline workflows
- WS10-A04: implemented webhook dispatch with retry, payload envelope, and audit trail (job dispatch deferred)

## First 5-Minute Smoke Flow

Use this checklist to quickly confirm that the WS-10 baseline is live and usable.

1. Set `DQ_API_BASE_URL` and `DQ_API_TOKEN` and call `GET /agent/v1/openapi`.
2. Run one `POST /agent/v1/rules/execute-batch` request with a known rule ID and workspace.
3. Call one metadata read path (`GET /agent/v1/metadata/data-objects` or `POST /agent/v1/metadata/lineage/query`).
4. Start the MCP server with `DQ_MCP_API_BASE_URL`, `DQ_MCP_API_TOKEN`, and `DQ_MCP_API_TIMEOUT_SECONDS`.
5. Send MCP `initialize`, then `tools/list`, then one `tools/call` (`validate_dataset`).
6. Send MCP `resources/list`, then `resources/read` for `dq://dashboards/execution-monitoring`.
7. Confirm one audit record appears via `GET /agent/v1/audit/events` (admin scope).

Expected result: all calls succeed with explicit JSON responses, and agent actions are visible in audit history.

## What Agents Can Use Today

There are two supported access patterns:

1. Agent-ready REST endpoints under `/agent/v1/*` for direct HTTP clients.
2. MCP server tools and resources over stdio for MCP-compatible clients.

Both patterns are governed by platform auth scopes and app-admin agent access policy.

## WS10-A01 Agent-Ready REST Endpoints

### Base Paths

- External API path: `/api/agent/v1/*`
- Gateway-compatible path: `/agent/v1/*`

### Endpoints

- `POST /agent/v1/rules/execute-batch`
  - Purpose: execute rule validation for a workspace and a set of rule IDs.
  - Request contract: snake_case JSON.
  - Example request:

```json
{
  "rule_ids": ["rule-001"],
  "workspace": "workspace-a"
}
```

- `GET /agent/v1/anomalies/deliveries/{delivery_id}`
  - Purpose: delivery-scoped anomaly and exception summary for agent triage.
  - Query options include snake_case fields such as `lookback_amount`, `lookback_unit`, and filter parameters.

- `GET /agent/v1/metadata/data-objects`
  - Purpose: metadata lookup for data objects.
  - Query options: `search`, `limit`.

- `POST /agent/v1/metadata/lineage/query`
  - Purpose: query ontology-backed lineage graph projections.
  - Request contract supports snake_case fields such as:
    - `workspace_id`
    - `data_product_id`
    - `label_contains`
    - `node_ids`
    - `node_types`
    - `relation_types`
    - `limit`
    - `offset`

- `GET /agent/v1/openapi`
  - Purpose: publish the OpenAPI subset for the agent endpoint family.
  - Response includes `openapi`, `info`, and filtered `paths` for `/agent/v1/*`.

- `GET /agent/v1/audit/events`
  - Purpose: list registered agent request audit events (admin-read scope).

### Contract Conventions

- Transport contracts are snake_case on the API surface.
- Endpoint models are backed by `SnakeModel` so clients can rely on canonical snake_case payloads.
- Published OpenAPI subset is available through `/agent/v1/openapi`.

## WS10-A02 MCP Server Resources And Tools

The MCP server exposes governed resources and tools for DQ workflows.

### MCP Resources

- `dq://dashboards/execution-monitoring`
  - Backed by execution monitoring dashboard summaries.
- `dq://rule-libraries/registry`
  - Backed by rule registry/list APIs.
- `dq://lineage/graph-latest`
  - Backed by the latest ontology lineage graph projection query.

### MCP Tools

- `validate_dataset`
  - Calls batch rule validation.
- `get_anomalies`
  - Calls delivery anomaly summary path.
- `trigger_remediation`
  - Creates governed incidents for remediation workflows.

### MCP Protocol Handlers

- `initialize`
- `tools/list`
- `tools/call`
- `resources/list`
- `resources/read`

## WS10-A03 Baseline Autonomous Workflow Coverage

The current baseline supports key workflow primitives required for autonomous DQ behaviors:

- Data steward flow:
  - Detect anomalies through `get_anomalies`.
  - Inspect metadata and lineage through REST or MCP resources.
  - Trigger incident/remediation through `trigger_remediation`.

- Lineage explorer flow:
  - Query ontology lineage graph via `/agent/v1/metadata/lineage/query`.
  - Read latest graph snapshot through MCP `dq://lineage/graph-latest`.

- Remediation bot flow:
  - Run targeted rule checks with `validate_dataset`.
  - Open governed remediation incidents with `trigger_remediation`.

## WS10-A04 External Agent Platform Contracts

The platform now exposes explicit integration contracts for external agent and orchestration systems.

### Supported Contract Endpoints

- `GET /agent/v1/integrations/contracts`
  - Lists the supported external platform contracts and whether each one is currently allowlisted.
- `POST /agent/v1/integrations/dispatches`
  - Validates and accepts an operator-owned dispatch request for a supported external platform.
  - Returns an accepted dispatch envelope with the normalized platform, dispatch mode, and target metadata.

### Contracted Platforms

The integration contract surface documents the following platforms:

- Mistral AI
- Microsoft Copilot
- GitHub Copilot
- Slack
- Airflow
- Dagster

### Initial Allow-List

The seeded default allow-list currently enables:

- `mistral_ai`
- `microsoft_copilot`

The allow-list is stored in app-config and seeded through repo mock-data so operator-managed environments can override it without code changes.

## WS10-A05 Decision Context For Agent Actions

The agent API now exposes a governance-aware decision context endpoint that bundles the most useful operator and steward signals into one backend-owned response.

### Supported Context Endpoint

- `GET /agent/v1/context/decisions/{rule_id}`
  - Purpose: return rule context, business context, lineage context, active SLA thresholds, explanation payloads, and remediation audit trail data for an agent decision.
  - Typical query options: `data_asset_id`, `recent_event_limit`, `lineage_snapshot_limit`.

### What The Response Includes

- Rule metadata and taxonomy.
- Business context from the linked asset when available.
- Latest lineage snapshot summary and snapshot history.
- Active SLA/SLO thresholds for the workspace.
- A derived explanation payload with signals, recommended actions, and evidence counts.
- Recent remediation-related audit events and rule status history.

### Quick Decision-Context Smoke Call

```bash
curl -sS "$DQ_API_BASE_URL/agent/v1/context/decisions/rule-001?data_asset_id=asset-001&recent_event_limit=5&lineage_snapshot_limit=2" \
  -H "Authorization: Bearer $DQ_API_TOKEN" \
  -H "X-Agent-Type: mcp" \
  -H "X-Agent-Source: quickstart" \
  -H "X-Agent-Instance-Id: quickstart-001" \
  -H "X-Forwarded-For: stdio" | jq
```

## Agent Quickstart

Use this section when building an agent connector, MCP client, or test harness.

### Prerequisites

- An API token with required scopes.
- Agent identity must be allowed by app-admin `agent_access_policy`.
- Base URL should include `/api` when using external HTTP routes.

### REST Quickstart (copy/paste)

Set environment variables:

```bash
export DQ_API_BASE_URL="http://localhost:9111/api"
export DQ_API_TOKEN="replace-with-token"
```

Get the agent OpenAPI subset:

```bash
curl -sS "$DQ_API_BASE_URL/agent/v1/openapi" \
  -H "Authorization: Bearer $DQ_API_TOKEN" \
  -H "X-Agent-Type: mcp" \
  -H "X-Agent-Source: quickstart" \
  -H "X-Agent-Instance-Id: quickstart-001" \
  -H "X-Forwarded-For: stdio" | jq
```

Execute a batch of rules:

```bash
curl -sS "$DQ_API_BASE_URL/agent/v1/rules/execute-batch" \
  -X POST \
  -H "Authorization: Bearer $DQ_API_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Agent-Type: mcp" \
  -H "X-Agent-Source: quickstart" \
  -H "X-Agent-Instance-Id: quickstart-001" \
  -H "X-Forwarded-For: stdio" \
  -d '{"rule_ids":["rule-001"],"workspace":"workspace-a"}' | jq
```

Read anomalies for a delivery:

```bash
curl -sS "$DQ_API_BASE_URL/agent/v1/anomalies/deliveries/delivery-001?lookback_amount=24&lookback_unit=hours" \
  -H "Authorization: Bearer $DQ_API_TOKEN" \
  -H "X-Agent-Type: mcp" \
  -H "X-Agent-Source: quickstart" \
  -H "X-Agent-Instance-Id: quickstart-001" \
  -H "X-Forwarded-For: stdio" | jq
```

Lookup metadata objects:

```bash
curl -sS "$DQ_API_BASE_URL/agent/v1/metadata/data-objects?search=customer&limit=10" \
  -H "Authorization: Bearer $DQ_API_TOKEN" \
  -H "X-Agent-Type: mcp" \
  -H "X-Agent-Source: quickstart" \
  -H "X-Agent-Instance-Id: quickstart-001" \
  -H "X-Forwarded-For: stdio" | jq
```

Query lineage graph:

```bash
curl -sS "$DQ_API_BASE_URL/agent/v1/metadata/lineage/query" \
  -X POST \
  -H "Authorization: Bearer $DQ_API_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Agent-Type: mcp" \
  -H "X-Agent-Source: quickstart" \
  -H "X-Agent-Instance-Id: quickstart-001" \
  -H "X-Forwarded-For: stdio" \
  -d '{"workspace_id":"workspace-a","limit":50,"offset":0}' | jq
```

Read audit events (admin scope):

```bash
curl -sS "$DQ_API_BASE_URL/agent/v1/audit/events?limit=20&offset=0" \
  -H "Authorization: Bearer $DQ_API_TOKEN" \
  -H "X-Agent-Type: mcp" \
  -H "X-Agent-Source: quickstart" \
  -H "X-Agent-Instance-Id: quickstart-001" \
  -H "X-Forwarded-For: stdio" | jq
```

### MCP Quickstart (initialize, list, call, resources)

Configure MCP server environment:

```bash
export DQ_MCP_API_BASE_URL="http://localhost:9111/api"
export DQ_MCP_API_TOKEN="replace-with-token"
export DQ_MCP_API_TIMEOUT_SECONDS="30"
```

The MCP server supports:

- `initialize`
- `tools/list`
- `tools/call`
- `resources/list`
- `resources/read`

Example JSON-RPC request bodies (protocol payload only):

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
```

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
```

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"validate_dataset","arguments":{"workspace":"workspace-a","rule_ids":["rule-001"]}}}
```

```json
{"jsonrpc":"2.0","id":4,"method":"resources/list","params":{}}
```

```json
{"jsonrpc":"2.0","id":5,"method":"resources/read","params":{"uri":"dq://dashboards/execution-monitoring"}}
```

### Expected Failure Modes (Fail-Fast)

- Missing/invalid scopes: HTTP 403 with `insufficient_scope` details.
- Agent not allowlisted: HTTP 403 with `agent_not_allowed` details.
- Missing required fields: HTTP 422 validation errors.
- Downstream or policy shape failures: HTTP 503 service-unavailable style errors.

## Governance And Security Behavior

- Agent access is deny-by-default unless explicitly allowed by app-admin `agent_access_policy` configuration.
- Agent provenance headers are captured for MCP-originated API calls:
  - `X-Agent-Type`
  - `X-Agent-Source`
  - `X-Agent-Instance-Id`
  - `X-Forwarded-For`
- Agent request outcomes are audited with explicit response typing (for example, success, validation error, denied, service unavailable).

## Validation Evidence

- MCP integration test coverage includes initialize, tools/list, and tools/call.
- MCP resource coverage includes resources/list and resources/read.
- Agent REST coverage includes snake_case contract validation and OpenAPI subset publication checks.

Primary tests:

- `dq-cli/tests/test_mcp_server_integration.py`
- `dq-api/fastapi/tests/api/test_agent_endpoints.py`

## Known Remaining WS-10 Follow-On Scope

The following WS-10 items are still open and should not be assumed complete:

- WS10-A05 richer governance and observability context for each agent action