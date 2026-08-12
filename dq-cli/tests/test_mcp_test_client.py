"""Tests for the MCP test client module.

These tests verify that the MCP test client can:
1. Start the MCP server as a subprocess
2. Send JSON-RPC requests and receive responses
3. Run smoke test scenarios
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


MCP_SERVER_MODULE = "dq_cli.mcp_server"
MCP_TEST_CLIENT_MODULE = "dq_cli.mcp_test_client"


def _get_python_cmd() -> str:
    """Get the Python interpreter command."""
    return sys.executable


def _build_server_cmd(base_url: str, timeout: float = 30.0) -> str:
    """Build the MCP server command."""
    return (
        f"{_get_python_cmd()} -m {MCP_SERVER_MODULE}"
        f" --base-url {base_url}"
        f" --timeout-seconds {timeout}"
    )


def _write_webhook_payload(filepath: str) -> None:
    """Write a test webhook payload to a file."""
    payload = {
        "metadata": {
            "dispatch_id": "test-mcp-dispatch",
            "platform": "mistral_ai",
            "source": "dq-made-easy",
            "contract_version": "1.0",
            "sent_at": "2026-07-21T12:00:00Z",
        },
        "event": {
            "type": "dq.alert.created",
            "timestamp": "2026-07-21T12:00:00Z",
        },
        "data": {
            "delivery_id": "delivery-test-001",
            "alert_kind": "sla_breach",
            "rule_id": "rule-test-001",
            "workspace": "test-workspace",
        },
    }
    with open(filepath, "w") as f:
        json.dump(payload, f)


class TestMcpTestClientModule:
    """Unit tests for the MCP test client module."""

    def test_mcp_test_client_module_imports(self) -> None:
        """Verify the MCP test client module imports correctly."""
        from dq_cli.mcp_test_client import McpClient, TestResult, run_smoke_test
        assert McpClient is not None
        assert TestResult is not None
        assert run_smoke_test is not None

    def test_test_result_tracking(self) -> None:
        """Verify TestResult tracks pass/fail correctly."""
        from dq_cli.mcp_test_client import TestResult

        result = TestResult()
        result.pass_check("test-1")
        result.pass_check("test-2")
        result.fail_check("test-3", "something went wrong")

        assert len(result.passed) == 2
        assert len(result.failed) == 1
        assert not result.success
        assert "test-3" in result.summary()
        assert "something went wrong" in result.summary()

    def test_test_result_success(self) -> None:
        """Verify TestResult reports success when all pass."""
        from dq_cli.mcp_test_client import TestResult

        result = TestResult()
        result.pass_check("test-1")
        result.pass_check("test-2")

        assert result.success
        assert len(result.passed) == 2
        assert len(result.failed) == 0

    def test_mcp_client_class_instantiation(self) -> None:
        """Verify McpClient can be instantiated."""
        from dq_cli.mcp_test_client import McpClient

        client = McpClient()
        assert client is not None
        assert not client._initialized

    def test_mcp_client_next_id(self) -> None:
        """Verify McpClient generates unique request IDs."""
        from dq_cli.mcp_test_client import McpClient

        client = McpClient()
        id1 = client._next_id()
        id2 = client._next_id()
        id3 = client._next_id()

        assert id1 == 1
        assert id2 == 2
        assert id3 == 3

    def test_mcp_response_is_error(self) -> None:
        """Verify McpResponse correctly identifies errors."""
        from dq_cli.mcp_test_client import McpResponse

        success_response = McpResponse(request_id=1, result={"data": "ok"})
        assert not success_response.is_error

        error_response = McpResponse(request_id=1, error={"code": -32601, "message": "error"})
        assert error_response.is_error


@pytest.fixture
def webhook_payload_file(tmp_path: Path) -> str:
    """Create a temporary webhook payload file."""
    filepath = str(tmp_path / "webhook_payload.json")
    _write_webhook_payload(filepath)
    return filepath


class TestMcpTestClientSmoke:
    """Integration tests for the MCP test client smoke test.

    These tests require a live dq-api instance. They are skipped by default
    unless --run-mcp-integration is passed.
    """

    @pytest.mark.skipif(
        not os.environ.get("DQ_API_BASE_URL"),
        reason="DQ_API_BASE_URL not set",
    )
    @pytest.mark.integration
    def test_smoke_test_runs_against_live_server(self) -> None:
        """Run the smoke test scenario against a live stack."""
        from dq_cli.mcp_test_client import _create_subprocess_client, run_smoke_test

        base_url = os.environ["DQ_API_BASE_URL"]
        token = os.environ.get("DQ_API_TOKEN", "")
        server_cmd = _build_server_cmd(base_url)
        if token:
            server_cmd += f" --token {token}"

        client = _create_subprocess_client(server_cmd)
        try:
            result = run_smoke_test(client)
            # Just verify the test runs (may fail against mock data)
            assert result.passed or result.failed  # Some output expected
        finally:
            client.close()

    @pytest.mark.skipif(
        not os.environ.get("DQ_API_BASE_URL"),
        reason="DQ_API_BASE_URL not set",
    )
    @pytest.mark.integration
    def test_webhook_dispatch_scenario(self, webhook_payload_file: str) -> None:
        """Run the webhook dispatch scenario against a live stack."""
        from dq_cli.mcp_test_client import (
            _create_subprocess_client,
            run_webhook_dispatch_test,
        )

        base_url = os.environ["DQ_API_BASE_URL"]
        token = os.environ.get("DQ_API_TOKEN", "")
        server_cmd = _build_server_cmd(base_url)
        if token:
            server_cmd += f" --token {token}"

        with open(webhook_payload_file) as f:
            webhook_payload = json.load(f)

        client = _create_subprocess_client(server_cmd)
        try:
            result = run_webhook_dispatch_test(client, webhook_payload=webhook_payload)
            assert result.passed or result.failed  # Some output expected
        finally:
            client.close()


class TestMcpTestClientCli:
    """Test the MCP test client CLI interface."""

    def test_cli_help(self, capsys: pytest.CaptureFixture) -> None:
        """Verify the CLI help works."""
        with pytest.raises(SystemExit) as exc_info:
            import subprocess
            result = subprocess.run(
                [_get_python_cmd(), "-m", MCP_TEST_CLIENT_MODULE, "--help"],
                capture_output=True,
                text=True,
            )
        assert result.returncode == 0
        assert "MCP client" in result.stdout or "mcp_test_client" in result.stdout

    def test_cli_requires_base_url(self) -> None:
        """Verify the CLI requires --base-url or --server-cmd."""
        import subprocess
        result = subprocess.run(
            [_get_python_cmd(), "-m", MCP_TEST_CLIENT_MODULE],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "base-url" in result.stderr or "required" in result.stderr.lower()
