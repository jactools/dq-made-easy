from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from app.application.services.data_contract_resolver import DataContractLookupError
from app.application.services.rule_join_consistency_mapping import (
    apply_join_consistency_contract_mapping,
)


@dataclass(frozen=True)
class _CatalogVersion:
    id: str
    data_object_id: str


@dataclass(frozen=True)
class _CatalogObject:
    id: str
    dataset_id: str


@dataclass(frozen=True)
class _CatalogAttribute:
    name: str
    type: str


class _CatalogRepository:
    def __init__(self, versions: list[_CatalogVersion], objects: list[_CatalogObject], attributes: dict[str, list[_CatalogAttribute]]) -> None:
        self._versions = versions
        self._objects = objects
        self._attributes = attributes

    def list_data_object_versions(self) -> list[_CatalogVersion]:
        return list(self._versions)

    def list_data_objects_catalog(self) -> list[_CatalogObject]:
        return list(self._objects)

    def list_attributes_catalog(self, version_id: str) -> list[_CatalogAttribute]:
        return list(self._attributes.get(version_id, []))


class _ContractResolver:
    def __init__(self, policy: dict | None = None, error: Exception | None = None) -> None:
        self._policy = policy or {}
        self._error = error

    async def resolve_contract_policy(self, contract_id: str, *, dataset_id: str | None = None, cache_ttl_seconds: int | None = None) -> dict:
        del contract_id, dataset_id, cache_ttl_seconds
        if self._error is not None:
            raise self._error
        return dict(self._policy)


def _build_valid_params(**extra_actuality_date: object) -> dict:
    actuality_date = {
        "leftAttribute": "left_updated_at",
        "rightAttribute": "right_updated_at",
        "toleranceSource": "DELIVERY_CONTRACT",
        "contractId": "contract-1",
    }
    actuality_date.update(extra_actuality_date)
    return {
        "checkType": "JOIN_CONSISTENCY",
        "leftDataObjectVersionId": "left-version",
        "rightDataObjectVersionId": "right-version",
        "joinKeys": [
            {"leftAttribute": "left_key", "rightAttribute": "right_key"},
        ],
        "comparisons": [
            {"leftAttribute": "left_value", "rightAttribute": "right_value", "mode": "exact"},
        ],
        "actualityDate": actuality_date,
        "minMatchRate": 90,
    }


def _build_repository(left_dataset_id: str = "dataset-1", right_dataset_id: str = "dataset-1") -> _CatalogRepository:
    versions = [
        _CatalogVersion(id="left-version", data_object_id="left-object"),
        _CatalogVersion(id="right-version", data_object_id="right-object"),
    ]
    objects = [
        _CatalogObject(id="left-object", dataset_id=left_dataset_id),
        _CatalogObject(id="right-object", dataset_id=right_dataset_id),
    ]
    attributes = {
        "left-version": [
            _CatalogAttribute(name="left_key", type="string"),
            _CatalogAttribute(name="left_value", type="string"),
            _CatalogAttribute(name="left_updated_at", type="datetime"),
        ],
        "right-version": [
            _CatalogAttribute(name="right_key", type="string"),
            _CatalogAttribute(name="right_value", type="string"),
            _CatalogAttribute(name="right_updated_at", type="datetime"),
        ],
    }
    return _CatalogRepository(versions=versions, objects=objects, attributes=attributes)


def test_apply_join_consistency_contract_mapping_passthrough_for_other_check_types() -> None:
    params = {"checkType": "ROW_COUNT", "threshold": 10}

    result = asyncio.run(
        apply_join_consistency_contract_mapping(
            check_type="ROW_COUNT",
            check_type_params=params,
            catalog_repository=_build_repository(),
            contract_resolver=_ContractResolver(),
            contract_cache_ttl_seconds=30,
        )
    )

    assert result is params


def test_apply_join_consistency_contract_mapping_resolves_policy_without_override() -> None:
    result = asyncio.run(
        apply_join_consistency_contract_mapping(
            check_type="JOIN_CONSISTENCY",
            check_type_params=_build_valid_params(),
            catalog_repository=_build_repository(),
            contract_resolver=_ContractResolver(
                policy={
                    "overrideAllowed": True,
                    "resolvedToleranceValue": 2,
                    "resolvedToleranceUnit": "days",
                    "contractVersion": "2026.05",
                }
            ),
            contract_cache_ttl_seconds=30,
        ),
    )

    assert result is not None
    assert result["actualityDate"]["resolvedToleranceValue"] == 2
    assert result["actualityDate"]["resolvedToleranceUnit"] == "days"
    assert result["actualityDate"]["contractVersion"] == "2026.05"


def test_apply_join_consistency_contract_mapping_resolves_override_within_bounds() -> None:
    result = asyncio.run(
        apply_join_consistency_contract_mapping(
            check_type="JOIN_CONSISTENCY",
            check_type_params=_build_valid_params(overrideToleranceValue=3, overrideToleranceUnit="days"),
            catalog_repository=_build_repository(),
            contract_resolver=_ContractResolver(
                policy={
                    "overrideAllowed": True,
                    "maxOverrideToleranceValue": 5,
                    "maxOverrideToleranceUnit": "days",
                    "resolvedToleranceValue": 2,
                    "resolvedToleranceUnit": "days",
                    "contractVersion": "2026.05",
                }
            ),
            contract_cache_ttl_seconds=30,
        ),
    )

    assert result is not None
    assert result["actualityDate"]["resolvedToleranceValue"] == 3
    assert result["actualityDate"]["resolvedToleranceUnit"] == "days"


def test_apply_join_consistency_contract_mapping_rejects_missing_join_attribute() -> None:
    params = _build_valid_params()
    params["joinKeys"] = [{"leftAttribute": "missing", "rightAttribute": "right_key"}]

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            apply_join_consistency_contract_mapping(
                check_type="JOIN_CONSISTENCY",
                check_type_params=params,
                catalog_repository=_build_repository(),
                contract_resolver=_ContractResolver(
                    policy={
                        "overrideAllowed": True,
                        "resolvedToleranceValue": 2,
                        "resolvedToleranceUnit": "days",
                        "contractVersion": "2026.05",
                    }
                ),
                contract_cache_ttl_seconds=30,
            ),
        )

    assert exc_info.value.status_code == 400
    assert "left attribute 'missing'" in str(exc_info.value.detail)


def test_apply_join_consistency_contract_mapping_rejects_non_temporal_actuality_attribute() -> None:
    params = _build_valid_params()
    params["actualityDate"]["leftAttribute"] = "left_value"

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            apply_join_consistency_contract_mapping(
                check_type="JOIN_CONSISTENCY",
                check_type_params=params,
                catalog_repository=_build_repository(),
                contract_resolver=_ContractResolver(
                    policy={
                        "overrideAllowed": True,
                        "resolvedToleranceValue": 2,
                        "resolvedToleranceUnit": "days",
                        "contractVersion": "2026.05",
                    }
                ),
                contract_cache_ttl_seconds=30,
            ),
        )

    assert exc_info.value.status_code == 400
    assert "actuality-date attribute must be date/timestamp compatible" in str(exc_info.value.detail)


def test_apply_join_consistency_contract_mapping_maps_lookup_error_and_override_policy() -> None:
    base_params = _build_valid_params(overrideToleranceValue=6, overrideToleranceUnit="days")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            apply_join_consistency_contract_mapping(
                check_type="JOIN_CONSISTENCY",
                check_type_params=base_params,
                catalog_repository=_build_repository(),
                contract_resolver=_ContractResolver(
                    error=DataContractLookupError("contract not found", status_code=503)
                ),
                contract_cache_ttl_seconds=30,
            ),
        )

    assert exc_info.value.status_code == 503
    assert str(exc_info.value.detail) == "contract not found"

    with pytest.raises(HTTPException) as override_exc_info:
        asyncio.run(
            apply_join_consistency_contract_mapping(
                check_type="JOIN_CONSISTENCY",
                check_type_params=base_params,
                catalog_repository=_build_repository(),
                contract_resolver=_ContractResolver(
                    policy={
                        "overrideAllowed": False,
                        "resolvedToleranceValue": 2,
                        "resolvedToleranceUnit": "days",
                        "contractVersion": "2026.05",
                    }
                ),
                contract_cache_ttl_seconds=30,
            ),
        )

    assert override_exc_info.value.status_code == 400
    assert "does not allow actuality-date tolerance overrides" in str(override_exc_info.value.detail)


def test_apply_join_consistency_contract_mapping_rejects_invalid_payload_shape() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            apply_join_consistency_contract_mapping(
                check_type="JOIN_CONSISTENCY",
                check_type_params={"checkType": "JOIN_CONSISTENCY", "leftDataObjectVersionId": "left-version"},
                catalog_repository=_build_repository(),
                contract_resolver=_ContractResolver(),
                contract_cache_ttl_seconds=30,
            ),
        )

    assert exc_info.value.status_code == 400
    assert "validation error" in str(exc_info.value.detail).lower()


def test_apply_join_consistency_contract_mapping_rejects_override_above_policy_bound() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            apply_join_consistency_contract_mapping(
                check_type="JOIN_CONSISTENCY",
                check_type_params=_build_valid_params(overrideToleranceValue=6, overrideToleranceUnit="days"),
                catalog_repository=_build_repository(),
                contract_resolver=_ContractResolver(
                    policy={
                        "overrideAllowed": True,
                        "maxOverrideToleranceValue": 5,
                        "maxOverrideToleranceUnit": "days",
                        "resolvedToleranceValue": 2,
                        "resolvedToleranceUnit": "days",
                        "contractVersion": "2026.05",
                    }
                ),
                contract_cache_ttl_seconds=30,
            ),
        )

    assert exc_info.value.status_code == 400
    assert "override exceeds contract policy bound" in str(exc_info.value.detail)


@pytest.mark.parametrize(
    ("repo_factory", "params_mutator", "expected_message"),
    [
        (
            lambda: _CatalogRepository(
                versions=[_CatalogVersion(id="left-version", data_object_id="left-object")],
                objects=[
                    _CatalogObject(id="left-object", dataset_id="dataset-1"),
                    _CatalogObject(id="right-object", dataset_id="dataset-1"),
                ],
                attributes={
                    "left-version": [
                        _CatalogAttribute(name="left_key", type="string"),
                        _CatalogAttribute(name="left_value", type="string"),
                        _CatalogAttribute(name="left_updated_at", type="datetime"),
                    ],
                    "right-version": [
                        _CatalogAttribute(name="right_key", type="string"),
                        _CatalogAttribute(name="right_value", type="string"),
                        _CatalogAttribute(name="right_updated_at", type="datetime"),
                    ],
                },
            ),
            lambda params: params,
            "JOIN_CONSISTENCY right data object version 'right-version' was not found",
        ),
        (
            lambda: _CatalogRepository(
                versions=[
                    _CatalogVersion(id="left-version", data_object_id="left-object"),
                    _CatalogVersion(id="right-version", data_object_id="missing-object"),
                ],
                objects=[_CatalogObject(id="left-object", dataset_id="dataset-1")],
                attributes={
                    "left-version": [
                        _CatalogAttribute(name="left_key", type="string"),
                        _CatalogAttribute(name="left_value", type="string"),
                        _CatalogAttribute(name="left_updated_at", type="datetime"),
                    ],
                    "right-version": [
                        _CatalogAttribute(name="right_key", type="string"),
                        _CatalogAttribute(name="right_value", type="string"),
                        _CatalogAttribute(name="right_updated_at", type="datetime"),
                    ],
                },
            ),
            lambda params: params,
            "JOIN_CONSISTENCY could not resolve dataset scope for data object version 'right-version'",
        ),
        (
            lambda: _CatalogRepository(
                versions=[
                    _CatalogVersion(id="left-version", data_object_id="left-object"),
                    _CatalogVersion(id="right-version", data_object_id="right-object"),
                ],
                objects=[
                    _CatalogObject(id="left-object", dataset_id="dataset-1"),
                    _CatalogObject(id="right-object", dataset_id=""),
                ],
                attributes={
                    "left-version": [
                        _CatalogAttribute(name="left_key", type="string"),
                        _CatalogAttribute(name="left_value", type="string"),
                        _CatalogAttribute(name="left_updated_at", type="datetime"),
                    ],
                    "right-version": [
                        _CatalogAttribute(name="right_key", type="string"),
                        _CatalogAttribute(name="right_value", type="string"),
                        _CatalogAttribute(name="right_updated_at", type="datetime"),
                    ],
                },
            ),
            lambda params: params,
            "JOIN_CONSISTENCY data object version does not map to a dataset-level contract scope: 'right-version'",
        ),
        (
            _build_repository,
            lambda params: params.__setitem__("actualityDate", {**params["actualityDate"], "rightAttribute": "right_value"}) or params,
            "JOIN_CONSISTENCY right actuality-date attribute must be date/timestamp compatible",
        ),
    ],
)
def test_apply_join_consistency_contract_mapping_rejects_additional_fail_fast_paths(
    repo_factory: object,
    params_mutator: object,
    expected_message: str,
) -> None:
    params = _build_valid_params()
    mutated_params = params_mutator(params)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            apply_join_consistency_contract_mapping(
                check_type="JOIN_CONSISTENCY",
                check_type_params=mutated_params,
                catalog_repository=repo_factory(),
                contract_resolver=_ContractResolver(
                    policy={
                        "overrideAllowed": True,
                        "resolvedToleranceValue": 2,
                        "resolvedToleranceUnit": "days",
                        "contractVersion": "2026.05",
                    }
                ),
                contract_cache_ttl_seconds=30,
            ),
        )

    assert exc_info.value.status_code == 400
    assert expected_message in str(exc_info.value.detail)