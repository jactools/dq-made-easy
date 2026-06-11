from __future__ import annotations

import base64
import json


def _jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def encode(value: dict[str, object]) -> str:
        raw = json.dumps(value).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


def smoke_auth_headers(*scopes: str) -> dict[str, str]:
    token = _jwt(
        {
            "sub": "user-123",
            "preferred_username": "admin",
            "iss": "http://keycloak.local:8080/realms/jaccloud",
            "aud": ["dq-rules-ui"],
            "scope": " ".join(scopes),
        }
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Kong-Request-Id": "test-request-id",
    }
