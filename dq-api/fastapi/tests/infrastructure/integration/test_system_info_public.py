"""Integration policy: system-info remains publicly accessible."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

pytestmark = pytest.mark.integration
client = TestClient(app)


def test_system_info_is_public_integration(live_db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = live_db_url
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get("/api/system/v1/system-info")

    assert response.status_code == 200
    payload = response.json()
    assert "api" in payload
    assert "database" in payload
