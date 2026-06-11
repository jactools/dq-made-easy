from __future__ import annotations

import os

from app.core.config import get_settings


APP_CONFIG_ENCRYPTION_KEY = "i0aU2BE0dzqEVAWxfEsvffw5zw93FjFZrr24RPVyo8c="

# Ensure tests use the host-accessible Postgres host and set BEFORE app import.
# Use the host-local dq database URL, not the internal container-network URL.
# Respect any externally provided DQ_DB_LOCAL_URL; otherwise build one from DQ_DB_HOST.
# Disable python-dotenv to avoid loading repository .env values during tests.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
_database_url_explicit = "DQ_DB_LOCAL_URL" in os.environ
os.environ.setdefault("DQ_DB_HOST", os.environ.get("DQ_DB_HOST", "dq-db.jac.dot"))
if not _database_url_explicit:
    os.environ["DQ_DB_LOCAL_URL"] = f"postgresql://postgres:postgres@{os.environ['DQ_DB_HOST']}:5432/dq"
    os.environ["DQ_TEST_DEFAULT_DATABASE_URL"] = "1"
os.environ["REQUIRE_DATABASE"] = "false"
os.environ["SSO_ENABLED"] = "true"
os.environ["SSO_PUBLIC_ISSUER_URL"] = "http://keycloak.local:8080/realms/jaccloud"
os.environ["SSO_CLIENT_ID"] = "dq-rules-ui"
os.environ["NATURAL_LANGUAGE_DRAFT_QUEUE_KEY"] = ""

# Disable OpenTelemetry exporters during tests to avoid background exporter
# threads emitting logs after the test runner closes file handles.
# Using the OTEL_* env vars prevents the SDK from starting network exporters.
os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")
os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "")
os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "")
os.environ["APP_CONFIG_ENCRYPTION_KEY"] = APP_CONFIG_ENCRYPTION_KEY

# Clear cached settings so later imports pick up the patched env.
get_settings.cache_clear()
import pytest
import pytest_asyncio


@pytest.fixture(autouse=True)
def _force_kong_marker_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests simulate going through Kong.

    The application enforces that all /v1 and /api/v1 requests carry a Kong marker
    header. TestClient calls the app directly, so we inject the header by default.
    """

    try:
        from fastapi.testclient import TestClient
    except Exception:
        return

    original_request = TestClient.request

    def patched_request(self, method, url, **kwargs):
        headers = dict(kwargs.get("headers") or {})
        headers.setdefault("X-Kong-Request-Id", "test-request-id")
        kwargs["headers"] = headers
        return original_request(self, method, url, **kwargs)

    monkeypatch.setattr(TestClient, "request", patched_request, raising=True)


@pytest.fixture(autouse=True)
def _restore_app_dependency_overrides() -> None:
    from app.main import app

    original_overrides = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-openmetadata-contract-cache-integration",
        action="store_true",
        default=False,
        help=(
            "Run opt-in OpenMetadata contract cache integration tests. "
            "These tests are skipped by default."
        ),
    )


_DISABLED_FAILING_TEST_NODEID_PREFIXES = (
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_mark = pytest.mark.skip(reason="Temporarily disabled while measuring suite coverage without known failing tests.")

    for item in items:
        if any(item.nodeid.startswith(prefix) for prefix in _DISABLED_FAILING_TEST_NODEID_PREFIXES):
            item.add_marker(skip_mark)


# `pytest_plugins` moved to top-level `conftest.py` to support newer pytest
# versions (defining `pytest_plugins` in a non-top-level conftest is no
# longer supported). See /conftest.py in the repository root.

import base64
import json
from httpx import ASGITransport, AsyncClient
from fastapi.testclient import TestClient


def _jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def encode(value: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("utf-8").rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


@pytest.fixture(autouse=True)
def sso_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure SSO env is set and cached settings cleared for each test."""
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", os.environ.get("SSO_PUBLIC_ISSUER_URL", "http://keycloak.jac.dot:8080/realms/jaccloud"))
    monkeypatch.setenv("SSO_CLIENT_ID", os.environ.get("SSO_CLIENT_ID", "dq-rules-ui"))
    monkeypatch.setenv("APP_CONFIG_ENCRYPTION_KEY", os.environ.get("APP_CONFIG_ENCRYPTION_KEY", APP_CONFIG_ENCRYPTION_KEY))
    monkeypatch.setenv("GX_EXCEPTION_STORAGE_BACKEND", "repository")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def auth_headers() -> callable:
    """Return a function that builds Authorization headers with requested scopes.

    The returned function accepts optional keyword args `sub` and
    `preferred_username` so tests can simulate different authenticated users.
    """

    def _make(
        *scopes: str,
        sub: str = "user-admin",
        preferred_username: str = "admin",
        email: str | None = None,
    ) -> dict[str, str]:
        payload: dict[str, object] = {
            "sub": sub,
            "preferred_username": preferred_username,
            "iss": os.environ.get("SSO_PUBLIC_ISSUER_URL", "http://keycloak.jac.dot:8080/realms/jaccloud"),
            "aud": ["dq-rules-ui"],
            "scope": " ".join(scopes),
        }
        if email is not None:
            payload["email"] = email
        token = _jwt(
            payload
        )
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
def client() -> TestClient:
    """Provide a TestClient instance for tests (uses app from app.main)."""
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    """Provide an AsyncClient instance for API tests.

    The client includes the Kong marker header by default so routes behind
    gateway-header checks behave consistently with TestClient-based tests.
    """
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"X-Kong-Request-Id": "test-request-id"},
    ) as c:
        yield c


@pytest.fixture
def find_user_by_query(client: TestClient, auth_headers: callable) -> callable:
    """Return a helper that returns the first user id matching a query or None."""

    def _fn(query: str) -> str | None:
        resp = client.get(
            f"/admin/v1/users?q={query}&sort=name&order=asc&page=1&limit=10",
            headers=auth_headers("dq:admin:read"),
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        items = data.get("data") or []
        return items[0]["id"] if items else None

    return _fn