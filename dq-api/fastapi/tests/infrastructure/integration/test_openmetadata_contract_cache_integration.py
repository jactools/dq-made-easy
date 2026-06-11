"""Integration policy: OpenMetadata contract caching can be verified explicitly when requested.

This test is intentionally opt-in and skipped in normal unit pipelines.
"""
from __future__ import annotations

import pytest

from app.application.services.data_contract_resolver import OpenMetadataContractResolver


pytestmark = pytest.mark.integration


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        del ttl_seconds
        self.store[key] = value


@pytest.mark.anyio
async def test_openmetadata_contract_policy_cache_respects_ttl(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    if not request.config.getoption("--run-openmetadata-contract-cache-integration"):
        pytest.skip(
            "Pass --run-openmetadata-contract-cache-integration to execute this opt-in integration test."
        )

    resolver = OpenMetadataContractResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="token",
        timeout_seconds=30,
        redis_host="redis",
    )
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
        cache_ttl_seconds=120,
    )
    second = await resolver.resolve_contract_policy(
        "urn:dq:contract:demo-azure-payments-sql",
        dataset_id="ds-contract",
        cache_ttl_seconds=120,
    )

    assert first["resolvedToleranceValue"] == 24
    assert second["resolvedToleranceUnit"] == "hours"
    assert call_counter["value"] == 1
