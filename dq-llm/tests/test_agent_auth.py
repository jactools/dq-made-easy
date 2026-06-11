import base64
import json
import time

from fastapi.testclient import TestClient

from entrypoint import app


def _make_token(*, sub: str = "alice", scope: str = "dq:rules:read") -> str:
    payload = {
        "sub": sub,
        "scope": scope,
        "exp": int(time.time()) + 3600,
        "iss": "https://keycloak.example.test/realms/dq",
    }

    header = base64.urlsafe_b64encode(b'{"alg": "none", "typ": "JWT"}').rstrip(b"=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    signature = b"signature"
    return f"{header.decode()}.{body.decode()}.{signature.decode()}"


def test_agent_health_requires_bearer_token():
    client = TestClient(app)

    response = client.get("/api/llm/v1/agent/health")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"


def test_agent_health_accepts_valid_bearer_token():
    client = TestClient(app)

    response = client.get(
        "/api/llm/v1/agent/health",
        headers={"Authorization": f"Bearer {_make_token()}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] is True
