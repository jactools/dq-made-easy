from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.domain.entities import rule_policy as rules_support


def test_derive_rule_status_from_row_variants() -> None:
    assert rules_support.derive_rule_status_from_row({"removed": True}) == "removed"
    assert rules_support.derive_rule_status_from_row({"active": True}) == "activated"
    assert rules_support.derive_rule_status_from_row({"last_approval_status": "pending"}) == "pending-approval"
    assert rules_support.derive_rule_status_from_row({}) == "draft"


def test_derive_rule_lifecycle_status_from_row_variants() -> None:
    assert rules_support.derive_rule_lifecycle_status_from_row({}) == "active"
    assert rules_support.derive_rule_lifecycle_status_from_row({"lifecycle_status": "deprecated"}) == "deprecated"
    assert rules_support.derive_rule_lifecycle_status_from_row({"removed": True}) == "retired"


def test_normalize_rule_row_contract_populates_lifecycle_status() -> None:
    payload = rules_support.normalize_rule_row_contract({"id": "rule-1", "name": "Rule 1"})

    assert payload["lifecycle_status"] == "active"


def test_ensure_unique_rule_name_empty_and_duplicates() -> None:
    with pytest.raises(HTTPException):
        asyncio.run(rules_support.ensure_unique_rule_name(repository=None, name="", workspace="ws"))

    class _DupRepo:
        def __init__(self, rows):
            self._rows = rows

        async def list_rule_records(self, workspace, include_deleted, is_template, limit, offset):
            del workspace, include_deleted, is_template, limit, offset
            return self._rows

    dup_repo = _DupRepo([{"id": "r1", "name": "MyRule"}])
    with pytest.raises(HTTPException):
        asyncio.run(rules_support.ensure_unique_rule_name(repository=dup_repo, name=" myrule ", workspace="ws"))

    ok_repo = _DupRepo([])
    asyncio.run(rules_support.ensure_unique_rule_name(repository=ok_repo, name="Unique", workspace="ws"))


def test_apply_referential_integrity_version_mapping_variants() -> None:
    class _Catalog:
        def list_data_object_versions(self):
            return [SimpleNamespace(id="v1", data_object_id="obj123")]

        def list_attributes_catalog(self, version_id):
            del version_id
            return [SimpleNamespace(name="attr1"), SimpleNamespace(name="attr2")]

    assert rules_support.apply_referential_integrity_version_mapping(
        check_type="OTHER",
        check_type_params={"a": 1},
        catalog_repository=_Catalog(),
    ) == {"a": 1}

    with pytest.raises(HTTPException):
        rules_support.apply_referential_integrity_version_mapping(
            check_type="REFERENTIAL_INTEGRITY",
            check_type_params=None,
            catalog_repository=_Catalog(),
        )

    params = {"refDataObjectVersionId": "v1", "refDataObjectId": "", "refAttribute": "attr1"}
    out = rules_support.apply_referential_integrity_version_mapping(
        check_type="REFERENTIAL_INTEGRITY",
        check_type_params=params,
        catalog_repository=_Catalog(),
    )
    assert out.get("refDataObjectId") == "obj123"
