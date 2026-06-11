from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

import entrypoint


def _make_token(*, sub: str = "alice") -> str:
    payload = {
        "sub": sub,
        "exp": int(time.time()) + 3600,
        "iss": "https://keycloak.example.test/realms/dq",
    }

    header = base64.urlsafe_b64encode(b'{"alg": "none", "typ": "JWT"}').rstrip(b"=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    signature = b"signature"
    return f"{header.decode()}.{body.decode()}.{signature.decode()}"


@dataclass
class _FakeAuditLogger:
    events: list[dict[str, object]]

    async def record_existing_audit_event(self, **kwargs):
        self.events.append(kwargs)


class _FakeAgent:
    async def run(self, prompt: str, context: dict[str, object] | None = None):
        return {
            "response": f"ack: {prompt}",
            "tool_calls": [
                {
                    "tool_name": "dq_connector.configure",
                    "parameters": {"api_key": "secret"},
                    "result": {"configured": True},
                    "duration_ms": 12.5,
                    "success": True,
                }
            ],
            "metadata": {"context_size": len(context or {})},
        }


class _FakeFactory:
    def create_general_agent(self, session_id: str):
        return _FakeAgent()

    def create_connector_agent(self, session_id: str):
        return _FakeAgent()

    def create_rule_agent(self, session_id: str):
        return _FakeAgent()

    def create_steward_agent(self, session_id: str):
        return _FakeAgent()


@pytest.fixture
def client() -> TestClient:
    return TestClient(entrypoint.app)


@pytest.fixture
def auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token()}"}


def test_run_agent_records_existing_audit_event(client: TestClient, auth_header: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    fake_audit_logger = _FakeAuditLogger(events=[])
    monkeypatch.setattr(entrypoint, "get_audit_logger", lambda: fake_audit_logger)
    monkeypatch.setattr(entrypoint, "_get_agent_factory", lambda: _FakeFactory())

    response = client.post(
        "/api/llm/v1/agent/run",
        headers=auth_header,
        json={
            "prompt": "hello",
            "agent_type": "general",
            "session_id": "session-123",
            "context": {"workspace": "main"},
        },
    )

    assert response.status_code == 200
    assert fake_audit_logger.events
    event = fake_audit_logger.events[0]
    assert event["action"] == "run_agent"
    assert event["endpoint"] == "/api/llm/v1/agent/run"
    assert event["method"] == "POST"
    assert event["response_type"] == "agent_response"
    assert event["success"] is True
    assert event["correlation_id"] == "session-123"
    assert event["parameters"]["prompt"] == "hello"
    assert event["parameters"]["tool_calls"][0]["tool_name"] == "dq_connector.configure"
    assert event["result"]["response"] == "ack: hello"
