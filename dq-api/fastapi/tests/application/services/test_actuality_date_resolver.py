from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from app.application.services.actuality_date_resolver import (
    ActualityDateResolutionDispatcher,
    ActualityDateResolutionError,
    auto_resolve_actuality_attributes,
)
from app.application.services.data_contract_resolver import DataContractLookupError


# -- Test fixtures -----------------------------------------------------------


@dataclass(frozen=True)
class _FakeAttribute:
    name: str
    type: str = "string"


@dataclass(frozen=True)
class _FakeVersion:
    id: str
    data_object_id: str


@dataclass(frozen=True)
class _FakeObject:
    id: str
    dataset_id: str = "dataset-1"


class _FakeCatalogRepository:
    def __init__(self, attributes: dict[str, list[_FakeAttribute]]) -> None:
        self._attributes = attributes

    def list_data_object_versions(self) -> list[_FakeVersion]:
        return [
            _FakeVersion(id="v-left", data_object_id="obj-1"),
            _FakeVersion(id="v-right", data_object_id="obj-2"),
        ]

    def list_data_objects_catalog(self) -> list[_FakeObject]:
        return [
            _FakeObject(id="obj-1"),
            _FakeObject(id="obj-2"),
        ]

    def list_attributes_catalog(self, version_id: str) -> list[_FakeAttribute]:
        return list(self._attributes.get(version_id, []))


class _FakeContractResolver:
    def __init__(self, policy: dict | None = None, error: Exception | None = None) -> None:
        self._policy = policy
        self._error = error

    async def resolve_contract_policy(
        self, contract_id: str, *, dataset_id: str | None = None, cache_ttl_seconds: int | None = None
    ) -> dict:
        if self._error:
            raise self._error
        return dict(self._policy or {
            "resolvedToleranceValue": 15,
            "resolvedToleranceUnit": "minutes",
            "overrideAllowed": False,
            "contractVersion": "1.0",
        })


# -- Explicit resolver tests -------------------------------------------------


@pytest.mark.asyncio
async def test_explicit_resolver_returns_supplied_values() -> None:
    dispatcher = ActualityDateResolutionDispatcher()
    result = await dispatcher.resolve(
        actuality_contract={
            "toleranceSource": "EXPLICIT",
            "contractId": "n/a",
            "resolvedToleranceValue": 45,
            "resolvedToleranceUnit": "hours",
        },
        left_version_id="v1",
        right_version_id="v2",
    )
    assert result["resolvedToleranceValue"] == 45
    assert result["resolvedToleranceUnit"] == "hours"


@pytest.mark.asyncio
async def test_explicit_resolver_rejects_missing_values() -> None:
    dispatcher = ActualityDateResolutionDispatcher()
    with pytest.raises(ActualityDateResolutionError, match="requires.*resolvedToleranceValue"):
        await dispatcher.resolve(
            actuality_contract={
                "toleranceSource": "EXPLICIT",
                "contractId": "n/a",
            },
            left_version_id="v1",
            right_version_id="v2",
        )


# -- Delivery metadata resolver tests ----------------------------------------


@pytest.mark.asyncio
async def test_delivery_metadata_resolver_returns_default_tolerance() -> None:
    dispatcher = ActualityDateResolutionDispatcher(
        default_tolerance_value=120,
        default_tolerance_unit="hours",
    )
    result = await dispatcher.resolve(
        actuality_contract={
            "toleranceSource": "DELIVERY_METADATA",
            "contractId": "meta-contract",
        },
        left_version_id="v1",
        right_version_id="v2",
    )
    assert result["resolvedToleranceValue"] == 120
    assert result["resolvedToleranceUnit"] == "hours"


# -- Contract resolver tests -------------------------------------------------


@pytest.mark.asyncio
async def test_contract_resolver_delegates_to_openmetadata() -> None:
    contract_resolver = _FakeContractResolver(policy={
        "resolvedToleranceValue": 60,
        "resolvedToleranceUnit": "hours",
        "overrideAllowed": True,
        "contractVersion": "2.0",
    })
    dispatcher = ActualityDateResolutionDispatcher(contract_resolver=contract_resolver)
    result = await dispatcher.resolve(
        actuality_contract={
            "toleranceSource": "DELIVERY_CONTRACT",
            "contractId": "contract-1",
        },
        left_version_id="v1",
        right_version_id="v2",
        dataset_id="dataset-1",
    )
    assert result["resolvedToleranceValue"] == 60
    assert result["resolvedToleranceUnit"] == "hours"
    assert result.get("contractVersion") == "2.0"


@pytest.mark.asyncio
async def test_contract_resolver_with_override() -> None:
    contract_resolver = _FakeContractResolver(policy={
        "resolvedToleranceValue": 30,
        "resolvedToleranceUnit": "minutes",
        "overrideAllowed": True,
        "maxOverrideToleranceValue": 60,
        "maxOverrideToleranceUnit": "minutes",
        "contractVersion": "1.0",
    })
    dispatcher = ActualityDateResolutionDispatcher(contract_resolver=contract_resolver)
    result = await dispatcher.resolve(
        actuality_contract={
            "toleranceSource": "DELIVERY_CONTRACT",
            "contractId": "contract-1",
            "overrideToleranceValue": 45,
            "overrideToleranceUnit": "minutes",
        },
        left_version_id="v1",
        right_version_id="v2",
    )
    assert result["resolvedToleranceValue"] == 45


@pytest.mark.asyncio
async def test_contract_resolver_rejects_override_when_not_allowed() -> None:
    contract_resolver = _FakeContractResolver(policy={
        "resolvedToleranceValue": 30,
        "resolvedToleranceUnit": "minutes",
        "overrideAllowed": False,
        "contractVersion": "1.0",
    })
    dispatcher = ActualityDateResolutionDispatcher(contract_resolver=contract_resolver)
    with pytest.raises(ActualityDateResolutionError, match="does not allow"):
        await dispatcher.resolve(
            actuality_contract={
                "toleranceSource": "DELIVERY_CONTRACT",
                "contractId": "contract-1",
                "overrideToleranceValue": 45,
                "overrideToleranceUnit": "minutes",
            },
            left_version_id="v1",
            right_version_id="v2",
        )


@pytest.mark.asyncio
async def test_contract_resolver_rejects_override_exceeding_bound() -> None:
    contract_resolver = _FakeContractResolver(policy={
        "resolvedToleranceValue": 30,
        "resolvedToleranceUnit": "minutes",
        "overrideAllowed": True,
        "maxOverrideToleranceValue": 45,
        "maxOverrideToleranceUnit": "minutes",
        "contractVersion": "1.0",
    })
    dispatcher = ActualityDateResolutionDispatcher(contract_resolver=contract_resolver)
    with pytest.raises(ActualityDateResolutionError, match="exceeds contract bound"):
        await dispatcher.resolve(
            actuality_contract={
                "toleranceSource": "DELIVERY_CONTRACT",
                "contractId": "contract-1",
                "overrideToleranceValue": 60,
                "overrideToleranceUnit": "minutes",
            },
            left_version_id="v1",
            right_version_id="v2",
        )


@pytest.mark.asyncio
async def test_contract_resolver_propagates_lookup_error() -> None:
    contract_resolver = _FakeContractResolver(
        error=DataContractLookupError("contract not found", status_code=503)
    )
    dispatcher = ActualityDateResolutionDispatcher(contract_resolver=contract_resolver)
    with pytest.raises(ActualityDateResolutionError):
        await dispatcher.resolve(
            actuality_contract={
                "toleranceSource": "DELIVERY_CONTRACT",
                "contractId": "missing",
            },
            left_version_id="v1",
            right_version_id="v2",
        )


# -- Dispatcher unknown source -----------------------------------------------


@pytest.mark.asyncio
async def test_dispatcher_rejects_unknown_source() -> None:
    dispatcher = ActualityDateResolutionDispatcher()
    with pytest.raises(ActualityDateResolutionError, match="Unknown toleranceSource"):
        await dispatcher.resolve(
            actuality_contract={
                "toleranceSource": "UNKNOWN",
                "contractId": "x",
            },
            left_version_id="v1",
            right_version_id="v2",
        )


# -- Auto-resolve attribute tests --------------------------------------------


def test_auto_resolve_picks_actuality_named_attribute() -> None:
    repo = _FakeCatalogRepository(attributes={
        "v-left": [
            _FakeAttribute(name="id", type="string"),
            _FakeAttribute(name="actuality_date", type="timestamp"),
            _FakeAttribute(name="updated_at", type="timestamp"),
        ],
        "v-right": [
            _FakeAttribute(name="id", type="string"),
            _FakeAttribute(name="actuality_date", type="date"),
            _FakeAttribute(name="modified_at", type="timestamp"),
        ],
    })
    left, right = auto_resolve_actuality_attributes(
        "v-left", "v-right", catalog_repository=repo
    )
    assert left == "actuality_date"
    assert right == "actuality_date"


def test_auto_resolve_uses_heuristic_keywords() -> None:
    repo = _FakeCatalogRepository(attributes={
        "v-left": [
            _FakeAttribute(name="id", type="string"),
            _FakeAttribute(name="updated_at", type="timestamp"),
            _FakeAttribute(name="created_at", type="timestamp"),
        ],
        "v-right": [
            _FakeAttribute(name="id", type="string"),
            _FakeAttribute(name="effective_date", type="date"),
            _FakeAttribute(name="created_at", type="timestamp"),
        ],
    })
    left, right = auto_resolve_actuality_attributes(
        "v-left", "v-right", catalog_repository=repo
    )
    # "updated" is a heuristic keyword; "effective" is also a keyword
    assert left == "updated_at"
    assert right == "effective_date"


def test_auto_resolve_falls_back_to_first_temporal() -> None:
    repo = _FakeCatalogRepository(attributes={
        "v-left": [
            _FakeAttribute(name="id", type="string"),
            _FakeAttribute(name="some_timestamp", type="timestamp"),
        ],
        "v-right": [
            _FakeAttribute(name="id", type="string"),
            _FakeAttribute(name="another_date", type="date"),
        ],
    })
    left, right = auto_resolve_actuality_attributes(
        "v-left", "v-right", catalog_repository=repo
    )
    assert left == "some_timestamp"
    assert right == "another_date"


def test_auto_resolve_raises_when_no_temporal_attribute() -> None:
    repo = _FakeCatalogRepository(attributes={
        "v-left": [
            _FakeAttribute(name="id", type="string"),
            _FakeAttribute(name="name", type="string"),
        ],
        "v-right": [
            _FakeAttribute(name="id", type="string"),
        ],
    })
    with pytest.raises(ActualityDateResolutionError, match="Could not auto-resolve"):
        auto_resolve_actuality_attributes("v-left", "v-right", catalog_repository=repo)
