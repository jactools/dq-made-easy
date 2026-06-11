import sys
import types
import pytest
from urllib.error import HTTPError, URLError

import app.application.services.data_contract_resolver as data_contract_resolver
from app.application.services.data_contract_resolver import DataContractLookupError
from app.application.services.data_contract_resolver import OpenMetadataContractResolver


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        del ttl_seconds
        self.store[key] = value


def _build_resolver() -> OpenMetadataContractResolver:
    return OpenMetadataContractResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="token",
        timeout_seconds=30,
        redis_host="redis",
    )


def test_extract_policy_uses_openmetadata_sla_and_odcs_extension_version() -> None:
    resolver = _build_resolver()

    payload = {
        "id": "2c735d55-8070-4c9a-b379-5cc1b05b2de9",
        "name": "payments-ledger-contract",
        "sla": {
            "maxLatency": {
                "value": 24,
                "unit": "hour",
            }
        },
        "extension": {
            "odcs": {
                "id": "urn:dq:contract:demo-azure-payments-sql",
                "info": {
                    "version": "1.2.0",
                },
            },
            "x-dq-rule-policy": {
                "joinConsistency": {
                    "actualityDate": {
                        "overrideAllowed": True,
                        "maxOverrideTolerance": {
                            "value": 4,
                            "unit": "hour",
                        },
                    }
                }
            },
        },
    }

    policy = resolver._extract_policy(payload, "urn:dq:contract:demo-azure-payments-sql")

    assert policy["contractVersion"] == "1.2.0"
    assert policy["resolvedToleranceValue"] == 24
    assert policy["resolvedToleranceUnit"] == "hours"
    assert policy["overrideAllowed"] is True
    assert policy["maxOverrideToleranceValue"] == 4
    assert policy["maxOverrideToleranceUnit"] == "hours"


def test_find_contract_in_list_matches_odcs_contract_id_in_extension() -> None:
    resolver = _build_resolver()
    payload = {
        "data": [
            {
                "id": "e47472d0-6af8-4ebd-a754-8cfe4f34bf20",
                "name": "payments-ledger-contract",
                "extension": {
                    "odcs": {
                        "id": "urn:dq:contract:demo-azure-payments-sql",
                    }
                },
            }
        ]
    }

    match = resolver._find_contract_in_list(payload, "urn:dq:contract:demo-azure-payments-sql")

    assert match is not None
    assert match["name"] == "payments-ledger-contract"


def test_extract_policy_rejects_missing_sla_max_latency() -> None:
    resolver = _build_resolver()

    with pytest.raises(DataContractLookupError) as error:
        resolver._extract_policy(
            {
                "name": "payments-ledger-contract",
                "sla": {},
                "extension": {},
            },
            "urn:dq:contract:demo-azure-payments-sql",
        )

    assert "sla.maxLatency" in str(error.value)


@pytest.mark.anyio
async def test_resolve_contract_policy_uses_cache_for_configured_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()
    fake_redis = _FakeRedis()
    call_counter = {"value": 0}

    def fake_request_json(path: str, *, allow_not_found: bool):
        del path, allow_not_found
        call_counter["value"] += 1
        return {
            "id": "2c735d55-8070-4c9a-b379-5cc1b05b2de9",
            "name": "payments-ledger-contract",
            "version": 1.0,
            "sla": {
                "maxLatency": {
                    "value": 24,
                    "unit": "hour",
                }
            },
            "extension": {
                "odcs": {
                    "id": "urn:dq:contract:demo-azure-payments-sql",
                    "info": {
                        "version": "1.2.0",
                    },
                }
            },
        }

    monkeypatch.setattr(resolver, "_request_json", fake_request_json)
    monkeypatch.setattr(resolver, "_get_redis_client", lambda: fake_redis)

    first = await resolver.resolve_contract_policy(
        "urn:dq:contract:demo-azure-payments-sql",
        dataset_id="ds-contract",
        cache_ttl_seconds=300,
    )
    second = await resolver.resolve_contract_policy(
        "urn:dq:contract:demo-azure-payments-sql",
        dataset_id="ds-contract",
        cache_ttl_seconds=300,
    )

    assert first["resolvedToleranceValue"] == 24
    assert second["resolvedToleranceUnit"] == "hours"
    assert call_counter["value"] == 1


@pytest.mark.anyio
async def test_resolve_contract_policy_bypasses_cache_when_redis_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()
    call_counter = {"value": 0}

    def fake_request_json(path: str, *, allow_not_found: bool):
        del path, allow_not_found
        call_counter["value"] += 1
        return {
            "id": "2c735d55-8070-4c9a-b379-5cc1b05b2de9",
            "name": "payments-ledger-contract",
            "version": 1.0,
            "sla": {
                "maxLatency": {
                    "value": 24,
                    "unit": "hour",
                }
            },
            "extension": {
                "odcs": {
                    "id": "urn:dq:contract:demo-azure-payments-sql",
                    "info": {
                        "version": "1.2.0",
                    },
                }
            },
        }

    monkeypatch.setattr(resolver, "_request_json", fake_request_json)
    monkeypatch.setattr(resolver, "_get_redis_client", lambda: None)

    await resolver.resolve_contract_policy(
        "urn:dq:contract:demo-azure-payments-sql",
        dataset_id="ds-contract",
        cache_ttl_seconds=300,
    )
    await resolver.resolve_contract_policy(
        "urn:dq:contract:demo-azure-payments-sql",
        dataset_id="ds-contract",
        cache_ttl_seconds=300,
    )

    assert call_counter["value"] == 2


def test_resolve_contract_policy_sync_validates_required_configuration() -> None:
    missing_contract = _build_resolver()
    with pytest.raises(DataContractLookupError) as error:
        missing_contract._resolve_contract_policy_sync("", None, 10)
    assert "contractId" in str(error.value)

    wrong_provider = OpenMetadataContractResolver(
        provider="catalog-x",
        endpoint="https://openmetadata.example.com",
        api_key="token",
        timeout_seconds=30,
    )
    with pytest.raises(DataContractLookupError) as provider_error:
        wrong_provider._resolve_contract_policy_sync("contract-1", None, 10)
    assert provider_error.value.status_code == 503

    missing_endpoint = OpenMetadataContractResolver(
        provider="openmetadata",
        endpoint="",
        api_key="token",
        timeout_seconds=30,
    )
    with pytest.raises(DataContractLookupError) as endpoint_error:
        missing_endpoint._resolve_contract_policy_sync("contract-1", None, 10)
    assert endpoint_error.value.status_code == 503


def test_cache_ttl_normalization_and_cache_key_builder() -> None:
    resolver = _build_resolver()
    assert resolver._normalize_cache_ttl_seconds(None) == 300
    assert resolver._normalize_cache_ttl_seconds(-10) == 0
    assert resolver._normalize_cache_ttl_seconds(45) == 45
    assert resolver._build_cache_key("contract-a", " dataset-1 ") == "dq:openmetadata:contract-policy:contract-a:dataset:dataset-1"


def test_get_cached_policy_handles_ttl_client_and_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()

    assert resolver._get_cached_policy("key", 0) is None

    class _RaisingClient:
        def get(self, _key: str) -> str:
            raise RuntimeError("cache read failed")

    monkeypatch.setattr(resolver, "_get_redis_client", lambda: _RaisingClient())
    assert resolver._get_cached_policy("key", 30) is None

    class _JsonClient:
        def __init__(self, payload: str) -> None:
            self._payload = payload

        def get(self, _key: str) -> str:
            return self._payload

    monkeypatch.setattr(resolver, "_get_redis_client", lambda: _JsonClient("not-json"))
    assert resolver._get_cached_policy("key", 30) is None

    monkeypatch.setattr(resolver, "_get_redis_client", lambda: _JsonClient("[1,2,3]"))
    assert resolver._get_cached_policy("key", 30) is None

    monkeypatch.setattr(resolver, "_get_redis_client", lambda: _JsonClient('{"overrideAllowed": true}'))
    assert resolver._get_cached_policy("key", 30) == {"overrideAllowed": True}


def test_set_cached_policy_swallows_cache_write_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()

    class _RaisingClient:
        def setex(self, _key: str, _ttl_seconds: int, _payload: str) -> None:
            raise RuntimeError("cache write failed")

    monkeypatch.setattr(resolver, "_get_redis_client", lambda: _RaisingClient())
    resolver._set_cached_policy("key", {"resolvedToleranceValue": 24}, 30)


def test_build_contract_lookup_paths_for_uuid_and_name() -> None:
    resolver = _build_resolver()

    uuid_paths = resolver._build_contract_lookup_paths("2c735d55-8070-4c9a-b379-5cc1b05b2de9")
    assert any("/v1/dataContracts/2c735d55-8070-4c9a-b379-5cc1b05b2de9" in path for path in uuid_paths)
    assert any("/v1/dataContracts/name/2c735d55-8070-4c9a-b379-5cc1b05b2de9" in path for path in uuid_paths)

    name_paths = resolver._build_contract_lookup_paths("urn:dq:contract:demo")
    assert len(name_paths) == 1
    assert "/v1/dataContracts/name/urn%3Adq%3Acontract%3Ademo" in name_paths[0]


def test_find_contract_in_list_supports_multiple_payload_shapes() -> None:
    resolver = _build_resolver()

    assert resolver._find_contract_in_list(None, "x") is None
    assert resolver._find_contract_in_list({"data": "bad"}, "x") is None

    entities_payload = {
        "entities": [{"id": "id-1", "name": "contract-a", "extension": {}}],
    }
    match = resolver._find_contract_in_list(entities_payload, "contract-a")
    assert match is not None
    assert match["id"] == "id-1"


def test_extract_contract_version_and_override_policy_fallbacks() -> None:
    resolver = _build_resolver()

    version_payload = {
        "extension": {
            "source": {
                "info": {
                    "version": "2.1.0",
                }
            }
        }
    }
    assert resolver._extract_contract_version(version_payload) == "2.1.0"
    assert resolver._extract_contract_version({"version": "3.0.0"}) == "3.0.0"

    policy_payload = {
        "dqRulePolicy": {
            "joinConsistency": {
                "actualityDate": {
                    "overrideAllowed": True,
                }
            }
        }
    }
    assert resolver._extract_override_policy(policy_payload)["overrideAllowed"] is True


def test_request_json_handles_http_url_json_and_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _build_resolver()

    class _FakeResponse:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

    def _ok_urlopen(request, timeout: int):
        del timeout
        assert request.headers.get("Authorization") == "Bearer token"
        return _FakeResponse(b'{"name":"contract-a"}')

    monkeypatch.setattr("app.application.services.data_contract_resolver.urlopen", _ok_urlopen)
    parsed = resolver._request_json("/v1/dataContracts/name/contract-a", allow_not_found=False)
    assert parsed == {"name": "contract-a"}

    def _not_found_urlopen(_request, timeout: int):
        del timeout
        raise HTTPError("https://example.com", 404, "not found", hdrs=None, fp=None)

    monkeypatch.setattr("app.application.services.data_contract_resolver.urlopen", _not_found_urlopen)
    assert resolver._request_json("/v1/dataContracts/name/missing", allow_not_found=True) is None

    def _server_error_urlopen(_request, timeout: int):
        del timeout
        raise HTTPError("https://example.com", 500, "boom", hdrs=None, fp=None)

    monkeypatch.setattr("app.application.services.data_contract_resolver.urlopen", _server_error_urlopen)
    with pytest.raises(DataContractLookupError):
        resolver._request_json("/v1/dataContracts/name/bad", allow_not_found=False)

    def _url_error(_request, timeout: int):
        del timeout
        raise URLError("network down")

    monkeypatch.setattr("app.application.services.data_contract_resolver.urlopen", _url_error)
    with pytest.raises(DataContractLookupError):
        resolver._request_json("/v1/dataContracts/name/net", allow_not_found=False)

    monkeypatch.setattr(
        "app.application.services.data_contract_resolver.urlopen",
        lambda _request, timeout: _FakeResponse(b"not-json"),
    )
    with pytest.raises(DataContractLookupError):
        resolver._request_json("/v1/dataContracts/name/json", allow_not_found=False)


def test_request_json_uses_dynamic_password_token_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_init: dict[str, object] = {}

    class _FakeProvider:
        def __init__(self, **kwargs) -> None:
            captured_init.update(kwargs)

        def get_token(self, *, correlation_id: str) -> str:
            assert correlation_id
            return "dynamic-token"

    class _FakeResponse:
        def read(self) -> bytes:
            return b'{"name":"contract-a"}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

    captured_headers: dict[str, str] = {}

    def _fake_urlopen(request, timeout: int):
        del timeout
        captured_headers.update(dict(request.headers.items()))
        return _FakeResponse()

    monkeypatch.setattr(data_contract_resolver, "OidcPasswordTokenProvider", _FakeProvider)
    monkeypatch.setattr("app.application.services.data_contract_resolver.urlopen", _fake_urlopen)

    resolver = OpenMetadataContractResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="",
        oidc_issuer="https://keycloak.example.com/realms/jaccloud",
        oidc_client_id="openmetadata",
        oidc_username="dq-admin@example.com",
        oidc_password="secret-password",
        timeout_seconds=30,
    )

    parsed = resolver._request_json("/v1/dataContracts/name/contract-a", allow_not_found=False)

    assert parsed == {"name": "contract-a"}
    assert captured_init["client_id"] == "openmetadata"
    assert captured_init["username"] == "dq-admin@example.com"
    assert captured_init["password"] == "secret-password"
    assert captured_headers["Authorization"] == "Bearer dynamic-token"
    assert captured_headers["X-correlation-id"]


def test_request_json_fails_fast_when_oidc_auth_is_misconfigured() -> None:
    resolver = OpenMetadataContractResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="",
        oidc_issuer="https://keycloak.example.com/realms/jaccloud",
        oidc_client_id="openmetadata",
        oidc_username="dq-admin@example.com",
        oidc_password="",
        timeout_seconds=30,
    )

    with pytest.raises(DataContractLookupError) as error:
        resolver._resolve_authorization_header(correlation_id="cid-1")

    assert error.value.status_code == 503
    assert "OIDC password is required" in str(error.value)


def test_fetch_contract_falls_back_to_list_lookup() -> None:
    resolver = _build_resolver()

    def _fake_request(path: str, *, allow_not_found: bool):
        del allow_not_found
        if path.startswith("/v1/dataContracts/name/"):
            return None
        if path.startswith("/v1/dataContracts?"):
            return {"data": [{"name": "contract-by-list", "sla": {"maxLatency": {"value": 1, "unit": "hour"}}}]}
        return None

    resolver._request_json = _fake_request  # type: ignore[method-assign]
    match = resolver._fetch_contract("contract-by-list")
    assert match["name"] == "contract-by-list"


def test_extract_policy_accepts_compact_override_and_rejects_invalid_values() -> None:
    resolver = _build_resolver()

    payload = {
        "sla": {"maxLatency": {"value": 2, "unit": "day"}},
        "extension": {
            "x-dq-rule-policy": {
                "joinConsistency": {
                    "actualityDate": {
                        "overrideAllowed": True,
                        "maxOverrideTolerance": "24h",
                    }
                }
            }
        },
    }
    policy = resolver._extract_policy(payload, "contract-x")
    assert policy["resolvedToleranceUnit"] == "days"
    assert policy["maxOverrideToleranceValue"] == 24
    assert policy["maxOverrideToleranceUnit"] == "hours"

    with pytest.raises(DataContractLookupError):
        resolver._parse_duration_to_value_unit("3w", field_name="field")

    with pytest.raises(DataContractLookupError):
        resolver._extract_policy(
            {
                "sla": {"maxLatency": {"value": 1, "unit": "hour"}},
                "extension": {
                    "x-dq-rule-policy": {
                        "joinConsistency": {
                            "actualityDate": {
                                "maxOverrideTolerance": {"value": 2, "unit": "weeks"},
                            }
                        }
                    }
                },
            },
            "contract-y",
        )


def test_initialize_token_provider_returns_none_without_auth_inputs() -> None:
    resolver = OpenMetadataContractResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="",
        timeout_seconds=30,
    )

    assert resolver._token_provider is None
    assert resolver._token_provider_error is None


def test_initialize_token_provider_supports_client_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeProvider:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(data_contract_resolver, "OidcClientCredentialsTokenProvider", _FakeProvider)
    monkeypatch.setattr(data_contract_resolver, "resolve_oidc_token_url", lambda issuer, token_url: token_url or f"{issuer}/token")

    resolver = OpenMetadataContractResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="",
        oidc_issuer="https://issuer.example.com/realms/main",
        oidc_client_id="client-id",
        oidc_client_secret="client-secret",
        oidc_scope="openid",
        timeout_seconds=30,
    )

    assert resolver._token_provider is not None
    assert captured["client_id"] == "client-id"
    assert captured["client_secret"] == "client-secret"
    assert captured["scope"] == "openid"


def test_set_cached_policy_skips_zero_ttl() -> None:
    resolver = _build_resolver()

    class _RecordingClient:
        def __init__(self) -> None:
            self.calls = 0

        def setex(self, _key: str, _ttl_seconds: int, _payload: str) -> None:
            self.calls += 1

    client = _RecordingClient()
    resolver._get_redis_client = lambda: client

    resolver._set_cached_policy("key", {"resolvedToleranceValue": 1}, 0)

    assert client.calls == 0


def test_get_redis_client_caches_client_and_handles_init_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, object] = {}

    class _FakeRedisClient:
        def __init__(self, **kwargs) -> None:
            created.update(kwargs)

    fake_redis_module = types.SimpleNamespace(Redis=_FakeRedisClient)
    monkeypatch.setitem(sys.modules, "redis", fake_redis_module)

    resolver = _build_resolver()
    client = resolver._get_redis_client()

    assert client is resolver._redis_client
    assert created["host"] == "redis"
    assert resolver._get_redis_client() is client

    failing_resolver = _build_resolver()
    failing_resolver._redis_client_init_attempted = False
    monkeypatch.setitem(sys.modules, "redis", types.SimpleNamespace(Redis=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))))

    assert failing_resolver._get_redis_client() is None
    assert failing_resolver._get_redis_client() is None


def test_get_redis_client_returns_none_when_host_is_not_configured() -> None:
    resolver = OpenMetadataContractResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="token",
        timeout_seconds=30,
        redis_host="",
    )

    assert resolver._get_redis_client() is None


def test_fetch_contract_raises_when_contract_cannot_be_found() -> None:
    resolver = _build_resolver()
    resolver._request_json = lambda path, *, allow_not_found: {"data": []} if path.startswith("/v1/dataContracts?") else None  # type: ignore[method-assign]

    with pytest.raises(DataContractLookupError, match="was not found"):
        resolver._fetch_contract("contract-missing")


def test_request_json_omits_authorization_when_no_token_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = OpenMetadataContractResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="",
        timeout_seconds=30,
    )

    class _FakeResponse:
        def read(self) -> bytes:
            return b'{"name":"contract-a"}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

    seen_headers: dict[str, str] = {}

    def _fake_urlopen(request, timeout: int):
        del timeout
        seen_headers.update(dict(request.headers.items()))
        return _FakeResponse()

    monkeypatch.setattr("app.application.services.data_contract_resolver.urlopen", _fake_urlopen)

    assert resolver._request_json("/v1/dataContracts/name/contract-a", allow_not_found=False) == {"name": "contract-a"}
    assert "Authorization" not in seen_headers


def test_resolve_authorization_header_handles_none_authconfigerror_empty_and_bearer() -> None:
    resolver = OpenMetadataContractResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="",
        timeout_seconds=30,
    )
    assert resolver._resolve_authorization_header(correlation_id="cid-none") is None

    class _RaisingProvider:
        def get_token(self, *, correlation_id: str) -> str:
            del correlation_id
            raise data_contract_resolver.AuthConfigError("token provider failed")

    resolver._token_provider = _RaisingProvider()
    with pytest.raises(DataContractLookupError, match="token acquisition failed"):
        resolver._resolve_authorization_header(correlation_id="cid-error")

    class _EmptyProvider:
        def get_token(self, *, correlation_id: str) -> str:
            del correlation_id
            return "   "

    resolver._token_provider = _EmptyProvider()
    with pytest.raises(DataContractLookupError, match="empty access token"):
        resolver._resolve_authorization_header(correlation_id="cid-empty")

    class _BearerProvider:
        def get_token(self, *, correlation_id: str) -> str:
            del correlation_id
            return "Bearer existing-token"

    resolver._token_provider = _BearerProvider()
    assert resolver._resolve_authorization_header(correlation_id="cid-bearer") == "Bearer existing-token"


def test_find_contract_in_list_and_iter_string_values_cover_no_match_paths() -> None:
    resolver = _build_resolver()

    assert resolver._find_contract_in_list({"items": ["bad-item", {"name": "other-contract"}]}, "contract-a") is None
    assert resolver._iter_string_values([" a ", {"nested": [" b "]}, 3]) == ["a", "b"]
    assert resolver._iter_string_values(42) == []


def test_normalize_sla_unit_rejects_invalid_value() -> None:
    resolver = _build_resolver()

    with pytest.raises(DataContractLookupError, match="sla.maxLatency.unit"):
        resolver._normalize_sla_unit("weeks")