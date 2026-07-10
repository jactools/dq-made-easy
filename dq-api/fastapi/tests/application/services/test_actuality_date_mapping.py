from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import HTTPException

from app.application.services.actuality_date_mapping import (
    apply_actuality_date_resolution,
    CROSS_OBJECT_CHECK_TYPES,
)
from app.application.services.actuality_date_resolver import (
    ActualityDateResolutionDispatcher,
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
        return [_FakeObject(id="obj-1"), _FakeObject(id="obj-2")]

    def list_attributes_catalog(self, version_id: str) -> list[_FakeAttribute]:
        return list(self._attributes.get(version_id, []))


class _FakeContractResolver:
    async def resolve_contract_policy(
        self, contract_id: str, *, dataset_id: str | None = None, cache_ttl_seconds: int | None = None
    ) -> dict:
        return {
            "resolvedToleranceValue": 30,
            "resolvedToleranceUnit": "minutes",
            "overrideAllowed": False,
            "contractVersion": "1.0",
        }


def _build_repo() -> _FakeCatalogRepository:
    return _FakeCatalogRepository(attributes={
        "v-left": [
            _FakeAttribute(name="left_key", type="string"),
            _FakeAttribute(name="left_value", type="string"),
            _FakeAttribute(name="left_updated_at", type="timestamp"),
        ],
        "v-right": [
            _FakeAttribute(name="right_key", type="string"),
            _FakeAttribute(name="right_value", type="string"),
            _FakeAttribute(name="right_updated_at", type="timestamp"),
        ],
    })


def _build_dispatcher() -> ActualityDateResolutionDispatcher:
    return ActualityDateResolutionDispatcher(contract_resolver=_FakeContractResolver())


# -- Cross-object check type coverage ----------------------------------------


def test_cross_object_check_types_contains_all_four() -> None:
    assert "CORRECT" in CROSS_OBJECT_CHECK_TYPES
    assert "RECONCILE" in CROSS_OBJECT_CHECK_TYPES
    assert "TRANSFER_MATCH" in CROSS_OBJECT_CHECK_TYPES
    assert "JOIN_CONSISTENCY" in CROSS_OBJECT_CHECK_TYPES


# -- Passthrough tests -------------------------------------------------------


@pytest.mark.asyncio
async def test_passthrough_for_non_cross_object_type() -> None:
    params = {"checkType": "THRESHOLD", "attribute": "email", "threshold": 95}
    result = await apply_actuality_date_resolution(
        check_type="THRESHOLD",
        check_type_params=params,
        catalog_repository=_build_repo(),
        actuality_dispatcher=_build_dispatcher(),
    )
    assert result is params


@pytest.mark.asyncio
async def test_passthrough_when_no_actuality_date() -> None:
    params = {
        "checkType": "CORRECT",
        "sourceDataObjectVersionId": "v-left",
        "referenceDataObjectVersionId": "v-right",
        "joinKeys": [{"leftAttribute": "left_key", "rightAttribute": "right_key"}],
        "comparison": {"leftAttribute": "left_value", "rightAttribute": "right_value"},
    }
    result = await apply_actuality_date_resolution(
        check_type="CORRECT",
        check_type_params=params,
        catalog_repository=_build_repo(),
        actuality_dispatcher=_build_dispatcher(),
    )
    assert result == params
    assert "actualityDate" not in result


@pytest.mark.asyncio
async def test_skips_join_consistency() -> None:
    """JOIN_CONSISTENCY is handled by the dedicated mapping service."""
    params = {
        "checkType": "JOIN_CONSISTENCY",
        "leftDataObjectVersionId": "v-left",
        "rightDataObjectVersionId": "v-right",
        "joinKeys": [{"leftAttribute": "left_key", "rightAttribute": "right_key"}],
        "comparisons": [{"leftAttribute": "left_value", "rightAttribute": "right_value"}],
        "actualityDate": {
            "leftAttribute": "left_updated_at",
            "rightAttribute": "right_updated_at",
            "toleranceSource": "DELIVERY_CONTRACT",
            "contractId": "c1",
        },
    }
    result = await apply_actuality_date_resolution(
        check_type="JOIN_CONSISTENCY",
        check_type_params=params,
        catalog_repository=_build_repo(),
        actuality_dispatcher=_build_dispatcher(),
    )
    # Should return params unchanged (skipped for JOIN_CONSISTENCY)
    assert result == params


# -- Resolution tests --------------------------------------------------------


@pytest.mark.asyncio
async def test_resolves_actuality_date_for_correct() -> None:
    params = {
        "checkType": "CORRECT",
        "sourceDataObjectVersionId": "v-left",
        "referenceDataObjectVersionId": "v-right",
        "joinKeys": [{"leftAttribute": "left_key", "rightAttribute": "right_key"}],
        "comparison": {"leftAttribute": "left_value", "rightAttribute": "right_value"},
        "actualityDate": {
            "leftAttribute": "left_updated_at",
            "rightAttribute": "right_updated_at",
            "toleranceSource": "DELIVERY_CONTRACT",
            "contractId": "c1",
        },
    }
    result = await apply_actuality_date_resolution(
        check_type="CORRECT",
        check_type_params=params,
        catalog_repository=_build_repo(),
        actuality_dispatcher=_build_dispatcher(),
    )
    assert result is not None
    assert result["actualityDate"]["resolvedToleranceValue"] == 30
    assert result["actualityDate"]["resolvedToleranceUnit"] == "minutes"


@pytest.mark.asyncio
async def test_resolves_actuality_date_for_reconcile() -> None:
    params = {
        "checkType": "RECONCILE",
        "leftDataObjectVersionId": "v-left",
        "rightDataObjectVersionId": "v-right",
        "joinKeys": [{"leftAttribute": "left_key", "rightAttribute": "right_key"}],
        "comparisons": [{"leftAttribute": "left_value", "rightAttribute": "right_value"}],
        "actualityDate": {
            "leftAttribute": "left_updated_at",
            "rightAttribute": "right_updated_at",
            "toleranceSource": "DELIVERY_CONTRACT",
            "contractId": "c1",
        },
    }
    result = await apply_actuality_date_resolution(
        check_type="RECONCILE",
        check_type_params=params,
        catalog_repository=_build_repo(),
        actuality_dispatcher=_build_dispatcher(),
    )
    assert result is not None
    assert result["actualityDate"]["resolvedToleranceValue"] == 30


@pytest.mark.asyncio
async def test_resolves_actuality_date_for_transfer_match() -> None:
    params = {
        "checkType": "TRANSFER_MATCH",
        "leftDataObjectVersionId": "v-left",
        "rightDataObjectVersionId": "v-right",
        "joinKeys": [{"leftAttribute": "left_key", "rightAttribute": "right_key"}],
        "comparisons": [{"leftAttribute": "left_value", "rightAttribute": "right_value"}],
        "actualityDate": {
            "leftAttribute": "left_updated_at",
            "rightAttribute": "right_updated_at",
            "toleranceSource": "DELIVERY_CONTRACT",
            "contractId": "c1",
        },
    }
    result = await apply_actuality_date_resolution(
        check_type="TRANSFER_MATCH",
        check_type_params=params,
        catalog_repository=_build_repo(),
        actuality_dispatcher=_build_dispatcher(),
    )
    assert result is not None
    assert result["actualityDate"]["resolvedToleranceValue"] == 30


# -- Attribute validation tests ----------------------------------------------


@pytest.mark.asyncio
async def test_rejects_non_temporal_left_actuality_attribute() -> None:
    params = {
        "checkType": "CORRECT",
        "sourceDataObjectVersionId": "v-left",
        "referenceDataObjectVersionId": "v-right",
        "joinKeys": [{"leftAttribute": "left_key", "rightAttribute": "right_key"}],
        "comparison": {"leftAttribute": "left_value", "rightAttribute": "right_value"},
        "actualityDate": {
            "leftAttribute": "left_value",  # not temporal
            "rightAttribute": "right_updated_at",
            "toleranceSource": "DELIVERY_CONTRACT",
            "contractId": "c1",
        },
    }
    with pytest.raises(HTTPException, match="must be date/timestamp compatible"):
        await apply_actuality_date_resolution(
            check_type="CORRECT",
            check_type_params=params,
            catalog_repository=_build_repo(),
            actuality_dispatcher=_build_dispatcher(),
        )


@pytest.mark.asyncio
async def test_rejects_missing_actuality_attribute() -> None:
    params = {
        "checkType": "CORRECT",
        "sourceDataObjectVersionId": "v-left",
        "referenceDataObjectVersionId": "v-right",
        "joinKeys": [{"leftAttribute": "left_key", "rightAttribute": "right_key"}],
        "comparison": {"leftAttribute": "left_value", "rightAttribute": "right_value"},
        "actualityDate": {
            "leftAttribute": "nonexistent",
            "rightAttribute": "right_updated_at",
            "toleranceSource": "DELIVERY_CONTRACT",
            "contractId": "c1",
        },
    }
    with pytest.raises(HTTPException, match="not found"):
        await apply_actuality_date_resolution(
            check_type="CORRECT",
            check_type_params=params,
            catalog_repository=_build_repo(),
            actuality_dispatcher=_build_dispatcher(),
        )
