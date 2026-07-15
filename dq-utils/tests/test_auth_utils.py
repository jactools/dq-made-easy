import os
import sys
import importlib.util
import types
import logging
import pytest


# Make local source importable
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(ROOT_DIR, "dq-utils", "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# Load module directly from file to avoid package-level side-effects
mod_path = os.path.join(SRC_DIR, "dq_utils", "auth_utils.py")
# Ensure a dq_utils package exists in sys.modules so dataclasses and relative
# module-level references resolve correctly when loading the module.
pkg = types.ModuleType("dq_utils")
pkg.__path__ = [os.path.join(SRC_DIR, "dq_utils")]
sys.modules["dq_utils"] = pkg

spec = importlib.util.spec_from_file_location("dq_utils.auth_utils", mod_path)
auth_utils = importlib.util.module_from_spec(spec)
# Ensure the module is present in sys.modules under its intended name so
# decorators (dataclasses) can resolve module references during class creation.
sys.modules[spec.name] = auth_utils
assert spec.loader is not None
spec.loader.exec_module(auth_utils)


def test_static_token_provider_accepts_and_returns_token():
    with pytest.raises(auth_utils.AuthConfigError):
        auth_utils.StaticTokenProvider("")

    p = auth_utils.StaticTokenProvider(" secret ")
    assert p.get_token(correlation_id="cid") == "secret"


def test_resolve_oidc_token_url_behaviour():
    assert (
        auth_utils.resolve_oidc_token_url(issuer="https://issuer", token_url=None)
        == "https://issuer/protocol/openid-connect/token"
    )
    assert (
        auth_utils.resolve_oidc_token_url(issuer=None, token_url="https://t")
        == "https://t"
    )
    assert auth_utils.resolve_oidc_token_url(issuer=None, token_url=None) is None


class DummyResponse:
    def __init__(self, status_code=200, payload=None, json_raises=False):
        self.status_code = status_code
        self._payload = payload or {}
        self._json_raises = json_raises

    def json(self):
        if self._json_raises:
            raise ValueError("not json")
        return self._payload


def test_oidc_client_credentials_get_token_success_and_errors(monkeypatch):
    calls = {}

    def fake_post_success(url, data=None, headers=None, timeout=None):
        calls['last'] = dict(url=url, data=data, headers=headers, timeout=timeout)
        return DummyResponse(status_code=200, payload={"access_token": "abc", "expires_in": 3600})

    provider = auth_utils.OidcClientCredentialsTokenProvider(
        token_url="https://tok",
        client_id="cid",
        client_secret="cs",
        scope=None,
        refresh_skew_seconds=60,
        timeout_seconds=1,
        max_startup_retries=0,
        retry_backoff_seconds=5.0,
    )

    # network success
    monkeypatch.setattr(auth_utils.requests, "post", fake_post_success)
    token = provider.get_token(correlation_id="cid")
    assert token == "abc"

    # Clear cache so subsequent calls actually invoke the token endpoint
    provider._cached = None

    # response with error status
    def fake_post_400(*a, **k):
        return DummyResponse(status_code=400, payload={})

    monkeypatch.setattr(auth_utils.requests, "post", fake_post_400)
    with pytest.raises(auth_utils.AuthConfigError):
        provider.get_token(correlation_id="cid")

    # response with non-json
    # Clear cache again for next scenario
    provider._cached = None

    def fake_post_nonjson(*a, **k):
        return DummyResponse(status_code=200, json_raises=True)

    monkeypatch.setattr(auth_utils.requests, "post", fake_post_nonjson)
    with pytest.raises(auth_utils.AuthConfigError):
        provider.get_token(correlation_id="cid")

    # network exception
    def fake_post_exc(*a, **k):
        raise auth_utils.requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(auth_utils.requests, "post", fake_post_exc)
    with pytest.raises(auth_utils.AuthConfigError):
        provider.get_token(correlation_id="cid")


def _resolve_retry_params() -> tuple[int, float]:
    """Read retry params from the same env vars the real callers use."""
    max_retries = int(os.getenv("DQ_ENGINE_MAX_RETRIES", "0"))
    backoff_ms = int(os.getenv("DQ_ENGINE_RETRY_BACKOFF_MS", "5000"))
    return max_retries, backoff_ms / 1000.0


def test_build_oidc_provider_wires_retry_params_from_env(monkeypatch):
    """Verify retry params are read from the same env vars callers use."""
    monkeypatch.setenv("TEST_OISSUER", "https://keycloak:8443/realms/test")
    monkeypatch.setenv("TEST_CLIENT_ID", "test-client")
    monkeypatch.setenv("TEST_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("DQ_ENGINE_MAX_RETRIES", "3")
    monkeypatch.setenv("DQ_ENGINE_RETRY_BACKOFF_MS", "2000")

    provider = auth_utils.build_oidc_token_provider_from_env(
        issuer_env_var="TEST_OISSUER",
        token_url_env_var="TEST_TOKEN_URL",
        client_id_env_var="TEST_CLIENT_ID",
        client_secret_env_var="TEST_CLIENT_SECRET",
        scope_env_var="TEST_SCOPE",
        max_startup_retries=int(os.getenv("DQ_ENGINE_MAX_RETRIES", "0")),
        retry_backoff_seconds=int(os.getenv("DQ_ENGINE_RETRY_BACKOFF_MS", "5000")) / 1000.0,
    )

    assert isinstance(provider, auth_utils.OidcClientCredentialsTokenProvider)
    assert provider._max_startup_retries == 3
    assert provider._retry_backoff_seconds == 2.0


def test_build_token_provider_from_env_prefers_static(monkeypatch):
    monkeypatch.setenv("MY_STATIC_TOKEN", "s1")
    max_retries, backoff = _resolve_retry_params()
    p = auth_utils.build_token_provider_from_env(
        static_token_env_var="MY_STATIC_TOKEN",
        issuer_env_var="ISS",
        token_url_env_var="T",
        client_id_env_var="CID",
        client_secret_env_var="CS",
        scope_env_var="S",
        max_startup_retries=max_retries,
        retry_backoff_seconds=backoff,
    )
    assert isinstance(p, auth_utils.StaticTokenProvider)
    assert p.get_token(correlation_id="c") == "s1"


def test_build_oidc_token_provider_from_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("ISS", raising=False)
    monkeypatch.delenv("T", raising=False)
    monkeypatch.delenv("CID", raising=False)
    monkeypatch.delenv("CS", raising=False)
    max_retries, backoff = _resolve_retry_params()

    with pytest.raises(auth_utils.AuthConfigError):
        auth_utils.build_oidc_token_provider_from_env(
            issuer_env_var="ISS",
            token_url_env_var="T",
            client_id_env_var="CID",
            client_secret_env_var="CS",
            scope_env_var="S",
            max_startup_retries=max_retries,
            retry_backoff_seconds=backoff,
        )
