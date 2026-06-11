from __future__ import annotations

import pytest

from app.application.services.product_spec_resolver import ProductSpecLookupError
from app.core.dependencies import get_product_spec_resolver


class _Resolver:
    def __init__(
        self,
        payload=None,
        error: ProductSpecLookupError | None = None,
        list_payload=None,
        list_error: ProductSpecLookupError | None = None,
        create_payload=None,
        create_error: ProductSpecLookupError | None = None,
        update_payload=None,
        update_error: ProductSpecLookupError | None = None,
        import_payload=None,
        import_error: ProductSpecLookupError | None = None,
        stewardship_payload=None,
        stewardship_error: ProductSpecLookupError | None = None,
        summary_payload=None,
        summary_error: ProductSpecLookupError | None = None,
    ) -> None:
        self._payload = payload
        self._error = error
        self._list_payload = list_payload
        self._list_error = list_error
        self._create_payload = create_payload
        self._create_error = create_error
        self._update_payload = update_payload
        self._update_error = update_error
        self._import_payload = import_payload
        self._import_error = import_error
        self._stewardship_payload = stewardship_payload
        self._stewardship_error = stewardship_error
        self._summary_payload = summary_payload
        self._summary_error = summary_error

    async def resolve_product_spec(self, product_spec_id: str) -> dict:
        if self._error is not None:
            raise self._error
        payload = dict(self._payload or {})
        payload.setdefault("product_spec_id", product_spec_id)
        return payload

    async def list_product_specs(
        self,
        *,
        owner: str | None = None,
        lifecycle_state: str | None = None,
        registry_definition_id: str | None = None,
        linked_contract_id: str | None = None,
        search: str | None = None,
    ) -> list[dict]:
        if self._list_error is not None:
            raise self._list_error
        items = [dict(item) for item in (self._list_payload if self._list_payload is not None else [self._payload or {}])]
        if owner is not None:
            items = [item for item in items if item.get("product_owner") == owner]
        if lifecycle_state is not None:
            items = [item for item in items if item.get("product_lifecycle_state") == lifecycle_state]
        if registry_definition_id is not None:
            items = [item for item in items if registry_definition_id in item.get("registry_definition_ids", [])]
        if linked_contract_id is not None:
            items = [item for item in items if linked_contract_id in [ref.get("odcs_contract_id") for ref in item.get("odcs_contract_refs", [])]]
        if search is not None:
            lowered = search.lower()
            items = [
                item
                for item in items
                if lowered in str(item.get("product_spec_id", "")).lower()
                or lowered in str(item.get("product_name", "")).lower()
                or lowered in str(item.get("business_definition", "")).lower()
            ]
        return items

    async def create_product_spec(self, payload: dict) -> dict:
        if self._create_error is not None:
            raise self._create_error
        result = dict(self._create_payload or self._payload or {})
        result.setdefault("product_spec_id", payload.get("product_spec_id"))
        return result

    async def update_product_spec(self, product_spec_id: str, payload: dict) -> dict:
        if self._update_error is not None:
            raise self._update_error
        result = dict(self._update_payload or self._payload or {})
        result.setdefault("product_spec_id", product_spec_id)
        return result

    async def import_product_specs(self, payload: dict, *, dry_run: bool = False) -> dict:
        if self._import_error is not None:
            raise self._import_error
        return dict(
            self._import_payload
            or {
                "dry_run": dry_run,
                "total": 1,
                "created": 0 if dry_run else 1,
                "updated": 0,
                "validated": 1 if dry_run else 0,
                "items": [
                    {
                        "product_spec_id": "ps.retail_banking_customer_360",
                        "outcome": "would_create" if dry_run else "created",
                        "product_spec": dict(self._payload or {}) if not dry_run else None,
                    }
                ],
            }
        )

    async def apply_stewardship_action(self, product_spec_id: str, payload: dict) -> dict:
        if self._stewardship_error is not None:
            raise self._stewardship_error
        result = dict(self._stewardship_payload or self._payload or {})
        result.setdefault("product_spec_id", product_spec_id)
        return result

    async def summarize_product_specs(self) -> dict:
        if self._summary_error is not None:
            raise self._summary_error
        return dict(
            self._summary_payload
            or {
                "total": 2,
                "by_lifecycle_state": {"active": 1, "draft": 1},
                "by_owner": {"customer-domain-owner": 1, "wealth-domain-owner": 1},
            }
        )


@pytest.fixture(autouse=True)
def isolated_product_spec_dependency(client):
    resolver = _Resolver(
        payload={
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
            "openmetadata_entity_id": "om-product-spec-1",
            "openmetadata_entity_type": "glossary_term",
            "source_system": "openmetadata",
            "provenance": {"created_by": "platform", "approved_by": "customer-domain-owner"},
        },
        list_payload=[
            {
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
                "openmetadata_entity_id": "om-product-spec-1",
                "openmetadata_entity_type": "glossary_term",
                "source_system": "openmetadata",
                "provenance": {"created_by": "platform", "approved_by": "customer-domain-owner"},
            },
            {
                "product_spec_id": "ps.wealth_customer_360",
                "product_name": "Wealth Customer 360",
                "product_version": "1.4.0",
                "product_lifecycle_state": "draft",
                "product_owner": "wealth-domain-owner",
                "product_objective": "Provide governed customer intelligence for wealth workflows.",
                "product_scope": {"domains": ["wealth_banking"], "included_entities": ["customer", "portfolio"]},
                "business_definition": "Wealth banking product boundary and governing meaning.",
                "registry_definition_ids": ["def.data_product.wealth_banking"],
                "odcs_contract_refs": [
                    {
                        "odcs_contract_id": "odcs.wealth.customer_360.delivery",
                        "odcs_contract_name": "Wealth Customer 360 Delivery",
                        "odcs_contract_version": "1.0.0",
                    }
                ],
                "openmetadata_entity_id": "om-product-spec-2",
                "openmetadata_entity_type": "glossary_term",
                "source_system": "openmetadata",
                "provenance": {"created_by": "platform", "approved_by": "wealth-domain-owner"},
            },
        ],
    )
    client.app.dependency_overrides[get_product_spec_resolver] = lambda: resolver
    yield resolver
    client.app.dependency_overrides.pop(get_product_spec_resolver, None)


def test_get_product_spec_returns_snake_case_payload(client, auth_headers, isolated_product_spec_dependency) -> None:
    response = client.get(
        "/api/data-catalog/v1/product-specs/ps.retail_banking_customer_360",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["product_spec_id"] == "ps.retail_banking_customer_360"
    assert payload["product_name"] == "Retail Banking Customer 360"
    assert payload["product_version"] == "2.1.0"
    assert payload["product_lifecycle_state"] == "active"
    assert payload["product_scope"]["domains"] == ["retail_banking"]
    assert payload["odcs_contract_refs"][0]["odcs_contract_id"] == "odcs.retail_banking.customer_360.delivery"


def test_list_product_specs_returns_paginated_filtered_payload(client, auth_headers, isolated_product_spec_dependency) -> None:
    response = client.get(
        "/api/data-catalog/v1/product-specs",
        params={
            "owner": "customer-domain-owner",
            "lifecycle_state": "active",
            "registry_definition_id": "def.data_product.retail_banking",
            "linked_contract_id": "odcs.retail_banking.customer_360.delivery",
            "search": "customer 360",
            "page": 1,
            "limit": 10,
        },
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["product_spec_id"] == "ps.retail_banking_customer_360"
    assert payload["data"][0]["odcs_contract_refs"][0]["odcs_contract_id"] == "odcs.retail_banking.customer_360.delivery"


def test_summarize_product_specs_returns_aggregated_payload(client, auth_headers, isolated_product_spec_dependency) -> None:
    response = client.get(
        "/api/data-catalog/v1/product-specs/summary",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["by_lifecycle_state"]["active"] == 1


def test_summarize_product_specs_maps_inventory_error(client, auth_headers, isolated_product_spec_dependency) -> None:
    isolated_product_spec_dependency._summary_error = ProductSpecLookupError(
        "OpenMetadata is unavailable while resolving product specs",
        status_code=503,
    )

    response = client.get(
        "/api/data-catalog/v1/product-specs/summary",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"]["error"] == "product_spec_inventory_unavailable"


def test_get_product_spec_maps_not_found_error(client, auth_headers, isolated_product_spec_dependency) -> None:
    isolated_product_spec_dependency._error = ProductSpecLookupError(
        "Product spec 'ps.retail_banking_customer_360' was not found in OpenMetadata",
        status_code=404,
    )

    response = client.get(
        "/api/data-catalog/v1/product-specs/ps.retail_banking_customer_360",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"]["error"] == "product_spec_not_found"
    assert payload["detail"]["product_spec_id"] == "ps.retail_banking_customer_360"


def test_get_product_spec_maps_ambiguous_error(client, auth_headers, isolated_product_spec_dependency) -> None:
    isolated_product_spec_dependency._error = ProductSpecLookupError(
        "Product spec 'ps.retail_banking_customer_360' resolved to multiple OpenMetadata terms",
        status_code=409,
    )

    response = client.get(
        "/api/data-catalog/v1/product-specs/ps.retail_banking_customer_360",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["detail"]["error"] == "product_spec_ambiguous"


def test_get_product_spec_maps_unavailable_error(client, auth_headers, isolated_product_spec_dependency) -> None:
    isolated_product_spec_dependency._error = ProductSpecLookupError(
        "OpenMetadata is unavailable while resolving product specs",
        status_code=503,
    )

    response = client.get(
        "/api/data-catalog/v1/product-specs/ps.retail_banking_customer_360",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"]["error"] == "product_spec_unavailable"


def test_list_product_specs_maps_inventory_error(client, auth_headers, isolated_product_spec_dependency) -> None:
    isolated_product_spec_dependency._list_error = ProductSpecLookupError(
        "OpenMetadata is unavailable while resolving product specs",
        status_code=503,
    )

    response = client.get(
        "/api/data-catalog/v1/product-specs",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"]["error"] == "product_spec_inventory_unavailable"


def test_create_product_spec_returns_created_payload(client, auth_headers, isolated_product_spec_dependency) -> None:
    response = client.post(
        "/api/data-catalog/v1/product-specs",
        json={
            "glossary": {
                "name": "retail_banking_product_specs",
                "display_name": "Retail Banking Product Specs",
                "description": "Governed ODPS-aligned retail banking product specifications.",
            },
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
            "provenance": {"created_by": "platform", "approved_by": "customer-domain-owner"},
        },
        headers=auth_headers("dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["product_spec_id"] == "ps.retail_banking_customer_360"


def test_update_product_spec_returns_updated_payload(client, auth_headers, isolated_product_spec_dependency) -> None:
    response = client.put(
        "/api/data-catalog/v1/product-specs/ps.retail_banking_customer_360",
        json={
            "glossary": {
                "name": "retail_banking_product_specs",
                "display_name": "Retail Banking Product Specs",
                "description": "Governed ODPS-aligned retail banking product specifications.",
            },
            "product_spec_id": "ps.retail_banking_customer_360",
            "product_name": "Retail Banking Customer 360",
            "product_version": "2.2.0",
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
            "provenance": {"created_by": "platform", "approved_by": "customer-domain-owner"},
        },
        headers=auth_headers("dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["product_spec_id"] == "ps.retail_banking_customer_360"


def test_update_product_spec_maps_conflict_error(client, auth_headers, isolated_product_spec_dependency) -> None:
    isolated_product_spec_dependency._update_error = ProductSpecLookupError(
        "Product spec update path and payload must use the same stable product_spec_id",
        status_code=409,
    )

    response = client.put(
        "/api/data-catalog/v1/product-specs/ps.retail_banking_customer_360",
        json={
            "glossary": {
                "name": "retail_banking_product_specs",
                "display_name": "Retail Banking Product Specs",
                "description": "Governed ODPS-aligned retail banking product specifications.",
            },
            "product_spec_id": "ps.wealth_customer_360",
            "product_name": "Retail Banking Customer 360",
            "product_version": "2.2.0",
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
            "provenance": {"created_by": "platform", "approved_by": "customer-domain-owner"},
        },
        headers=auth_headers("dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["detail"]["error"] == "product_spec_conflict"


def test_import_product_specs_returns_report(client, auth_headers, isolated_product_spec_dependency) -> None:
    response = client.post(
        "/api/data-catalog/v1/product-specs/import",
        json={
            "glossary": {
                "name": "retail_banking_product_specs",
                "display_name": "Retail Banking Product Specs",
                "description": "Governed ODPS-aligned retail banking product specifications.",
            },
            "product_specs": [
                {
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
                    "provenance": {"created_by": "platform", "approved_by": "customer-domain-owner"},
                    "migration": {"legacy_product_ids": ["legacy.customer_360"]},
                }
            ],
        },
        headers=auth_headers("dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["outcome"] == "created"


def test_import_product_specs_maps_validation_error(client, auth_headers, isolated_product_spec_dependency) -> None:
    isolated_product_spec_dependency._import_error = ProductSpecLookupError(
        "product spec import requires at least one product_spec entry",
        status_code=422,
    )

    response = client.post(
        "/api/data-catalog/v1/product-specs/import?dry_run=true",
        json={
            "glossary": {
                "name": "retail_banking_product_specs",
                "display_name": "Retail Banking Product Specs",
                "description": "Governed ODPS-aligned retail banking product specifications.",
            },
            "product_specs": [],
        },
        headers=auth_headers("dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"]["error"] == "invalid_product_spec_request"


def test_apply_product_spec_stewardship_action_returns_updated_payload(client, auth_headers, isolated_product_spec_dependency) -> None:
    response = client.post(
        "/api/data-catalog/v1/product-specs/ps.retail_banking_customer_360/stewardship-actions",
        json={
            "glossary": {
                "name": "retail_banking_product_specs",
                "display_name": "Retail Banking Product Specs",
                "description": "Governed ODPS-aligned retail banking product specifications.",
            },
            "action": "approve",
            "actor": "customer-domain-owner",
            "change_reason": "Approved by governance board",
        },
        headers=auth_headers("dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["product_spec_id"] == "ps.retail_banking_customer_360"


def test_apply_product_spec_stewardship_action_maps_validation_error(client, auth_headers, isolated_product_spec_dependency) -> None:
    isolated_product_spec_dependency._stewardship_error = ProductSpecLookupError(
        "product spec stewardship action requires a supported action",
        status_code=422,
    )

    response = client.post(
        "/api/data-catalog/v1/product-specs/ps.retail_banking_customer_360/stewardship-actions",
        json={
            "glossary": {
                "name": "retail_banking_product_specs",
                "display_name": "Retail Banking Product Specs",
                "description": "Governed ODPS-aligned retail banking product specifications.",
            },
            "action": "approve",
            "actor": "customer-domain-owner",
            "change_reason": "Testing error mapping",
        },
        headers=auth_headers("dq:rules:edit", "dq:rules:write"),
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"]["error"] == "invalid_product_spec_request"
