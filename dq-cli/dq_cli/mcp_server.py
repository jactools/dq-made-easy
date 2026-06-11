from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx


JSON_RPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "dq-made-easy-mcp"
SERVER_VERSION = "0.1.0"

RESOURCE_URI_DASHBOARDS = "dq://dashboards/execution-monitoring"
RESOURCE_URI_RULE_LIBRARIES = "dq://rule-libraries/registry"
RESOURCE_URI_LINEAGE_GRAPH = "dq://lineage/graph-latest"


class McpServerError(RuntimeError):
    """Represents a tool-level failure that should be surfaced to the MCP client."""


@dataclass(slots=True)
class ServerConfig:
    base_url: str
    token: str | None
    timeout_seconds: float
    agent_type: str
    agent_source: str
    agent_instance_id: str
    agent_origin: str


class DqApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str | None,
        timeout_seconds: float,
        agent_type: str,
        agent_source: str,
        agent_instance_id: str,
        agent_origin: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds
        self._agent_type = agent_type
        self._agent_source = agent_source
        self._agent_instance_id = agent_instance_id
        self._agent_origin = agent_origin

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Agent-Type": self._agent_type,
            "X-Agent-Source": self._agent_source,
            "X-Agent-Instance-Id": self._agent_instance_id,
            "X-Forwarded-For": self._agent_origin,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _request(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=self._headers(),
                    json=payload,
                    params=params,
                )
        except httpx.RequestError as exc:
            raise McpServerError(f"API request failed for {method} {path}: {exc}") from exc

        if response.status_code >= 400:
            body = response.text.strip()
            raise McpServerError(
                f"API request failed for {method} {path}: status={response.status_code} body={body}"
            )

        if not response.content:
            return {}

        try:
            decoded: Any = response.json()
        except ValueError as exc:
            raise McpServerError(f"API response for {method} {path} is not valid JSON") from exc

        if not isinstance(decoded, dict):
            return {"data": decoded}
        return decoded

    def validate_dataset(self, *, workspace: str, rule_ids: list[str]) -> dict[str, Any]:
        if not workspace.strip():
            raise McpServerError("workspace is required")
        if not rule_ids:
            raise McpServerError("rule_ids must contain at least one rule id")

        payload = {
            "ruleIds": [str(rule_id).strip() for rule_id in rule_ids if str(rule_id).strip()],
            "workspace": workspace,
        }
        if not payload["ruleIds"]:
            raise McpServerError("rule_ids must contain at least one non-empty rule id")

        return self._request(
            method="POST",
            path="/rulebuilder/v1/rules/validate/batch",
            payload=payload,
        )

    def get_anomalies(
        self,
        *,
        delivery_id: str,
        lookback_amount: int,
        lookback_unit: str,
        status: str | None,
        rule_name: str | None,
        data_object_name: str | None,
        reason_code: str | None,
    ) -> dict[str, Any]:
        if not delivery_id.strip():
            raise McpServerError("delivery_id is required")

        params: dict[str, Any] = {
            "lookbackAmount": lookback_amount,
            "lookbackUnit": lookback_unit,
        }
        if status:
            params["status"] = status
        if rule_name:
            params["ruleName"] = rule_name
        if data_object_name:
            params["dataObjectName"] = data_object_name
        if reason_code:
            params["reasonCode"] = reason_code

        return self._request(
            method="GET",
            path=f"/rulebuilder/v1/deliveries/{delivery_id}/exception-summary",
            params=params,
        )

    def trigger_remediation(
        self,
        *,
        incident_kind: str,
        title: str,
        description: str | None,
        severity: str | None,
        workspace_id: str | None,
        run_id: str | None,
        run_plan_id: str | None,
        scope_kind: str | None,
        scope_id: str | None,
        violation_count: int | None,
        violated_rule_ids: list[str] | None,
        failure_code: str | None,
        failure_message: str | None,
        create_itsm_ticket: bool,
    ) -> dict[str, Any]:
        if not incident_kind.strip():
            raise McpServerError("incident_kind is required")
        if not title.strip():
            raise McpServerError("title is required")

        payload: dict[str, Any] = {
            "incident_kind": incident_kind,
            "title": title,
            "create_itsm_ticket": create_itsm_ticket,
        }

        if description:
            payload["description"] = description
        if severity:
            payload["severity"] = severity
        if workspace_id:
            payload["workspace_id"] = workspace_id
        if run_id:
            payload["run_id"] = run_id
        if run_plan_id:
            payload["run_plan_id"] = run_plan_id
        if scope_kind:
            payload["scope_kind"] = scope_kind
        if scope_id:
            payload["scope_id"] = scope_id
        if violation_count is not None:
            payload["violation_count"] = violation_count
        if violated_rule_ids:
            payload["violated_rule_ids"] = [
                str(rule_id).strip() for rule_id in violated_rule_ids if str(rule_id).strip()
            ]
        if failure_code:
            payload["failure_code"] = failure_code
        if failure_message:
            payload["failure_message"] = failure_message

        return self._request(
            method="POST",
            path="/rulebuilder/v1/incidents",
            payload=payload,
        )

    def get_execution_monitoring_dashboard(self) -> dict[str, Any]:
        return self._request(
            method="GET",
            path="/rulebuilder/v1/observability/health-scorecards",
        )

    def get_rule_library_registry(self, *, page: int = 1, limit: int = 100) -> dict[str, Any]:
        return self._request(
            method="GET",
            path="/rulebuilder/v1/rules/registry",
            params={"page": page, "limit": limit},
        )

    def get_latest_lineage_graph(
        self,
        *,
        workspace_id: str | None = None,
        data_product_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }
        if workspace_id:
            payload["workspace_id"] = workspace_id
        if data_product_id:
            payload["data_product_id"] = data_product_id

        return self._request(
            method="POST",
            path="/data-catalog/v1/ontology/graph/query",
            payload=payload,
        )


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_args() -> ServerConfig:
    parser = argparse.ArgumentParser(
        prog="dq-mcp-server",
        description="Run the dq-made-easy MCP server over stdio.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base URL for dq-api, including /api prefix.",
    )
    parser.add_argument(
        "--token",
        default=_env("DQ_MCP_API_TOKEN"),
        help="Bearer token for dq-api requests.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=None,
        help="HTTP timeout in seconds for dq-api calls.",
    )
    args = parser.parse_args()

    base_url = str(args.base_url or _env("DQ_MCP_API_BASE_URL") or "").strip()
    if not base_url:
        raise SystemExit("Missing required MCP API base URL. Set --base-url or DQ_MCP_API_BASE_URL.")

    timeout_candidate = args.timeout_seconds
    if timeout_candidate is None:
        timeout_env = _env("DQ_MCP_API_TIMEOUT_SECONDS")
        if timeout_env is None:
            raise SystemExit(
                "Missing required MCP API timeout. Set --timeout-seconds or DQ_MCP_API_TIMEOUT_SECONDS."
            )
        try:
            timeout_candidate = float(timeout_env)
        except ValueError as exc:
            raise SystemExit("DQ_MCP_API_TIMEOUT_SECONDS must be a number") from exc

    if timeout_candidate <= 0:
        raise SystemExit("--timeout-seconds must be greater than zero")

    return ServerConfig(
        base_url=base_url.rstrip("/"),
        token=args.token,
        timeout_seconds=float(timeout_candidate),
        agent_type="mcp",
        agent_source=SERVER_NAME,
        agent_instance_id=f"{SERVER_NAME}:{os.getpid()}",
        agent_origin="stdio",
    )


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "validate_dataset",
            "description": "Run batch rule validation for a workspace.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace": {
                        "type": "string",
                        "description": "Workspace name or key used by the validation batch endpoint.",
                    },
                    "rule_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Rule IDs to validate.",
                    },
                },
                "required": ["workspace", "rule_ids"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_anomalies",
            "description": "Fetch delivery-scoped exception analytics.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "delivery_id": {"type": "string"},
                    "lookback_amount": {"type": "integer", "minimum": 1, "maximum": 720, "default": 24},
                    "lookback_unit": {
                        "type": "string",
                        "enum": ["hours", "days", "weeks"],
                        "default": "hours",
                    },
                    "status": {"type": "string"},
                    "rule_name": {"type": "string"},
                    "data_object_name": {"type": "string"},
                    "reason_code": {"type": "string"},
                },
                "required": ["delivery_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "trigger_remediation",
            "description": "Create an incident to start remediation workflows.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "incident_kind": {
                        "type": "string",
                        "description": "technical_run_error or functional_violation",
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "severity": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "run_id": {"type": "string"},
                    "run_plan_id": {"type": "string"},
                    "scope_kind": {"type": "string"},
                    "scope_id": {"type": "string"},
                    "violation_count": {"type": "integer", "minimum": 0},
                    "violated_rule_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "failure_code": {"type": "string"},
                    "failure_message": {"type": "string"},
                    "create_itsm_ticket": {"type": "boolean", "default": False},
                },
                "required": ["incident_kind", "title"],
                "additionalProperties": False,
            },
        },
    ]


def _resource_definitions() -> list[dict[str, Any]]:
    return [
        {
            "uri": RESOURCE_URI_DASHBOARDS,
            "name": "execution_monitoring_dashboard",
            "description": "Execution monitoring dashboard summaries and scorecards.",
            "mimeType": "application/json",
        },
        {
            "uri": RESOURCE_URI_RULE_LIBRARIES,
            "name": "rule_library_registry",
            "description": "Governed rule registry and library entries.",
            "mimeType": "application/json",
        },
        {
            "uri": RESOURCE_URI_LINEAGE_GRAPH,
            "name": "lineage_graph_latest",
            "description": "Latest persisted ontology lineage graph projection.",
            "mimeType": "application/json",
        },
    ]


def _read_resource(client: DqApiClient, *, uri: str) -> dict[str, Any]:
    normalized_uri = str(uri or "").strip()
    if normalized_uri == RESOURCE_URI_DASHBOARDS:
        return client.get_execution_monitoring_dashboard()
    if normalized_uri == RESOURCE_URI_RULE_LIBRARIES:
        return client.get_rule_library_registry(page=1, limit=100)
    if normalized_uri == RESOURCE_URI_LINEAGE_GRAPH:
        return client.get_latest_lineage_graph(limit=200, offset=0)
    raise McpServerError(f"Unknown resource '{normalized_uri}'")


def _write_message(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    header = f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line == b"\r\n":
            break
        decoded = line.decode("ascii", errors="replace").strip()
        if not decoded:
            continue
        name, sep, value = decoded.partition(":")
        if not sep:
            continue
        headers[name.strip().lower()] = value.strip()

    content_length = headers.get("content-length")
    if content_length is None:
        raise McpServerError("Missing Content-Length header")

    try:
        length = int(content_length)
    except ValueError as exc:
        raise McpServerError("Invalid Content-Length header") from exc

    body = sys.stdin.buffer.read(length)
    if len(body) != length:
        raise McpServerError("Unexpected EOF while reading message body")

    try:
        payload = json.loads(body.decode("utf-8"))
    except ValueError as exc:
        raise McpServerError("Request body is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise McpServerError("JSON-RPC payload must be an object")
    return payload


def _result_for_text(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def _handle_request(client: DqApiClient, request: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    method = request.get("method")
    params = request.get("params")
    request_id = request.get("id")

    if method == "initialize":
        return (
            {
                "jsonrpc": JSON_RPC_VERSION,
                "id": request_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "capabilities": {"tools": {}, "resources": {}},
                },
            },
            False,
        )

    if method == "ping":
        return (
            {
                "jsonrpc": JSON_RPC_VERSION,
                "id": request_id,
                "result": {},
            },
            False,
        )

    if method == "tools/list":
        return (
            {
                "jsonrpc": JSON_RPC_VERSION,
                "id": request_id,
                "result": {"tools": _tool_definitions()},
            },
            False,
        )

    if method == "resources/list":
        return (
            {
                "jsonrpc": JSON_RPC_VERSION,
                "id": request_id,
                "result": {"resources": _resource_definitions()},
            },
            False,
        )

    if method == "resources/read":
        if not isinstance(params, dict):
            return (
                {
                    "jsonrpc": JSON_RPC_VERSION,
                    "id": request_id,
                    "error": {"code": -32602, "message": "Invalid params for resources/read"},
                },
                False,
            )

        resource_uri = str(params.get("uri") or "").strip()
        if not resource_uri:
            return (
                {
                    "jsonrpc": JSON_RPC_VERSION,
                    "id": request_id,
                    "error": {"code": -32602, "message": "resources/read requires uri"},
                },
                False,
            )

        try:
            payload = _read_resource(client, uri=resource_uri)
        except McpServerError as exc:
            return (
                {
                    "jsonrpc": JSON_RPC_VERSION,
                    "id": request_id,
                    "error": {"code": -32001, "message": str(exc)},
                },
                False,
            )

        return (
            {
                "jsonrpc": JSON_RPC_VERSION,
                "id": request_id,
                "result": {
                    "contents": [
                        {
                            "uri": resource_uri,
                            "mimeType": "application/json",
                            "text": json.dumps(payload, indent=2, sort_keys=True),
                        }
                    ]
                },
            },
            False,
        )

    if method == "tools/call":
        if not isinstance(params, dict):
            return (
                {
                    "jsonrpc": JSON_RPC_VERSION,
                    "id": request_id,
                    "error": {"code": -32602, "message": "Invalid params for tools/call"},
                },
                False,
            )

        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return (
                {
                    "jsonrpc": JSON_RPC_VERSION,
                    "id": request_id,
                    "error": {"code": -32602, "message": "tools/call arguments must be an object"},
                },
                False,
            )

        try:
            if tool_name == "validate_dataset":
                payload = client.validate_dataset(
                    workspace=str(arguments.get("workspace") or ""),
                    rule_ids=[str(value) for value in list(arguments.get("rule_ids") or [])],
                )
            elif tool_name == "get_anomalies":
                payload = client.get_anomalies(
                    delivery_id=str(arguments.get("delivery_id") or ""),
                    lookback_amount=int(arguments.get("lookback_amount", 24)),
                    lookback_unit=str(arguments.get("lookback_unit") or "hours"),
                    status=_optional_string(arguments.get("status")),
                    rule_name=_optional_string(arguments.get("rule_name")),
                    data_object_name=_optional_string(arguments.get("data_object_name")),
                    reason_code=_optional_string(arguments.get("reason_code")),
                )
            elif tool_name == "trigger_remediation":
                payload = client.trigger_remediation(
                    incident_kind=str(arguments.get("incident_kind") or ""),
                    title=str(arguments.get("title") or ""),
                    description=_optional_string(arguments.get("description")),
                    severity=_optional_string(arguments.get("severity")),
                    workspace_id=_optional_string(arguments.get("workspace_id")),
                    run_id=_optional_string(arguments.get("run_id")),
                    run_plan_id=_optional_string(arguments.get("run_plan_id")),
                    scope_kind=_optional_string(arguments.get("scope_kind")),
                    scope_id=_optional_string(arguments.get("scope_id")),
                    violation_count=_optional_int(arguments.get("violation_count")),
                    violated_rule_ids=_optional_string_list(arguments.get("violated_rule_ids")),
                    failure_code=_optional_string(arguments.get("failure_code")),
                    failure_message=_optional_string(arguments.get("failure_message")),
                    create_itsm_ticket=bool(arguments.get("create_itsm_ticket", False)),
                )
            else:
                raise McpServerError(f"Unknown tool '{tool_name}'")
        except (TypeError, ValueError) as exc:
            result = _result_for_text(f"Invalid tool arguments: {exc}", is_error=True)
        except McpServerError as exc:
            result = _result_for_text(str(exc), is_error=True)
        else:
            result = _result_for_text(json.dumps(payload, indent=2, sort_keys=True), is_error=False)

        return (
            {
                "jsonrpc": JSON_RPC_VERSION,
                "id": request_id,
                "result": result,
            },
            False,
        )

    if method == "shutdown":
        return (
            {
                "jsonrpc": JSON_RPC_VERSION,
                "id": request_id,
                "result": {},
            },
            True,
        )

    return (
        {
            "jsonrpc": JSON_RPC_VERSION,
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}",
            },
        },
        False,
    )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("violated_rule_ids must be a list of strings")
    normalized = [str(item).strip() for item in value if str(item).strip()]
    return normalized or None


def main() -> None:
    config = _parse_args()
    client = DqApiClient(
        base_url=config.base_url,
        token=config.token,
        timeout_seconds=config.timeout_seconds,
        agent_type=config.agent_type,
        agent_source=config.agent_source,
        agent_instance_id=config.agent_instance_id,
        agent_origin=config.agent_origin,
    )

    should_exit = False
    while not should_exit:
        try:
            message = _read_message()
            if message is None:
                break

            # Notifications have no request id and do not require a response.
            if "id" not in message:
                if message.get("method") == "exit":
                    break
                continue

            response, should_exit = _handle_request(client, message)
            _write_message(response)
        except McpServerError as exc:
            error_id = None
            error_response = {
                "jsonrpc": JSON_RPC_VERSION,
                "id": error_id,
                "error": {
                    "code": -32603,
                    "message": str(exc),
                },
            }
            _write_message(error_response)


if __name__ == "__main__":
    main()
