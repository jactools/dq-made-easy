from __future__ import annotations

import json

from dq_cli import mcp_server


class _StubClient:
    def validate_dataset(self, *, workspace: str, rule_ids: list[str]) -> dict:
        return {
            "run_id": "run-001",
            "workspace": workspace,
            "rule_ids": rule_ids,
        }

    def get_execution_monitoring_dashboard(self) -> dict:
        return {"dashboard": "execution_monitoring", "status": "ok"}

    def get_execution_run(self, *, run_id: str) -> dict:
        return {
            "run_id": run_id,
            "resultSummary": {
                "engine_type": "spark_expectations",
                "result": "failed",
                "passed_count": 2,
                "failed_count": 1,
                "failure_code": "DQ_EXECUTION_ERROR",
                "failure_message": "row-level expectation failed",
                "failed_check": {"check_name": "not_null", "reason": "customer_id cannot be null"},
                "failure_metrics": {"failed_check_count": 1, "failed_row_count": 1},
                "trace": {"exception_type": "ValueError", "message": "row-level expectation failed"},
            },
        }

    def get_rule_library_registry(self, *, page: int = 1, limit: int = 100) -> dict:
        return {"page": page, "limit": limit, "entries": []}

    def get_latest_lineage_graph(
        self,
        *,
        workspace_id: str | None = None,
        data_product_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict:
        return {
            "workspace_id": workspace_id,
            "data_product_id": data_product_id,
            "limit": limit,
            "offset": offset,
            "nodes": [],
            "edges": [],
        }


def test_initialize_tools_list_and_tools_call_path() -> None:
    client = _StubClient()

    init_response, should_exit = mcp_server._handle_request(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        },
    )
    assert should_exit is False
    assert init_response["result"]["protocolVersion"] == mcp_server.PROTOCOL_VERSION
    assert "tools" in init_response["result"]["capabilities"]

    tools_response, should_exit = mcp_server._handle_request(
        client,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
    )
    assert should_exit is False
    tool_names = {item["name"] for item in tools_response["result"]["tools"]}
    assert {"validate_dataset", "get_anomalies", "trigger_remediation", "get_execution_run"}.issubset(tool_names)

    call_response, should_exit = mcp_server._handle_request(
        client,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "validate_dataset",
                "arguments": {
                    "workspace": "workspace-a",
                    "rule_ids": ["rule-1"],
                },
            },
        },
    )
    assert should_exit is False
    assert call_response["result"]["isError"] is False
    call_payload = json.loads(call_response["result"]["content"][0]["text"])
    assert call_payload["run_id"] == "run-001"

    run_response, should_exit = mcp_server._handle_request(
        client,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "get_execution_run",
                "arguments": {"run_id": "run-777"},
            },
        },
    )
    assert should_exit is False
    assert run_response["result"]["isError"] is False
    run_payload = json.loads(run_response["result"]["content"][0]["text"])
    assert run_payload["run_id"] == "run-777"
    assert run_payload["resultSummary"]["failure_code"] == "DQ_EXECUTION_ERROR"
    assert run_payload["resultSummary"]["failure_metrics"]["failed_row_count"] == 1


def test_resources_list_and_resources_read_path() -> None:
    client = _StubClient()

    resources_response, should_exit = mcp_server._handle_request(
        client,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/list",
            "params": {},
        },
    )
    assert should_exit is False
    uris = {item["uri"] for item in resources_response["result"]["resources"]}
    assert mcp_server.RESOURCE_URI_DASHBOARDS in uris
    assert mcp_server.RESOURCE_URI_RULE_LIBRARIES in uris
    assert mcp_server.RESOURCE_URI_LINEAGE_GRAPH in uris

    read_response, should_exit = mcp_server._handle_request(
        client,
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {
                "uri": mcp_server.RESOURCE_URI_DASHBOARDS,
            },
        },
    )
    assert should_exit is False
    contents = read_response["result"]["contents"]
    assert len(contents) == 1
    assert contents[0]["uri"] == mcp_server.RESOURCE_URI_DASHBOARDS
    payload = json.loads(contents[0]["text"])
    assert payload["dashboard"] == "execution_monitoring"


def test_api_client_includes_agent_provenance_headers() -> None:
    client = mcp_server.DqApiClient(
        base_url="https://example.invalid/api",
        token="abc123",
        timeout_seconds=10.0,
        agent_type="mcp",
        agent_source="dq-made-easy-mcp",
        agent_instance_id="dq-made-easy-mcp:999",
        agent_origin="stdio",
    )

    headers = client._headers()
    assert headers["Authorization"] == "Bearer abc123"
    assert headers["X-Agent-Type"] == "mcp"
    assert headers["X-Agent-Source"] == "dq-made-easy-mcp"
    assert headers["X-Agent-Instance-Id"] == "dq-made-easy-mcp:999"
    assert headers["X-Forwarded-For"] == "stdio"
