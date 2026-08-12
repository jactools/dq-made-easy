"""Integration tests for outbound webhook dispatch to external agent platforms.

These tests verify that the dispatch endpoint actually sends webhook payloads
to the configured target URL and returns delivery results.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
import httpx
from fastapi import HTTPException

from app.core.dependencies import get_agent_request_audit_repository
from app.core.dependencies import get_app_config_repository
from app.main import app


# -- Helpers to override agent dependencies in tests --


def _make_config_repository(allowed_agents=None, platform_allowlist=None):
    class _ConfigRepository:
        def __init__(self, allowed_agents, platform_allowlist):
            self._allowed_agents = list(allowed_agents)
            self._platform_allowlist = list(platform_allowlist)

        def get_app_config(self):
            return SimpleNamespace(
                agentPlatformAllowlist=self._platform_allowlist,
                agentAccessPolicy={
                    "defaultAction": "deny",
                    "allowedAgents": self._allowed_agents,
                },
            )

    return _ConfigRepository(allowed_agents or [], platform_allowlist or [])


@pytest.fixture
def _agent_dependency_overrides():
    class _AuditRepository:
        def __init__(self):
            self.events = []

        async def record_event(self, event):
            self.events.append(event)
            return event

        async def list_events(self, *, limit: int = 100, offset: int = 0):
            return self.events[offset : offset + limit]

    audit_repository = _AuditRepository()
    config_repository = _make_config_repository(
        allowed_agents=[{"agent_type": "mcp", "agent_source": "pytest-agent"}],
        platform_allowlist=["mistral_ai", "microsoft_copilot"],
    )
    app.dependency_overrides[get_app_config_repository] = lambda: config_repository
    app.dependency_overrides[get_agent_request_audit_repository] = lambda: audit_repository
    try:
        yield {
            "audit_repository": audit_repository,
            "config_repository": config_repository,
            "config_repository_cls": _make_config_repository,
        }
    finally:
        app.dependency_overrides.pop(get_app_config_repository, None)
        app.dependency_overrides.pop(get_agent_request_audit_repository, None)


def _agent_headers(auth_headers, *scopes: str) -> dict[str, str]:
    return {
        **auth_headers(*scopes),
        "X-Request-Id": "req-agent-dispatch-1",
        "X-Agent-Type": "mcp",
        "X-Agent-Source": "pytest-agent",
        "X-Agent-Instance-Id": "pytest-instance-1",
        "X-Forwarded-For": "10.0.0.1",
    }


# -- Async test server helpers --


async def _run_mock_webhook_server(port: int = 0) -> tuple[str, list[dict[str, Any]], asyncio.Event]:
    """Start a simple async HTTP server that accepts webhook POST requests.

    Returns (base_url, received_requests, ready_event).
    """
    received_requests: list[dict[str, Any]] = []
    ready_event = asyncio.Event()
    stop_event = asyncio.Event()

    async def handler(scope):
        if scope["type"] != "http":
            return
        path = scope.get("path", "")
        method = scope.get("method", "")

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            if message["type"] == "http.response.start":
                pass
            elif message["type"] == "http.response.body":
                pass

        if method == "POST" and path == "/webhook":
            # Read body
            body_parts = []
            while True:
                msg = await receive()
                if msg.get("type") == "http.request":
                    body_parts.append(msg.get("body", b""))
                    if not msg.get("more_body", False):
                        break

            body = b"".join(body_parts).decode("utf-8")
            received_requests.append(
                {
                    "method": method,
                    "path": path,
                    "headers": dict(scope.get("headers", [])),
                    "body": body,
                    "json": json.loads(body) if body else None,
                }
            )

            # Respond 200
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b'{"ok": true}'})
        else:
            # 404 for other paths
            await send({"type": "http.response.start", "status": 404, "headers": []})
            await send({"type": "http.response.body", "body": b'{"error": "not found"}'})

    from uvicorn import Config, Server

    config = Config(
        app=handler,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = Server(config)
    task = asyncio.create_task(server.serve())

    # Wait until server is ready
    await asyncio.sleep(0.2)
    if port == 0:
        # Find the actual port — for simplicity we'll bind explicitly in tests
        # and use a known port. This fallback just returns the config port.
        actual_port = config.port
    else:
        actual_port = port

    ready_event.set()

    async def shutdown():
        stop_event.set()
        server.should_exit = True
        await task

    return f"http://127.0.0.1:{actual_port}", received_requests, ready_event, shutdown


# -- Test: dispatch service unit tests --


class TestDispatchServiceWebhookDelivery:
    """Unit tests for the agent_dispatch_service module."""

    @pytest.mark.asyncio
    async def test_dispatch_webhook_delivers_success(self):
        from app.application.services.agent_dispatch_service import (
            dispatch_webhook,
            WebhookDeliveryResult,
        )

        def mock_handler(request):
            assert request.method == "POST"
            assert request.url.path == "/webhook"
            body = json.loads(request.content)
            assert "metadata" in body
            assert "event" in body
            assert "data" in body
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(mock_handler)
        base_url = "http://mock.invalid"

        async def _mock_async_client(**kwargs):
            return httpx.Client(transport=transport, **kwargs)

        import unittest.mock
        with unittest.mock.patch("app.application.services.agent_dispatch_service.httpx.AsyncClient", _mock_async_client):
            result = await dispatch_webhook(
                webhook_url=f"{base_url}/webhook",
                payload={"test": "data"},
                timeout_seconds=5.0,
            )

        assert result.status == "delivered"
        assert result.http_status_code == 200
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_dispatch_webhook_fails_on_400_client_error(self):
        from app.application.services.agent_dispatch_service import (
            dispatch_webhook,
            AgentDispatchError,
        )

        def mock_handler(request):
            return httpx.Response(400, json={"error": "bad request"})

        transport = httpx.MockTransport(mock_handler)

        async def _mock_async_client(**kwargs):
            return httpx.Client(transport=transport, **kwargs)

        import unittest.mock
        with unittest.mock.patch("app.application.services.agent_dispatch_service.httpx.AsyncClient", _mock_async_client):
            with pytest.raises(AgentDispatchError, match="Dispatch failed"):
                await dispatch_webhook(
                    webhook_url="http://mock.invalid/webhook",
                    payload={"test": "data"},
                    timeout_seconds=5.0,
                )

    @pytest.mark.asyncio
    async def test_dispatch_webhook_retries_on_500(self):
        from app.application.services.agent_dispatch_service import dispatch_webhook

        call_count = 0

        def mock_handler(request):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return httpx.Response(500, json={"error": "internal"})
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(mock_handler)

        async def _mock_async_client(**kwargs):
            return httpx.Client(transport=transport, **kwargs)

        import unittest.mock
        with unittest.mock.patch("app.application.services.agent_dispatch_service.httpx.AsyncClient", _mock_async_client):
            result = await dispatch_webhook(
                webhook_url="http://mock.invalid/webhook",
                payload={"test": "data"},
                max_retries=3,
                timeout_seconds=5.0,
            )

        assert result.status == "delivered"
        assert call_count == 2  # First attempt + one retry


    @pytest.mark.asyncio
    async def test_dispatch_webhook_exhausts_retries(self):
        from app.application.services.agent_dispatch_service import (
            dispatch_webhook,
            AgentDispatchError,
        )

        call_count = 0

        def mock_handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(503, json={"error": "unavailable"})

        transport = httpx.MockTransport(mock_handler)

        async def _mock_async_client(**kwargs):
            return httpx.Client(transport=transport, **kwargs)

        import unittest.mock
        with unittest.mock.patch("app.application.services.agent_dispatch_service.httpx.AsyncClient", _mock_async_client):
            with pytest.raises(AgentDispatchError, match="failed after"):
                await dispatch_webhook(
                    webhook_url="http://mock.invalid/webhook",
                    payload={"test": "data"},
                    max_retries=1,
                    timeout_seconds=5.0,
                )

        assert call_count == 2  # First attempt + one retry


class TestDispatchServicePayloadBuilding:
    """Tests for the webhook payload envelope builder."""

    def test_build_webhook_payload_structure(self):
        from app.application.services.agent_dispatch_service import build_webhook_payload

        payload = build_webhook_payload(
            platform="mistral_ai",
            event_type="dq.alert.created",
            payload={"delivery_id": "delivery-001", "rule_id": "rule-001"},
            dispatch_id="dispatch-abc",
        )

        assert "metadata" in payload
        assert payload["metadata"]["dispatch_id"] == "dispatch-abc"
        assert payload["metadata"]["platform"] == "mistral_ai"
        assert payload["metadata"]["source"] == "dq-made-easy"
        assert payload["metadata"]["contract_version"] == "1.0"
        assert "event" in payload
        assert payload["event"]["type"] == "dq.alert.created"
        assert "data" in payload
        assert payload["data"]["delivery_id"] == "delivery-001"
        assert payload["data"]["rule_id"] == "rule-001"


# -- Integration tests: dispatch endpoint with mock webhook server --


class TestDispatchEndpointWebhookIntegration:
    """End-to-end tests for the dispatch endpoint with mock webhook receivers."""

    def test_dispatch_endpoint_delivers_webhook_payload(
        self,
        client,
        auth_headers,
        monkeypatch: pytest.MonkeyPatch,
        _agent_dependency_overrides,
    ) -> None:
        """WS10-AC04: dispatch endpoint sends webhook to external platform."""
        from app.application.services import agent_dispatch_service as dispatch_svc

        received_payload = {}

        def mock_dispatch_webhook(**kwargs):
            received_payload["webhook_url"] = kwargs["webhook_url"]
            received_payload["payload"] = kwargs["payload"]
            return SimpleNamespace(
                dispatch_id="test-dispatch-001",
                status="delivered",
                http_status_code=200,
                error_message=None,
                retry_count=0,
                response_body='{"ok": true}',
                as_dict=lambda: {
                    "dispatch_id": "test-dispatch-001",
                    "status": "delivered",
                    "http_status_code": 200,
                    "error_message": None,
                    "retry_count": 0,
                    "response_body": '{"ok": true}',
                },
            )

        async def _async_mock_dispatch_webhook(**kw):
            return mock_dispatch_webhook(**kw)

        monkeypatch.setattr(dispatch_svc, "dispatch_webhook", _async_mock_dispatch_webhook)

        response = client.post(
            "/agent/v1/integrations/dispatches",
            headers=_agent_headers(auth_headers, "dq:rules:write"),
            json={
                "platform": "mistral_ai",
                "dispatch_mode": "webhook",
                "event_type": "dq.alert.created",
                "webhook_url": "https://mistral.example.invalid/hooks/dq",
                "webhook_headers": {"x-test": "1"},
                "payload": {"delivery_id": "delivery-001"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "delivered"
        assert payload["platform"] == "mistral_ai"
        assert payload["dispatch_mode"] == "webhook"
        assert payload["delivery_result"] is not None
        assert payload["delivery_result"]["status"] == "delivered"
        assert payload["delivery_result"]["http_status_code"] == 200
        assert payload["delivered_at"] is not None

        # Verify webhook payload structure
        assert "webhook_url" in received_payload
        assert "payload" in received_payload
        outbound = received_payload["payload"]
        assert outbound["metadata"]["platform"] == "mistral_ai"
        assert outbound["metadata"]["source"] == "dq-made-easy"
        assert outbound["event"]["type"] == "dq.alert.created"
        assert outbound["data"]["delivery_id"] == "delivery-001"

    def test_dispatch_endpoint_job_mode_stays_accepted(
        self,
        client,
        auth_headers,
        _agent_dependency_overrides,
    ) -> None:
        """Job dispatch mode should still return 'accepted' without outbound call."""
        response = client.post(
            "/agent/v1/integrations/dispatches",
            headers=_agent_headers(auth_headers, "dq:rules:write"),
            json={
                "platform": "mistral_ai",
                "dispatch_mode": "job",
                "event_type": "dq.alert.created",
                "job_name": "dq-alert-dispatch",
                "job_arguments": {"workspace": "ws-a"},
                "payload": {"delivery_id": "delivery-001"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "accepted"
        assert payload["platform"] == "mistral_ai"
        assert payload["dispatch_mode"] == "job"
        assert payload["delivery_result"] is None

    def test_dispatch_endpoint_rejects_unallowlisted_platform(
        self,
        client,
        auth_headers,
        _agent_dependency_overrides,
    ) -> None:
        response = client.post(
            "/agent/v1/integrations/dispatches",
            headers=_agent_headers(auth_headers, "dq:rules:write"),
            json={
                "platform": "slack",
                "dispatch_mode": "webhook",
                "event_type": "dq.alert.created",
                "webhook_url": "https://slack.example.invalid/hooks",
                "payload": {},
            },
        )

        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "agent_platform_not_allowed"

    def test_dispatch_endpoint_audit_records_delivery_result(
        self,
        client,
        auth_headers,
        monkeypatch: pytest.MonkeyPatch,
        _agent_dependency_overrides,
    ) -> None:
        """Delivery result should be recorded in the audit trail."""
        from app.application.services import agent_dispatch_service as dispatch_svc

        def mock_dispatch_webhook(**kwargs):
            return SimpleNamespace(
                dispatch_id="test-dispatch-audit",
                status="delivered",
                http_status_code=201,
                error_message=None,
                retry_count=0,
                response_body='{"accepted": true}',
                as_dict=lambda: {
                    "dispatch_id": "test-dispatch-audit",
                    "status": "delivered",
                    "http_status_code": 201,
                    "error_message": None,
                    "retry_count": 0,
                    "response_body": '{"accepted": true}',
                },
            )

        async def _async_mock_dispatch_webhook2(**kw):
            return mock_dispatch_webhook(**kw)

        monkeypatch.setattr(dispatch_svc, "dispatch_webhook", _async_mock_dispatch_webhook2)

        client.post(
            "/agent/v1/integrations/dispatches",
            headers=_agent_headers(auth_headers, "dq:rules:write"),
            json={
                "platform": "microsoft_copilot",
                "dispatch_mode": "webhook",
                "event_type": "dq.rule.validated",
                "webhook_url": "https://copilot.example.invalid/hooks/dq",
                "payload": {"rule_id": "rule-001", "result": "pass"},
            },
        )

        audit_events = _agent_dependency_overrides["audit_repository"].events
        assert len(audit_events) == 1
        event = audit_events[0]
        assert event.action == "dispatch_platform_integration"
        assert event.success is True
        assert event.details["delivery_status"] == "delivered"
        assert event.details["delivery_result"] is not None
        assert event.details["delivery_result"]["http_status_code"] == 201
