from __future__ import annotations

import base64
import json

import pytest


pytestmark = pytest.mark.asyncio


def _make_bearer_token(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.sig"


async def test_demo_endpoint_returns_snake_case(async_client):
    payload = {
        "sub": "test-user",
        "aud": "dq-rules-ui",
        "iss": "http://keycloak.local:8080/realms/jaccloud",
        "exp": 9999999999,
        "scope": "dq:rules:read",
    }
    token = _make_bearer_token(payload)
    headers = {"Authorization": f"Bearer {token}"}

    response = await async_client.get("/api/rulebuilder/v1/demo/snake", headers=headers)
    assert response.status_code == 200
    body = response.json()
    # Keys should be snake_case due to SnakeModel aliasing
    assert "camel_case_field" in body
    assert "another_field" in body
    assert body["camel_case_field"] == "value"
    assert body["another_field"] == 123
