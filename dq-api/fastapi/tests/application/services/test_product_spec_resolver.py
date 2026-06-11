from __future__ import annotations

import pytest

from app.application.services.product_spec_resolver import OpenMetadataProductSpecResolver
from app.application.services.product_spec_resolver import ProductSpecLookupError


def _build_resolver() -> OpenMetadataProductSpecResolver:
    return OpenMetadataProductSpecResolver(
        provider="openmetadata",
        endpoint="https://openmetadata.example.com",
        api_key="token",
        timeout_seconds=30,
    )


def test_normalize_product_spec_uses_openmetadata_metadata_and_contract_refs() -> None:
    resolver = _build_resolver()

    payload = {
        "id": "om-product-spec-1",
        "name": "ps.retail_banking_customer_360",
        "displayName": "Retail Banking Customer 360",
        "description": "Governed product boundary covering retail banking customer experiences.",
        "version": "2.1.0",
        "status": "active",
        "owners": [{"displayName": "customer-domain-owner"}],
        "entityType": "glossary_term",
        "extension": {
            "product_spec_id": "ps.retail_banking_customer_360",
            "product_name": "Retail Banking Customer 360",
            "product_version": "2.1.0",
            "product_lifecycle_state": "active",
            "product_owner": "customer-domain-owner",
            "product_objective": "Provide governed customer intelligence for retail banking workflows.",
            "product_scope": {"domains": ["retail_banking"], "included_entities": ["customer", "account"]},
            "business_definition": "Retail banking product boundary and governing meaning.",
            "registry_definition_ids": ["def.data_product.retail_banking", "def.data_object.customer"],
            "odcs_contract_refs": [
                {
                    "odcs_contract_id": "odcs.retail_banking.customer_360.delivery",
                    "odcs_contract_name": "Retail Banking Customer 360 Delivery",
                    "odcs_contract_version": "1.0.0",
                }
            ],
            "provenance": {
                "created_by": "platform",
                "approved_by": "customer-domain-owner",
            },
        },
    }

    normalized = resolver._normalize_product_spec(payload, "ps.retail_banking_customer_360")

    assert normalized["product_spec_id"] == "ps.retail_banking_customer_360"
    assert normalized["product_name"] == "Retail Banking Customer 360"
    assert normalized["product_version"] == "2.1.0"
    assert normalized["product_lifecycle_state"] == "active"
    assert normalized["product_owner"] == "customer-domain-owner"
    assert normalized["product_objective"].startswith("Provide governed customer intelligence")
    assert normalized["product_scope"]["domains"] == ["retail_banking"]
    assert normalized["registry_definition_ids"] == ["def.data_product.retail_banking", "def.data_object.customer"]
    assert normalized["odcs_contract_refs"][0]["odcs_contract_id"] == "odcs.retail_banking.customer_360.delivery"
    assert normalized["provenance"]["created_by"] == "platform"


def test_normalize_product_spec_parses_stringified_contract_refs() -> None:
    resolver = _build_resolver()

    payload = {
        "id": "om-product-spec-1",
        "name": "ps.retail_banking_customer_360",
        "displayName": "Retail Banking Customer 360",
        "description": "Governed product boundary covering retail banking customer experiences.",
        "extension": {
            "product_spec_id": "ps.retail_banking_customer_360",
            "product_name": "Retail Banking Customer 360",
            "business_definition": "Retail banking product boundary and governing meaning.",
            "odcs_contract_refs": "[{\"odcs_contract_id\":\"urn:dq:contract:retail-banking-customer-360-delivery\",\"odcs_contract_name\":\"retail_banking_customer_360_delivery\",\"odcs_contract_version\":\"1.0.0\",\"openmetadata_entity_id\":\"7768c0da-5cd9-5cc5-8baa-a26484fd55e8\",\"openmetadata_entity_type\":\"data_contract\",\"source_system\":\"openmetadata\"}]",
        },
    }

    normalized = resolver._normalize_product_spec(payload, "ps.retail_banking_customer_360")

    assert normalized["odcs_contract_refs"] == [
        {
            "odcs_contract_id": "urn:dq:contract:retail-banking-customer-360-delivery",
            "odcs_contract_name": "retail_banking_customer_360_delivery",
            "odcs_contract_version": "1.0.0",
            "openmetadata_entity_id": "7768c0da-5cd9-5cc5-8baa-a26484fd55e8",
            "openmetadata_entity_type": "data_contract",
            "source_system": "openmetadata",
        }
    ]


def test_resolve_product_spec_validates_required_configuration() -> None:
    resolver = _build_resolver()

    with pytest.raises(ProductSpecLookupError) as error:
        resolver._resolve_product_spec_sync("",)

    assert "product_spec_id" in str(error.value)

    wrong_provider = OpenMetadataProductSpecResolver(
        provider="catalog-x",
        endpoint="https://openmetadata.example.com",
        api_key="token",
        timeout_seconds=30,
    )
    with pytest.raises(ProductSpecLookupError) as provider_error:
        wrong_provider._resolve_product_spec_sync("ps.retail_banking_customer_360")
    assert provider_error.value.status_code == 503

    missing_endpoint = OpenMetadataProductSpecResolver(
        provider="openmetadata",
        endpoint="",
        api_key="token",
        timeout_seconds=30,
    )
    with pytest.raises(ProductSpecLookupError) as endpoint_error:
        missing_endpoint._resolve_product_spec_sync("ps.retail_banking_customer_360")
    assert endpoint_error.value.status_code == 503


def test_normalize_product_spec_rejects_missing_contract_references() -> None:
    resolver = _build_resolver()

    with pytest.raises(ProductSpecLookupError) as error:
        resolver._normalize_product_spec(
            {
                "id": "om-product-spec-1",
                "name": "ps.retail_banking_customer_360",
                "description": "Governed product boundary covering retail banking customer experiences.",
                "extension": {
                    "product_spec_id": "ps.retail_banking_customer_360",
                    "business_definition": "Retail banking product boundary and governing meaning.",
                },
            },
            "ps.retail_banking_customer_360",
        )

    assert "ODCS contract references" in str(error.value)


def test_normalize_product_spec_rejects_missing_business_definition() -> None:
    resolver = _build_resolver()

    with pytest.raises(ProductSpecLookupError) as error:
        resolver._normalize_product_spec(
            {
                "id": "om-product-spec-1",
                "name": "ps.retail_banking_customer_360",
                "extension": {
                    "product_spec_id": "ps.retail_banking_customer_360",
                    "odcs_contract_refs": ["odcs.retail_banking.customer_360.delivery"],
                },
            },
            "ps.retail_banking_customer_360",
        )

    assert "business_definition" in str(error.value)


def test_build_product_spec_lookup_paths_and_identifier_matching() -> None:
    resolver = _build_resolver()

    uuid_paths = resolver._build_product_spec_lookup_paths("2c735d55-8070-4c9a-b379-5cc1b05b2de9")
    assert "/v1/glossaryTerms/2c735d55-8070-4c9a-b379-5cc1b05b2de9?fields=description,extension" in uuid_paths
    assert "/v1/glossaryTerms/name/2c735d55-8070-4c9a-b379-5cc1b05b2de9?fields=description,extension" in uuid_paths

    payload = {
        "id": "om-product-spec-1",
        "name": "ps.retail_banking_customer_360",
        "extension": {
            "product_spec_id": "ps.retail_banking_customer_360",
            "odcs_contract_refs": ["odcs.retail_banking.customer_360.delivery"],
            "business_definition": "Retail banking product boundary and governing meaning.",
        },
    }
    assert resolver._matches_product_spec_identifier(payload, "ps.retail_banking_customer_360") is True


def test_resolve_product_spec_falls_back_to_list_scan_when_direct_name_probe_returns_bad_request(monkeypatch) -> None:
    resolver = _build_resolver()

    direct_path = "/v1/glossaryTerms/name/ps.retail_banking_customer_360?fields=description,extension"
    calls: list[tuple[str, bool, bool]] = []

    def _fake_request_json(path: str, *, allow_not_found: bool, allow_bad_request: bool = False):
        calls.append((path, allow_not_found, allow_bad_request))
        if path == direct_path:
            return None
        if path == "/v1/glossaryTerms?fields=description%2Cextension&limit=1000":
            return {
                "data": [
                    {
                        "id": "om-product-spec-1",
                        "name": "ps.retail_banking_customer_360",
                        "displayName": "Retail Banking Customer 360",
                        "description": "Governed product boundary covering retail banking customer experiences.",
                        "version": "1.0.0",
                        "status": "active",
                        "extension": {
                            "product_spec_id": "ps.retail_banking_customer_360",
                            "product_name": "Retail Banking Customer 360",
                            "product_version": "1.0.0",
                            "product_owner": "customer-domain-owner",
                            "product_objective": "Provide governed customer intelligence for retail banking workflows.",
                            "product_scope": {"domains": ["retail_banking"]},
                            "business_definition": "Retail banking product boundary and governing meaning.",
                            "registry_definition_ids": ["def.data_product.retail_banking"],
                            "odcs_contract_refs": [
                                {
                                    "odcs_contract_id": "urn:dq:contract:retail-banking-customer-360-delivery",
                                    "odcs_contract_name": "retail_banking_customer_360_delivery",
                                    "odcs_contract_version": "1.0.0",
                                }
                            ],
                        },
                    }
                ]
            }
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(resolver, "_request_json", _fake_request_json)

    resolved = resolver._resolve_product_spec_sync("ps.retail_banking_customer_360")

    assert resolved["product_spec_id"] == "ps.retail_banking_customer_360"
    assert resolved["odcs_contract_refs"][0]["odcs_contract_id"] == "urn:dq:contract:retail-banking-customer-360-delivery"
    assert calls[0] == (direct_path, True, True)


def test_list_product_specs_filters_and_sorts_inventory(monkeypatch) -> None:
    resolver = _build_resolver()

    def _fake_request_json(path: str, *, allow_not_found: bool, allow_bad_request: bool = False):
        assert path == "/v1/glossaryTerms?fields=description%2Cextension&limit=1000"
        assert allow_not_found is False
        assert allow_bad_request is False
        return {
            "data": [
                {
                    "id": "om-product-spec-2",
                    "name": "ps.wealth_customer_360",
                    "displayName": "Wealth Customer 360",
                    "description": "Governed product boundary for wealth operations.",
                    "extension": {
                        "product_spec_id": "ps.wealth_customer_360",
                        "product_name": "Wealth Customer 360",
                        "product_lifecycle_state": "draft",
                        "product_owner": "wealth-domain-owner",
                        "product_objective": "Provide governed customer intelligence for wealth workflows.",
                        "product_scope": {"domains": ["wealth_banking"]},
                        "business_definition": "Wealth banking product boundary and governing meaning.",
                        "registry_definition_ids": ["def.data_product.wealth_banking"],
                        "odcs_contract_refs": [
                            {
                                "odcs_contract_id": "urn:dq:contract:wealth-customer-360-delivery",
                                "odcs_contract_name": "wealth_customer_360_delivery",
                                "odcs_contract_version": "1.0.0",
                            }
                        ],
                    },
                },
                {
                    "id": "om-product-spec-1",
                    "name": "ps.retail_banking_customer_360",
                    "displayName": "Retail Banking Customer 360",
                    "description": "Governed product boundary covering retail banking customer experiences.",
                    "extension": {
                        "product_spec_id": "ps.retail_banking_customer_360",
                        "product_name": "Retail Banking Customer 360",
                        "product_lifecycle_state": "active",
                        "product_owner": "customer-domain-owner",
                        "product_objective": "Provide governed customer intelligence for retail banking workflows.",
                        "product_scope": {"domains": ["retail_banking"]},
                        "business_definition": "Retail banking product boundary and governing meaning.",
                        "registry_definition_ids": ["def.data_product.retail_banking"],
                        "odcs_contract_refs": [
                            {
                                "odcs_contract_id": "urn:dq:contract:retail-banking-customer-360-delivery",
                                "odcs_contract_name": "retail_banking_customer_360_delivery",
                                "odcs_contract_version": "1.0.0",
                            }
                        ],
                    },
                },
                {
                    "id": "om-glossary-term-1",
                    "name": "customer_status",
                    "description": "Regular glossary term that is not a product spec.",
                    "extension": {},
                },
            ]
        }

    monkeypatch.setattr(resolver, "_request_json", _fake_request_json)

    resolved = resolver._list_product_specs_sync(
        owner="customer-domain-owner",
        lifecycle_state="active",
        registry_definition_id="def.data_product.retail_banking",
        linked_contract_id="urn:dq:contract:retail-banking-customer-360-delivery",
        search="customer 360",
    )

    assert [item["product_spec_id"] for item in resolved] == ["ps.retail_banking_customer_360"]


def test_list_product_specs_rejects_duplicate_product_spec_ids(monkeypatch) -> None:
    resolver = _build_resolver()

    def _fake_request_json(path: str, *, allow_not_found: bool, allow_bad_request: bool = False):
        return {
            "data": [
                {
                    "id": "om-product-spec-1",
                    "name": "ps.retail_banking_customer_360",
                    "description": "Retail banking product boundary.",
                    "extension": {
                        "product_spec_id": "ps.retail_banking_customer_360",
                        "product_name": "Retail Banking Customer 360",
                        "business_definition": "Retail banking product boundary.",
                        "odcs_contract_refs": [{"odcs_contract_id": "urn:dq:contract:retail-banking-customer-360-delivery"}],
                    },
                },
                {
                    "id": "om-product-spec-2",
                    "name": "ps.retail_banking_customer_360",
                    "description": "Retail banking product boundary duplicate.",
                    "extension": {
                        "product_spec_id": "ps.retail_banking_customer_360",
                        "product_name": "Retail Banking Customer 360 Duplicate",
                        "business_definition": "Retail banking product boundary duplicate.",
                        "odcs_contract_refs": [{"odcs_contract_id": "urn:dq:contract:retail-banking-customer-360-delivery-v2"}],
                    },
                },
            ]
        }

    monkeypatch.setattr(resolver, "_request_json", _fake_request_json)

    with pytest.raises(ProductSpecLookupError) as error:
        resolver._list_product_specs_sync(
            owner=None,
            lifecycle_state=None,
            registry_definition_id=None,
            linked_contract_id=None,
            search=None,
        )

    assert error.value.status_code == 409
    assert "duplicate stable identifier" in str(error.value)


def test_create_product_spec_syncs_openmetadata_payload(monkeypatch) -> None:
    resolver = _build_resolver()

    create_calls: list[tuple[str, str, object | None]] = []

    def _fake_resolve_product_spec_sync(product_spec_id: str):
        raise ProductSpecLookupError(f"Product spec '{product_spec_id}' was not found in OpenMetadata", status_code=404)

    def _fake_request_json(
        path: str,
        *,
        allow_not_found: bool,
        allow_bad_request: bool = False,
        method: str = "GET",
        body=None,
        error_context: str = "resolving product specs",
    ):
        create_calls.append((method, path, body))
        if path == "/v1/glossaries" and method == "PUT":
            return {"id": "glossary-1", "fullyQualifiedName": "retail_banking_product_specs"}
        if path == "/v1/metadata/types/name/glossaryTerm" and method == "GET":
            return {"id": "type-glossary-term", "properties": []}
        if path == "/v1/metadata/types/name/string" and method == "GET":
            return {"id": "type-string"}
        if path == "/v1/dataContracts?limit=1000" and method == "GET":
            return {
                "data": [
                    {
                        "id": "om-contract-1",
                        "name": "retail_banking_customer_360_delivery",
                        "sourceUrl": "urn:dq:contract:retail-banking-customer-360-delivery",
                    }
                ]
            }
        if path == "/v1/glossaryTerms" and method == "PUT":
            return {
                "id": "om-product-spec-1",
                "entityType": "glossary_term",
                "name": "ps.retail_banking_customer_360",
                "displayName": "Retail Banking Customer 360",
                "description": "Retail banking product boundary and governing meaning.",
                "extension": body["extension"],
            }
        if path.startswith("/v1/metadata/types/") and method == "PUT":
            return {"ok": True}
        raise AssertionError(f"unexpected call: {method} {path}")

    monkeypatch.setattr(resolver, "_resolve_product_spec_sync", _fake_resolve_product_spec_sync)
    monkeypatch.setattr(resolver, "_request_json", _fake_request_json)

    created = resolver._create_product_spec_sync(
        {
            "glossary": {
                "name": "retail_banking_product_specs",
                "display_name": "Retail Banking Product Specs",
                "description": "Governed ODPS-aligned retail banking product specifications.",
            },
            "product_spec_id": "ps.retail_banking_customer_360",
            "product_name": "Retail Banking Customer 360",
            "product_version": "1.0.0",
            "product_lifecycle_state": "active",
            "product_owner": "customer-domain-owner",
            "product_objective": "Provide governed customer intelligence for retail banking workflows.",
            "product_scope": {"domains": ["retail_banking"]},
            "business_definition": "Retail banking product boundary and governing meaning.",
            "registry_definition_ids": ["def.data_product.retail_banking"],
            "odcs_contract_refs": [
                {
                    "odcs_contract_id": "urn:dq:contract:retail-banking-customer-360-delivery",
                    "odcs_contract_name": "retail_banking_customer_360_delivery",
                    "odcs_contract_version": "1.0.0",
                }
            ],
            "provenance": {"created_by": "platform"},
        }
    )

    assert created["product_spec_id"] == "ps.retail_banking_customer_360"
    assert created["openmetadata_entity_id"] == "om-product-spec-1"
    assert created["odcs_contract_refs"][0]["openmetadata_entity_id"] == "om-contract-1"
    assert any(call[:2] == ("PUT", "/v1/glossaryTerms") for call in create_calls)


def test_update_product_spec_rejects_stable_identifier_mismatch() -> None:
    resolver = _build_resolver()

    with pytest.raises(ProductSpecLookupError) as error:
        resolver._update_product_spec_sync(
            "ps.retail_banking_customer_360",
            {
                "glossary": {
                    "name": "retail_banking_product_specs",
                    "display_name": "Retail Banking Product Specs",
                    "description": "Governed ODPS-aligned retail banking product specifications.",
                },
                "product_spec_id": "ps.wealth_customer_360",
                "product_name": "Retail Banking Customer 360",
                "product_version": "1.0.0",
                "product_lifecycle_state": "active",
                "product_owner": "customer-domain-owner",
                "product_objective": "Provide governed customer intelligence for retail banking workflows.",
                "product_scope": {"domains": ["retail_banking"]},
                "business_definition": "Retail banking product boundary and governing meaning.",
                "registry_definition_ids": ["def.data_product.retail_banking"],
                "odcs_contract_refs": [
                    {
                        "odcs_contract_id": "urn:dq:contract:retail-banking-customer-360-delivery",
                        "odcs_contract_name": "retail_banking_customer_360_delivery",
                        "odcs_contract_version": "1.0.0",
                    }
                ],
                "provenance": {"created_by": "platform"},
            },
        )

    assert error.value.status_code == 409
    assert "same stable product_spec_id" in str(error.value)


def test_normalize_product_spec_reads_migration_metadata() -> None:
    resolver = _build_resolver()

    payload = {
        "id": "om-product-spec-1",
        "name": "ps.retail_banking_customer_360",
        "displayName": "Retail Banking Customer 360",
        "description": "Governed product boundary covering retail banking customer experiences.",
        "extension": {
            "product_spec_id": "ps.retail_banking_customer_360",
            "product_name": "Retail Banking Customer 360",
            "business_definition": "Retail banking product boundary and governing meaning.",
            "odcs_contract_refs": [
                {
                    "odcs_contract_id": "urn:dq:contract:retail-banking-customer-360-delivery",
                    "odcs_contract_name": "retail_banking_customer_360_delivery",
                    "odcs_contract_version": "1.0.0",
                }
            ],
            "migration": {
                "legacy_product_ids": ["legacy.customer_360"],
                "retirement_plan": {"phase": "sunset", "target_date": "2026-12-31"},
            },
        },
    }

    normalized = resolver._normalize_product_spec(payload, "ps.retail_banking_customer_360")

    assert normalized["migration"]["legacy_product_ids"] == ["legacy.customer_360"]
    assert normalized["migration"]["retirement_plan"]["phase"] == "sunset"


def test_import_product_specs_sync_reports_create_update_and_dry_run(monkeypatch) -> None:
    resolver = _build_resolver()
    synced: list[str] = []

    existing = {
        "product_spec_id": "ps.existing",
        "product_name": "Existing Product",
        "business_definition": "Existing product definition.",
        "odcs_contract_refs": [{"odcs_contract_id": "urn:dq:contract:existing"}],
    }

    def _fake_resolve_product_spec_sync(product_spec_id: str):
        if product_spec_id == "ps.existing":
            return existing
        raise ProductSpecLookupError(f"Product spec '{product_spec_id}' was not found in OpenMetadata", status_code=404)

    def _fake_sync_product_spec(payload: dict[str, object]):
        synced.append(str(payload["product_spec_id"]))
        return {
            "product_spec_id": payload["product_spec_id"],
            "product_name": payload["product_name"],
            "product_version": payload["product_version"],
            "product_lifecycle_state": payload["product_lifecycle_state"],
            "product_owner": payload["product_owner"],
            "product_objective": payload["product_objective"],
            "product_scope": payload["product_scope"],
            "business_definition": payload["business_definition"],
            "registry_definition_ids": payload["registry_definition_ids"],
            "odcs_contract_refs": payload["odcs_contract_refs"],
            "openmetadata_entity_id": f"om-{payload['product_spec_id']}",
            "openmetadata_entity_type": "glossary_term",
            "source_system": "openmetadata",
            "provenance": payload["provenance"],
            "migration": payload["migration"],
        }

    monkeypatch.setattr(resolver, "_resolve_product_spec_sync", _fake_resolve_product_spec_sync)
    monkeypatch.setattr(resolver, "_sync_product_spec", _fake_sync_product_spec)

    payload = {
        "glossary": {
            "name": "retail_banking_product_specs",
            "display_name": "Retail Banking Product Specs",
            "description": "Governed ODPS-aligned retail banking product specifications.",
        },
        "product_specs": [
            {
                "product_spec_id": "ps.existing",
                "product_name": "Existing Product",
                "product_version": "1.1.0",
                "product_lifecycle_state": "active",
                "product_owner": "customer-domain-owner",
                "product_objective": "Maintain existing governed coverage.",
                "product_scope": {"domains": ["retail_banking"]},
                "business_definition": "Existing product definition.",
                "registry_definition_ids": ["def.data_product.retail_banking"],
                "odcs_contract_refs": [
                    {
                        "odcs_contract_id": "urn:dq:contract:existing",
                        "odcs_contract_name": "existing_contract",
                        "odcs_contract_version": "1.0.0",
                    }
                ],
                "provenance": {"created_by": "platform"},
                "migration": {"legacy_product_ids": ["legacy.existing"]},
            },
            {
                "product_spec_id": "ps.new",
                "product_name": "New Product",
                "product_version": "1.0.0",
                "product_lifecycle_state": "draft",
                "product_owner": "customer-domain-owner",
                "product_objective": "Introduce a new governed product.",
                "product_scope": {"domains": ["retail_banking"]},
                "business_definition": "New product definition.",
                "registry_definition_ids": ["def.data_product.retail_banking"],
                "odcs_contract_refs": [
                    {
                        "odcs_contract_id": "urn:dq:contract:new",
                        "odcs_contract_name": "new_contract",
                        "odcs_contract_version": "1.0.0",
                    }
                ],
                "provenance": {"created_by": "platform"},
                "migration": {"legacy_product_ids": ["legacy.new"]},
            },
        ],
    }

    dry_run_report = resolver._import_product_specs_sync(payload, True)
    assert dry_run_report["dry_run"] is True
    assert dry_run_report["validated"] == 2
    assert dry_run_report["items"][0]["outcome"] == "would_update"
    assert dry_run_report["items"][1]["outcome"] == "would_create"

    report = resolver._import_product_specs_sync(payload, False)
    assert report["dry_run"] is False
    assert report["updated"] == 1
    assert report["created"] == 1
    assert report["items"][0]["outcome"] == "updated"
    assert report["items"][1]["outcome"] == "created"
    assert synced == ["ps.existing", "ps.new"]


def test_apply_stewardship_action_sync_transitions_lifecycle(monkeypatch) -> None:
    resolver = _build_resolver()

    existing = {
        "product_spec_id": "ps.retail_banking_customer_360",
        "product_name": "Retail Banking Customer 360",
        "product_version": "1.0.0",
        "product_lifecycle_state": "draft",
        "product_owner": "customer-domain-owner",
        "product_objective": "Provide governed customer intelligence.",
        "product_scope": {"domains": ["retail_banking"]},
        "business_definition": "Retail banking product boundary.",
        "registry_definition_ids": ["def.data_product.retail_banking"],
        "odcs_contract_refs": [
            {
                "odcs_contract_id": "urn:dq:contract:retail-banking-customer-360-delivery",
                "odcs_contract_name": "retail_banking_customer_360_delivery",
                "odcs_contract_version": "1.0.0",
            }
        ],
        "provenance": {"created_by": "platform"},
        "migration": {},
    }

    captured_payload: dict[str, object] = {}

    def _fake_resolve_product_spec_sync(product_spec_id: str):
        assert product_spec_id == "ps.retail_banking_customer_360"
        return existing

    def _fake_sync_product_spec(payload: dict[str, object]):
        captured_payload.update(payload)
        return {
            **existing,
            "product_lifecycle_state": payload["product_lifecycle_state"],
            "provenance": payload["provenance"],
        }

    monkeypatch.setattr(resolver, "_resolve_product_spec_sync", _fake_resolve_product_spec_sync)
    monkeypatch.setattr(resolver, "_sync_product_spec", _fake_sync_product_spec)

    updated = resolver._apply_stewardship_action_sync(
        "ps.retail_banking_customer_360",
        {
            "glossary": {
                "name": "retail_banking_product_specs",
                "display_name": "Retail Banking Product Specs",
                "description": "Governed ODPS-aligned retail banking product specifications.",
            },
            "action": "approve",
            "actor": "customer-domain-owner",
            "change_reason": "Approved by governance board",
        },
    )

    assert captured_payload["product_lifecycle_state"] == "active"
    assert updated["product_lifecycle_state"] == "active"
    assert updated["provenance"]["change_reason"] == "Approved by governance board"


def test_summarize_product_specs_sync_aggregates_by_owner_and_lifecycle(monkeypatch) -> None:
    resolver = _build_resolver()

    monkeypatch.setattr(
        resolver,
        "_list_product_specs_sync",
        lambda owner, lifecycle_state, registry_definition_id, linked_contract_id, search: [
            {
                "product_spec_id": "ps.retail_banking_customer_360",
                "product_lifecycle_state": "active",
                "product_owner": "customer-domain-owner",
            },
            {
                "product_spec_id": "ps.wealth_customer_360",
                "product_lifecycle_state": "draft",
                "product_owner": "wealth-domain-owner",
            },
            {
                "product_spec_id": "ps.cards_customer_360",
                "product_lifecycle_state": "active",
                "product_owner": "customer-domain-owner",
            },
        ],
    )

    summary = resolver._summarize_product_specs_sync()

    assert summary["total"] == 3
    assert summary["by_lifecycle_state"] == {"active": 2, "draft": 1}
    assert summary["by_owner"] == {"customer-domain-owner": 2, "wealth-domain-owner": 1}


def test_apply_stewardship_action_sync_fails_fast_when_existing_payload_is_incomplete(monkeypatch) -> None:
    resolver = _build_resolver()

    monkeypatch.setattr(
        resolver,
        "_resolve_product_spec_sync",
        lambda product_spec_id: {
            "product_spec_id": product_spec_id,
            "product_name": "Retail Banking Customer 360",
            "product_version": "1.0.0",
            "product_lifecycle_state": "draft",
            "product_owner": "customer-domain-owner",
            "product_objective": "Provide governed customer intelligence.",
            "product_scope": {"domains": ["retail_banking"]},
            "business_definition": "Retail banking product boundary.",
            "registry_definition_ids": ["def.data_product.retail_banking"],
            "odcs_contract_refs": [],
            "provenance": {"created_by": "platform"},
            "migration": {},
        },
    )

    with pytest.raises(ProductSpecLookupError) as error:
        resolver._apply_stewardship_action_sync(
            "ps.retail_banking_customer_360",
            {
                "glossary": {
                    "name": "retail_banking_product_specs",
                    "display_name": "Retail Banking Product Specs",
                    "description": "Governed ODPS-aligned retail banking product specifications.",
                },
                "action": "approve",
                "actor": "customer-domain-owner",
                "change_reason": "Approved by governance board",
            },
        )

    assert error.value.status_code == 422
    assert "existing odcs_contract_refs" in str(error.value)
