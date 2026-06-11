import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.application.services import rule_join_consistency_mapping as rules_join_consistency_support


def _make_base_params():
    return {
        "leftDataObjectVersionId": "lv",
        "rightDataObjectVersionId": "rv",
        "joinKeys": [{"leftAttribute": "la", "rightAttribute": "ra"}],
        "comparisons": [{"leftAttribute": "ca", "rightAttribute": "cb", "mode": "exact"}],
        "actualityDate": {"leftAttribute": "la", "rightAttribute": "ra", "contractId": "cid"},
        "minMatchRate": 99.0,
    }


def test_apply_join_consistency_invalid_schema_raises():
    # empty params will fail TypeAdapter validation
    with pytest.raises(HTTPException):
        asyncio.run(
            rules_join_consistency_support.apply_join_consistency_contract_mapping(
                check_type="JOIN_CONSISTENCY",
                check_type_params={},
                catalog_repository=None,
                contract_resolver=None,
                contract_cache_ttl_seconds=300,
            )
        )


def test_apply_join_consistency_left_version_missing_raises():
    params = _make_base_params()

    class _Catalog:
        def list_data_object_versions(self):
            # does not include left 'lv' -> should raise
            return [SimpleNamespace(id="other", data_object_id="obj")]

    with pytest.raises(HTTPException):
        asyncio.run(
            rules_join_consistency_support.apply_join_consistency_contract_mapping(
                check_type="JOIN_CONSISTENCY",
                check_type_params=params,
                catalog_repository=_Catalog(),
                contract_resolver=None,
                contract_cache_ttl_seconds=300,
            )
        )


def test_apply_join_consistency_missing_attribute_raises():
    params = _make_base_params()

    class _Catalog:
        def list_data_object_versions(self):
            return [SimpleNamespace(id="lv", data_object_id="obj"), SimpleNamespace(id="rv", data_object_id="obj")]

        def list_data_objects_catalog(self):
            return [SimpleNamespace(id="obj", dataset_id="ds")]

        def list_attributes_catalog(self, version_id):
            # attributes do not include required 'la' and 'ra'
            return [SimpleNamespace(name="x", type="varchar")]

    with pytest.raises(HTTPException):
        asyncio.run(
            rules_join_consistency_support.apply_join_consistency_contract_mapping(
                check_type="JOIN_CONSISTENCY",
                check_type_params=params,
                catalog_repository=_Catalog(),
                contract_resolver=None,
                contract_cache_ttl_seconds=300,
            )
        )


def test_apply_join_consistency_success_resolves_contract_and_returns_params():
    params = _make_base_params()

    class _Catalog:
        def list_data_object_versions(self):
            return [SimpleNamespace(id="lv", data_object_id="obj"), SimpleNamespace(id="rv", data_object_id="obj")]

        def list_data_objects_catalog(self):
            return [SimpleNamespace(id="obj", dataset_id="ds")]

        def list_attributes_catalog(self, version_id):
            return [
                SimpleNamespace(name="la", type="timestamp"),
                SimpleNamespace(name="ra", type="timestamp"),
                SimpleNamespace(name="ca", type="timestamp"),
                SimpleNamespace(name="cb", type="timestamp"),
            ]

    class _Resolver:
        async def resolve_contract_policy(self, contract_id, dataset_id, cache_ttl_seconds):
            return {
                "overrideAllowed": False,
                "resolvedToleranceValue": 10,
                "resolvedToleranceUnit": "days",
                "contractVersion": "cv1",
            }

    out = asyncio.run(
        rules_join_consistency_support.apply_join_consistency_contract_mapping(
            check_type="JOIN_CONSISTENCY",
            check_type_params=params,
            catalog_repository=_Catalog(),
            contract_resolver=_Resolver(),
            contract_cache_ttl_seconds=300,
        )
    )

    assert isinstance(out, dict)
    ad = out.get("actualityDate") or {}
    assert ad.get("resolvedToleranceValue") == 10
    assert ad.get("resolvedToleranceUnit") == "days"
    assert ad.get("contractVersion") == "cv1"
