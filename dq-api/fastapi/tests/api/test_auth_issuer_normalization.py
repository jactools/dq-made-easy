from urllib.parse import parse_qs
from urllib.parse import urlparse

import pytest

from app.api.v1.endpoints import auth as auth_endpoints
from app.core.config import get_settings
from app.core.dependencies import get_app_config_repository
from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository


@pytest.mark.parametrize(
    ("malformed_public_issuer", "canonical_public_issuer", "internal_issuer"),
    [
        (
            "http://https//keycloak.jac.dot:9444/realms/jaccloud",
            "https://keycloak.jac.dot:9444/realms/jaccloud",
            "http://keycloak:8080/realms/jaccloud",
        ),
        (
            "http://https//dq-made-easy.example/iam/realms/jaccloud",
            "https://dq-made-easy.example/iam/realms/jaccloud",
            "http://keycloak:8080/realms/jaccloud",
        ),
    ],
)
def test_auth_redirect_normalizes_malformed_public_issuer(
    client,
    monkeypatch: pytest.MonkeyPatch,
    malformed_public_issuer: str,
    canonical_public_issuer: str,
    internal_issuer: str,
) -> None:
    client.app.dependency_overrides[get_app_config_repository] = lambda: InMemoryAppConfigRepository()
    malformed_discovery_endpoint = "http://https//keycloak.jac.dot:8080/realms/jaccloud/protocol/openid-connect/auth"

    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", malformed_public_issuer)
    monkeypatch.setenv("SSO_INTERNAL_ISSUER_URL", internal_issuer)
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    monkeypatch.setenv("OIDC_REDIRECT_BASE_URL", "https://api.example.test")
    get_settings.cache_clear()

    async def fake_fetch(backend_issuer: str) -> dict[str, object]:
        if backend_issuer == canonical_public_issuer:
            raise auth_endpoints.HTTPException(status_code=503, detail="OIDC discovery failed")
        if backend_issuer == internal_issuer:
            return {
                "authorization_endpoint": malformed_discovery_endpoint,
            }
        raise AssertionError(f"Unexpected issuer: {backend_issuer}")

    monkeypatch.setattr(auth_endpoints, "_fetch_oidc_metadata", fake_fetch)

    response = client.get(
        "/api/auth/v1/redirect?frontend=https://frontend.example/",
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)

    assert location.startswith(f"{canonical_public_issuer}/protocol/openid-connect/auth")
    assert query["client_id"] == ["dq-rules-ui"]
    assert query["redirect_uri"] == ["https://api.example.test/auth/v1/callback"]