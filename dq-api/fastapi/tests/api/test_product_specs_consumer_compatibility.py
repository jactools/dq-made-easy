from __future__ import annotations

import pytest

from app.core.dependencies import get_product_spec_resolver


class _StatefulResolver:
    def __init__(self) -> None:
        self._records = {
            "ps.retail_banking_customer_360": {
                "product_spec_id": "ps.retail_banking_customer_360",
                "product_name": "Retail Banking Customer 360",
                "product_version": "2.1.0",
                "product_lifecycle_state": "draft",
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
                        "openmetadata_entity_id": "om-contract-1",
                        "openmetadata_entity_type": "data_contract",
                        "source_system": "openmetadata",
                    }
                ],
                "openmetadata_entity_id": "om-product-spec-1",
                "openmetadata_entity_type": "glossary_term",
                "source_system": "openmetadata",
                "provenance": {"created_by": "platform", "approved_by": "customer-domain-owner"},
                "migration": {"legacy_product_ids": ["legacy.customer_360"]},
            },
            "ps.wealth_customer_360": {
                "product_spec_id": "ps.wealth_customer_360",
                "product_name": "Wealth Customer 360",
                "product_version": "1.4.0",
                "product_lifecycle_state": "active",
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
                        "openmetadata_entity_id": "om-contract-2",
                        "openmetadata_entity_type": "data_contract",
                        "source_system": "openmetadata",
                    }
                ],
                "openmetadata_entity_id": "om-product-spec-2",
                "openmetadata_entity_type": "glossary_term",
                "source_system": "openmetadata",
                "provenance": {"created_by": "platform", "approved_by": "wealth-domain-owner"},
                "migration": {},
            },
        }

    async def resolve_product_spec(self, product_spec_id: str) -> dict:
        return dict(self._records[product_spec_id])

    async def list_product_specs(
        self,
        *,
        owner: str | None = None,
        lifecycle_state: str | None = None,
        registry_definition_id: str | None = None,
        linked_contract_id: str | None = None,
        search: str | None = None,
    ) -> list[dict]:
        items = [dict(item) for item in self._records.values()]
        if owner is not None:
            items = [item for item in items if item.get("product_owner") == owner]
        if lifecycle_state is not None:
            items = [item for item in items if item.get("product_lifecycle_state") == lifecycle_state]
        if registry_definition_id is not None:
            items = [item for item in items if registry_definition_id in item.get("registry_definition_ids", [])]
        if linked_contract_id is not None:
            items = [
                item
                for item in items
                if linked_contract_id in [ref.get("odcs_contract_id") for ref in item.get("odcs_contract_refs", [])]
            ]
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
        record = dict(payload)
        self._records[record["product_spec_id"]] = record
        return dict(record)

    async def update_product_spec(self, product_spec_id: str, payload: dict) -> dict:
        record = dict(self._records[product_spec_id])
        record.update(payload)
        self._records[product_spec_id] = record
        return dict(record)

    async def import_product_specs(self, payload: dict, *, dry_run: bool = False) -> dict:
        return {
            "dry_run": dry_run,
            "total": 0,
            "created": 0,
            "updated": 0,
            "validated": 0,
            "items": [],
        }

    async def apply_stewardship_action(self, product_spec_id: str, payload: dict) -> dict:
        lifecycle_state_by_action = {
            "submit_for_approval": "in_review",
            "approve": "active",
            "request_changes": "draft",
            "deprecate": "deprecated",
            "retire": "retired",
        }
        record = dict(self._records[product_spec_id])
        record["product_lifecycle_state"] = lifecycle_state_by_action[payload["action"]]
        record["provenance"] = {
            **dict(record.get("provenance") or {}),
            "change_reason": payload["change_reason"],
            "approved_by": payload["actor"],
        }
        self._records[product_spec_id] = record
        return dict(record)

    async def summarize_product_specs(self) -> dict:
        items = list(self._records.values())
        by_lifecycle_state: dict[str, int] = {}
        by_owner: dict[str, int] = {}
        for item in items:
            state = str(item.get("product_lifecycle_state") or "unspecified")
            owner = str(item.get("product_owner") or "unassigned")
            by_lifecycle_state[state] = by_lifecycle_state.get(state, 0) + 1
            by_owner[owner] = by_owner.get(owner, 0) + 1
        return {
            "total": len(items),
            "by_lifecycle_state": by_lifecycle_state,
            "by_owner": by_owner,
        }


@pytest.fixture(autouse=True)
def isolated_product_spec_dependency(client):
    resolver = _StatefulResolver()
    client.app.dependency_overrides[get_product_spec_resolver] = lambda: resolver
    yield resolver
    client.app.dependency_overrides.pop(get_product_spec_resolver, None)


def test_product_spec_consumer_list_summary_shapes_are_stable(client, auth_headers, isolated_product_spec_dependency) -> None:
    list_response = client.get(
        "/api/data-catalog/v1/product-specs",
        params={"page": 1, "limit": 20, "search": "customer 360"},
        headers=auth_headers("dq:rules:read"),
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["pagination"]["total"] == 2
    assert "data" in list_payload
    assert {"product_spec_id", "product_lifecycle_state", "product_owner"}.issubset(list_payload["data"][0].keys())

    summary_response = client.get(
        "/api/data-catalog/v1/product-specs/summary",
        headers=auth_headers("dq:rules:read"),
    )
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["total"] == 2
    assert summary_payload["by_lifecycle_state"]["draft"] == 1
    assert summary_payload["by_owner"]["wealth-domain-owner"] == 1


def test_product_spec_consumer_stewardship_roundtrip_updates_read_model(client, auth_headers, isolated_product_spec_dependency) -> None:
    before = client.get(
        "/api/data-catalog/v1/product-specs/ps.retail_banking_customer_360",
        headers=auth_headers("dq:rules:read"),
    )
    assert before.status_code == 200
    assert before.json()["product_lifecycle_state"] == "draft"

    action_response = client.post(
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
    assert action_response.status_code == 200

    after = client.get(
        "/api/data-catalog/v1/product-specs/ps.retail_banking_customer_360",
        headers=auth_headers("dq:rules:read"),
    )
    assert after.status_code == 200
    assert after.json()["product_lifecycle_state"] == "active"
    assert after.json()["provenance"]["change_reason"] == "Approved by governance board"
