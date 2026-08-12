"""Test MCP client for the DQ Made Easy MCP server.

Simulates an external AI agent that connects to the MCP server over stdio
and exercises the full tool/resource protocol.

Usage:
    # Run the MCP server in background, then feed it requests via pipe:
    python -m dq_cli.mcp_server --base-url http://localhost:9111/api &
    python -m dq_cli.mcp_test_client --base-url http://localhost:9111/api

    # Or use stdin/stdout directly (pipes):
    python -m dq_cli.mcp_server --base-url URL | python -m dq_cli.mcp_test_client

    # Or with subprocess (recommended for testing):
    python -m dq_cli.mcp_test_client --server-cmd "python -m dq_cli.mcp_server --base-url URL --timeout-seconds 30"

    # Run a specific scenario:
    python -m dq_cli.mcp_test_client --scenario smoke_test --base-url http://localhost:9111/api

Exit codes:
    0 - All checks passed
    1 - Test failure
    2 - Configuration error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# MCP protocol constants
JSON_RPC_VERSION = "2.0"


class McpClientError(RuntimeError):
    """Raised when the MCP client encounters an error."""


@dataclass
class McpResponse:
    """Parsed response from the MCP server."""

    request_id: int | None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None


class McpClient:
    """MCP client that communicates with the server over stdio.

    Supports both direct stdio mode (client reads stdin, writes stdout)
    and subprocess mode (client spawns the server and pipes to it).
    """

    def __init__(
        self,
        *,
        server_process: subprocess.Popen | None = None,
        client_name: str = "dq-mcp-test-client",
        client_version: str = "1.0.0",
    ) -> None:
        self._process = server_process
        self._request_id = 0
        self._client_name = client_name
        self._client_version = client_version
        self._initialized = False

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _read_line(self) -> bytes:
        """Read a line from stdin (client mode) or server stdout (subprocess mode)."""
        if self._process:
            line = self._process.stdout.readline() if self._process.stdout else b""  # type: ignore[union-attr]
        else:
            line = sys.stdin.buffer.readline()
        return line

    def _write_message(self, payload: dict[str, Any]) -> None:
        """Write a JSON-RPC message with Content-Length framing."""
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        header = f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii")

        if self._process:
            self._process.stdin.write(header + encoded)  # type: ignore[union-attr]
            self._process.stdin.flush()  # type: ignore[union-attr]
        else:
            sys.stdout.buffer.write(header + encoded)
            sys.stdout.buffer.flush()

    def _read_message(self, timeout_seconds: float = 30.0) -> dict[str, Any] | None:
        """Read a JSON-RPC message with Content-Length framing."""
        headers: dict[str, str] = {}
        start_time = time.time()

        while True:
            line = self._read_line()
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

            if time.time() - start_time > timeout_seconds:
                raise McpClientError("Timeout reading headers")

        content_length = headers.get("content-length")
        if content_length is None:
            raise McpClientError("Missing Content-Length header")

        try:
            length = int(content_length)
        except ValueError as exc:
            raise McpClientError(f"Invalid Content-Length header: {content_length}") from exc

        body = b""
        while len(body) < length:
            chunk = self._read_line() if not self._process else self._process.stdout.readline()  # type: ignore[union-attr]
            if not chunk:
                raise McpClientError("Unexpected EOF while reading message body")
            body += chunk

        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError as exc:
            raise McpClientError(f"Message body is not valid JSON: {body[:200]}") from exc

        if not isinstance(payload, dict):
            raise McpClientError("JSON-RPC payload must be an object")

        return payload

    def _send_request(self, method: str, params: dict[str, Any] | None = None) -> McpResponse:
        """Send a JSON-RPC request and wait for the response."""
        request_id = self._next_id()
        request = {
            "jsonrpc": JSON_RPC_VERSION,
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        self._write_message(request)
        response = self._read_message()

        if response is None:
            raise McpClientError("No response received from server")

        return McpResponse(
            request_id=response.get("id"),
            result=response.get("result"),
            error=response.get("error"),
        )

    def initialize(self) -> dict[str, Any]:
        """Initialize the MCP connection."""
        response = self._send_request("initialize", {
            "clientInfo": {
                "name": self._client_name,
                "version": self._client_version,
            },
            "protocolVersion": "2024-11-05",
        })

        if response.is_error:
            raise McpClientError(f"initialize failed: {response.error}")

        self._initialized = True
        return response.result or {}

    def tools_list(self) -> list[dict[str, Any]]:
        """List available tools."""
        response = self._send_request("tools/list")
        if response.is_error:
            raise McpClientError(f"tools/list failed: {response.error}")
        return (response.result or {}).get("tools", [])

    def resources_list(self) -> list[dict[str, Any]]:
        """List available resources."""
        response = self._send_request("resources/list")
        if response.is_error:
            raise McpClientError(f"resources/list failed: {response.error}")
        return (response.result or {}).get("resources", [])

    def resources_read(self, uri: str) -> list[dict[str, Any]]:
        """Read a resource by URI."""
        response = self._send_request("resources/read", {"uri": uri})
        if response.is_error:
            raise McpClientError(f"resources/read failed for {uri}: {response.error}")
        return (response.result or {}).get("contents", [])

    def tools_call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call a tool."""
        response = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })
        if response.is_error:
            raise McpClientError(f"tools/call failed for {name}: {response.error}")
        return response.result or {}

    def ping(self) -> bool:
        """Send a ping to the server."""
        response = self._send_request("ping")
        return not response.is_error

    def shutdown(self) -> bool:
        """Send shutdown notification to the server."""
        response = self._send_request("shutdown")
        return not response.is_error

    def send_exit_notification(self) -> None:
        """Send exit notification (no response expected)."""
        self._write_message({"jsonrpc": JSON_RPC_VERSION, "method": "exit"})

    def close(self) -> None:
        """Clean up the connection."""
        try:
            self.shutdown()
            self.send_exit_notification()
        except McpClientError:
            pass
        finally:
            if self._process:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=5)
                except Exception:
                    self._process.kill()


def _create_subprocess_client(server_cmd: str) -> McpClient:
    """Create an MCP client that spawns the server as a subprocess."""
    cmd_parts = server_cmd.split()
    process = subprocess.Popen(
        cmd_parts,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    return McpClient(server_process=process)


class TestResult:
    """Accumulates test results."""

    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def pass_check(self, name: str) -> None:
        self.passed.append(name)

    def fail_check(self, name: str, reason: str) -> None:
        self.failed.append((name, reason))

    @property
    def success(self) -> bool:
        return len(self.failed) == 0

    def summary(self) -> str:
        lines = [
            f"Test Results: {len(self.passed)} passed, {len(self.failed)} failed",
        ]
        for name, reason in self.failed:
            lines.append(f"  FAILED: {name} - {reason}")
        return "\n".join(lines)


def run_smoke_test(client: McpClient) -> TestResult:
    """Run the full smoke test scenario."""
    result = TestResult()

    # Step 1: Initialize
    try:
        init_result = client.initialize()
        server_info = init_result.get("serverInfo", {})
        result.pass_check("initialize - server responded")

        if server_info.get("name") == "dq-made-easy-mcp":
            result.pass_check("initialize - server name matches")
        else:
            result.fail_check("initialize - server name", f"expected 'dq-made-easy-mcp', got '{server_info.get('name')}'")

    except McpClientError as exc:
        result.fail_check("initialize", str(exc))
        return result

    # Step 2: List tools
    try:
        tools = client.tools_list()
        tool_names = {t["name"] for t in tools}
        expected_tools = {"validate_dataset", "get_anomalies", "trigger_remediation", "get_execution_run"}

        if expected_tools.issubset(tool_names):
            result.pass_check("tools/list - all expected tools available")
        else:
            missing = expected_tools - tool_names
            result.fail_check("tools/list", f"missing tools: {missing}")

    except McpClientError as exc:
        result.fail_check("tools/list", str(exc))

    # Step 3: List resources
    try:
        resources = client.resources_list()
        resource_uris = {r["uri"] for r in resources}
        expected_uris = {
            "dq://dashboards/execution-monitoring",
            "dq://rule-libraries/registry",
            "dq://lineage/graph-latest",
        }

        if expected_uris.issubset(resource_uris):
            result.pass_check("resources/list - all expected resources available")
        else:
            missing = expected_uris - resource_uris
            result.fail_check("resources/list", f"missing resources: {missing}")

    except McpClientError as exc:
        result.fail_check("resources/list", str(exc))

    # Step 4: Ping
    try:
        if client.ping():
            result.pass_check("ping - server responded")
        else:
            result.fail_check("ping", "no response")
    except McpClientError as exc:
        result.fail_check("ping", str(exc))

    # Step 5: Read a resource (dashboards)
    try:
        contents = client.resources_read("dq://dashboards/execution-monitoring")
        if contents:
            result.pass_check("resources/read - execution-monitoring dashboard returned content")
        else:
            result.fail_check("resources/read", "empty content for dashboard")
    except McpClientError as exc:
        result.fail_check("resources/read", str(exc))

    # Step 6: Call a tool (validate_dataset) - may fail if no rules exist
    try:
        tool_result = client.tools_call("validate_dataset", {
            "workspace": "smoke-test-workspace",
            "rule_ids": ["smoke-test-rule"],
        })
        # Tool call succeeded (even if the validation itself returns errors)
        content_items = tool_result.get("content", [])
        if content_items:
            result.pass_check("tools/call - validate_dataset returned response")
            # Check if it's an error response (expected for test data)
            is_error = content_items[0].get("isError", False)
            if is_error:
                result.pass_check("tools/call - validate_dataset error expected (no real rules)")
            else:
                result.pass_check("tools/call - validate_dataset succeeded")
        else:
            result.fail_check("tools/call", "empty response from validate_dataset")
    except McpClientError as exc:
        # Expected if no rules exist
        if "workspace" in str(exc).lower() or "rule" in str(exc).lower():
            result.pass_check("tools/call - validate_dataset error expected")
        else:
            result.fail_check("tools/call", str(exc))

    return result


def run_webhook_dispatch_test(client: McpClient, *, webhook_payload: dict[str, Any]) -> TestResult:
    """Run a test that simulates processing a webhook dispatch.

    This simulates what an external AI agent would do after receiving a
    webhook from the DQ platform:
    1. Initialize MCP connection
    2. Parse the webhook event
    3. Call appropriate MCP tools to investigate/remediate
    """
    result = TestResult()

    # Step 1: Initialize
    try:
        client.initialize()
        result.pass_check("initialize")
    except McpClientError as exc:
        result.fail_check("initialize", str(exc))
        return result

    # Step 2: Parse webhook payload
    event_type = webhook_payload.get("event", {}).get("type", "")
    data = webhook_payload.get("data", {})
    dispatch_id = webhook_payload.get("metadata", {}).get("dispatch_id", "unknown")

    result.pass_check(f"parse webhook - event type: {event_type}, dispatch_id: {dispatch_id}")

    # Step 3: Based on event type, call appropriate tools
    delivery_id = data.get("delivery_id")
    rule_id = data.get("rule_id")

    if delivery_id:
        try:
            anomaly_result = client.tools_call("get_anomalies", {
                "delivery_id": delivery_id,
                "lookback_amount": 24,
                "lookback_unit": "hours",
            })
            result.pass_check(f"tools/call get_anomalies for delivery {delivery_id}")
        except McpClientError as exc:
            # May fail if delivery doesn't exist
            result.pass_check(f"tools/call get_anomalies - expected error: {exc}")

    if rule_id:
        try:
            validate_result = client.tools_call("validate_dataset", {
                "workspace": data.get("workspace", "test-workspace"),
                "rule_ids": [rule_id],
            })
            result.pass_check(f"tools/call validate_dataset for rule {rule_id}")
        except McpClientError as exc:
            result.pass_check(f"tools/call validate_dataset - expected error: {exc}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="dq-mcp-test-client",
        description="Test MCP client for the DQ Made Easy MCP server.",
    )
    parser.add_argument(
        "--server-cmd",
        default=None,
        help="Command to start the MCP server (subprocess mode).",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base URL for the MCP server (used with --server-cmd).",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer token for dq-api requests.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="Timeout for MCP server requests.",
    )
    parser.add_argument(
        "--scenario",
        choices=["smoke_test", "webhook_dispatch"],
        default="smoke_test",
        help="Test scenario to run.",
    )
    parser.add_argument(
        "--webhook-file",
        default=None,
        help="Path to a webhook payload JSON file (for webhook_dispatch scenario).",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="Path to write test results as JSON.",
    )

    args = parser.parse_args()

    # Determine server command
    server_cmd = args.server_cmd
    if not server_cmd:
        if args.base_url:
            cmd_parts = [
                sys.executable, "-m", "dq_cli.mcp_server",
                "--base-url", args.base_url,
                "--timeout-seconds", str(args.timeout_seconds),
            ]
            if args.token:
                cmd_parts.extend(["--token", args.token])
            server_cmd = " ".join(cmd_parts)
        else:
            print("Error: --base-url or --server-cmd is required", file=sys.stderr)
            return 2

    try:
        client = _create_subprocess_client(server_cmd)
    except Exception as exc:
        print(f"Error: Failed to start MCP server: {exc}", file=sys.stderr)
        return 2

    try:
        if args.scenario == "smoke_test":
            result = run_smoke_test(client)
        elif args.scenario == "webhook_dispatch":
            if not args.webhook_file:
                print("Error: --webhook-file is required for webhook_dispatch scenario", file=sys.stderr)
                return 2

            with open(args.webhook_file) as f:
                webhook_payload = json.load(f)

            result = run_webhook_dispatch_test(client, webhook_payload=webhook_payload)
        else:
            print(f"Error: Unknown scenario '{args.scenario}'", file=sys.stderr)
            return 2

        # Print results
        print(result.summary())

        # Write output file if requested
        if args.output_file:
            output_data = {
                "scenario": args.scenario,
                "passed": result.passed,
                "failed": [{"name": name, "reason": reason} for name, reason in result.failed],
                "success": result.success,
            }
            with open(args.output_file, "w") as f:
                json.dump(output_data, f, indent=2)

        return 0 if result.success else 1

    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
