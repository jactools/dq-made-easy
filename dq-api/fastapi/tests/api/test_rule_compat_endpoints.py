from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_rules_repository
from app.main import app

client = TestClient(app)


def _jwt(payload: dict[str, object]) -> str:
    import base64
    import json

    header = {"alg": "none", "typ": "JWT"}

    def encode(value: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("utf-8").rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


def _auth_headers(*scopes: str) -> dict[str, str]:
    token = _jwt(
        {
            "sub": "user-123",
            "preferred_username": "admin",
            "iss": "http://keycloak.local:8080/realms/jaccloud",
            "aud": ["dq-rules-ui"],
            "scope": " ".join(scopes),
        }
    )
    return {"Authorization": f"Bearer {token}"}


def setup_module() -> None:
    get_settings.cache_clear()


def teardown_module() -> None:
    get_settings.cache_clear()


def test_aliases_resolve_returns_manual_and_unresolved(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    class _CatalogRepo:
        def list_attributes_catalog(self, _workspace):
            return [
                SimpleNamespace(name="Email", type="string", id="attr-email", data_object_id=None),
                SimpleNamespace(name="Status", type="string", id="attr-status", data_object_id="catalog"),
            ]

    app.dependency_overrides[get_data_catalog_repository] = lambda: _CatalogRepo()

    try:
        response = client.post(
            "/api/rulebuilder/v1/rules/aliases/resolve",
            headers={**_auth_headers("dq:rules:write"), "Content-Type": "application/json"},
            json={
                "aliases": ["email", "country"],
                "manualMappings": {"email": "attr-email"},
            },
        )
    finally:
        app.dependency_overrides.pop(get_data_catalog_repository, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolutions"]["email"]["source"] == "manual"
    assert payload["resolutions"]["country"]["source"] == "unresolved"


def test_rule_versions_returns_array(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    class _RulesRepo:
        async def list_rule_versions(self, rule_id, limit=20, offset=0):
            assert rule_id == "rule-email-format"
            assert limit == 20
            assert offset == 0
            return {"versions": [{"id": "rv-1", "versionNumber": 2, "isCurrentVersion": True}]}

    app.dependency_overrides[get_rules_repository] = lambda: _RulesRepo()

    try:
        response = client.get(
            "/api/rulebuilder/v1/rules/rule-email-format/versions",
            headers=_auth_headers("dq:rules:read"),
        )
    finally:
        app.dependency_overrides.pop(get_rules_repository, None)

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["versions"], list)
    assert payload["versions"][0]["id"] == "rv-1"
    assert payload["versions"][0]["version_number"] == 2