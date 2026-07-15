import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

import pytest
import yaml

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

import pytest
import yaml

from app.api.v1.endpoints import data_catalog as data_catalog_endpoints
from app.application.services.data_definition_task_service import ANALYSIS_TYPE_DEFINITION_TASK
from app.core.config import get_settings
from app.core.dependencies import get_data_asset_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_gx_execution_run_repository
from app.core.dependencies import get_suggestions_repository
from app.domain.entities import NaturalLanguageDraftRequestEntity
from app.domain.entities import NaturalLanguageDraftRequestHistoryEntity
from app.domain.entities.data_catalog import DataDeliveryNoteEntity
from app.domain.entities.gx_execution_run import GxExecutionRunListQueryEntity
from app.domain.entities.gx_execution_run import build_gx_execution_run_create_entity
from app.infrastructure.repositories.in_memory_data_asset_repository import InMemoryDataAssetRepository
from app.infrastructure.repositories.in_memory_data_catalog_repository import InMemoryDataCatalogRepository
from app.infrastructure.repositories.in_memory_gx_execution_run_repository import InMemoryGxExecutionRunRepository
from app.main import app

client = TestClient(app)


class _FakeDefinitionTaskSuggestionsRepository:
    def __init__(self) -> None:
        self.natural_language_requests: list[NaturalLanguageDraftRequestEntity] = []
        self.natural_language_request_history: list[NaturalLanguageDraftRequestHistoryEntity] = []
        self.update_calls: list[dict] = []

    def record_natural_language_request(
        self,
        *,
        request: NaturalLanguageDraftRequestEntity,
    ) -> NaturalLanguageDraftRequestEntity:
        self.natural_language_requests.insert(0, request)
        self.record_natural_language_request_history_event(
            request_id=request.request_id,
            action="created",
            to_status=request.status,
            actor_id=request.requested_by_user_id,
            details={"analysis_type": request.analysis_type, "current_workspace_id": request.current_workspace_id},
        )
        return request

    def update_natural_language_request(self, **kwargs):
        self.update_calls.append(dict(kwargs))
        request = next((row for row in self.natural_language_requests if row.request_id == kwargs["request_id"]), None)
        if request is None:
            request = NaturalLanguageDraftRequestEntity(
                request_id=kwargs["request_id"],
                job_id=kwargs.get("job_id") or "job-1",
                current_workspace_id="retail-banking",
                search_scope="current",
                analysis_provider="llm",
                analysis_type=ANALYSIS_TYPE_DEFINITION_TASK,
                prompt="Define customer segments",
                requested_by_user_id="user-123",
            )
            self.natural_language_requests.insert(0, request)

        previous_status = request.status
        request.status = kwargs["status"]
        if kwargs.get("job_id") is not None:
            request.job_id = kwargs["job_id"]
        if kwargs.get("started_at") is not None:
            request.started_at = kwargs["started_at"]
        if kwargs.get("completed_at") is not None:
            request.completed_at = kwargs["completed_at"]
        request.error_message = kwargs.get("error_message")
        request.suggestion_id = kwargs.get("suggestion_id")
        if kwargs.get("result") is not None:
            request.result = dict(kwargs["result"])
        self.record_natural_language_request_history_event(
            request_id=request.request_id,
            action="status_changed",
            from_status=previous_status,
            to_status=request.status,
            actor_id=request.requested_by_user_id,
            details={"result": dict(request.result) if request.result is not None else None},
        )
        return request

    def record_natural_language_request_history_event(
        self,
        *,
        request_id: str,
        action: str,
        from_status: str | None = None,
        to_status: str | None = None,
        actor_id: str | None = None,
        details: dict | None = None,
    ) -> NaturalLanguageDraftRequestHistoryEntity:
        entity = NaturalLanguageDraftRequestHistoryEntity(
            id=f"history-{len(self.natural_language_request_history) + 1}",
            request_id=request_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            changed_at=f"2026-04-27T00:00:0{len(self.natural_language_request_history)}+00:00",
            details=dict(details or {}),
        )
        self.natural_language_request_history.insert(0, entity)
        return entity

    def list_natural_language_request_history(self, *, request_id: str, limit: int, offset: int):
        if not any(row.request_id == request_id for row in self.natural_language_requests):
            return None
        rows = [row for row in self.natural_language_request_history if row.request_id == request_id]
        return list(rows[offset : offset + limit])


class _FakeOpenMetadataDefinitionImporter:
    def __init__(self) -> None:
        self.imported_contracts: list[dict] = []

    def import_contract(self, import_contract: dict) -> dict:
        self.imported_contracts.append(import_contract)
        return {
            "glossary": {
                "name": "finance_terms",
                "display_name": "Finance Terms",
                "fully_qualified_name": "finance_terms",
            },
            "definition_count": len(import_contract.get("glossary_terms") or []),
            "definitions": [
                {
                    "name": "def_attribute_retail_loans_facility_facility_id",
                    "term_fqn": "finance_terms.def_attribute_retail_loans_facility_facility_id",
                    "openmetadata_entity_id": "om-term-1",
                }
            ],
        }


def _definition_task_result() -> dict:
    definition = {
        "concept_key": "def.attribute.retail_loans.facility.facility_id",
        "definition_id": "def.attribute.retail_loans.facility.facility_id",
        "target_id": "attr-1",
        "definition_name": "Facility Identifier",
        "business_definition": "An identifier that uniquely distinguishes a lending facility within the finance domain",
        "primary_domain": "Finance",
        "definition_owner": "Jane Steward",
        "source_references": [
            {
                "source_system": "Facility",
                "data_set_name": "Retail Loans",
                "data_object_name": "Facility",
                "attribute_name": "facility_id",
                "logical_path": "Finance/Retail Loans/Facility/v3/facility_id",
            }
        ],
        "policy_documents": [
            {
                "name": "Guidelines for Definitions of Business Terms",
                "version": "1.0",
                "source": "Data Definition Board",
            }
        ],
        "homonym_context": {
            "primary_domain": "Finance",
            "object_class": "Facility",
            "property": "facility_id",
            "logical_path": "Finance/Retail Loans/Facility/v3/facility_id",
        },
        "status": "draft",
        "board_review_status": "pending_board_review",
        "provenance": {},
    }
    return {
        "review_status": "pending_board_review",
        "board_review_packet": {"review_status": "pending_board_review", "decision_required": True},
        "registry_contract": {"definitions": [dict(definition)]},
        "openmetadata_import_contract": {
            "glossary": {
                "name": "finance_terms",
                "display_name": "Finance Terms",
                "description": "Approved finance data definitions.",
            },
            "definitions_manifest": {"definitions": [dict(definition)]},
            "glossary_terms": [
                {
                    "name": "def_attribute_retail_loans_facility_facility_id",
                    "displayName": "Facility Identifier",
                    "description": "An identifier that uniquely distinguishes a lending facility within the finance domain",
                    "extension": {
                        "concept_key": "def.attribute.retail_loans.facility.facility_id",
                        "definition_id": "def.attribute.retail_loans.facility.facility_id",
                        "target_id": "attr-1",
                        "primary_domain": "Finance",
                        "definition_owner": "Jane Steward",
                        "source_references": definition["source_references"],
                        "policy_documents": definition["policy_documents"],
                        "homonym_context": definition["homonym_context"],
                        "status": "draft",
                        "board_review_status": "pending_board_review",
                        "provenance": "{}",
                    },
                }
            ],
        },
    }


def _jwt(payload: dict[str, object]) -> str:
    import base64
    import json

    header = {"alg": "none", "typ": "JWT"}

    def encode(value: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode("utf-8").rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


def _auth_headers(*scopes: str) -> dict[str, str]:
    token = _jwt(
        {
            "sub": "user-123",
            "preferred_username": "admin",
            "iss": "http://keycloak.local:8080/realms/jaccloud",
            "aud": ["dq-rules-ui"],
            "scope": " ".join(scopes),
        }
    )
    return {"Authorization": f"Bearer {token}"}


def setup_module() -> None:
    get_settings.cache_clear()


def teardown_module() -> None:
    get_settings.cache_clear()


@pytest.fixture
def data_asset_repository() -> InMemoryDataAssetRepository:
    repository = InMemoryDataAssetRepository()
    repository.create_data_asset(
        {
            "id": "asset-1",
            "name": "Customer health",
            "workspace_id": "retail-banking",
            "current_version_id": "asset-1-v1",
        }
    )
    repository.create_data_asset_version(
        "asset-1",
        {
            "id": "asset-1-v1",
            "version": 1,
            "source_bindings": [
                {
                    "source_data_object_version_id": "dov-1",
                    "source_field_id": "field-1",
                    "source_field_name": "customer_id",
                    "source_field_type": "string",
                }
            ],
            "derived_fields": [
                {
                    "name": "customer_segment",
                    "expression": "case when amount > 100 then 'gold' end",
                    "data_type": "string",
                }
            ],
        },
    )
    return repository


@pytest.fixture(autouse=True)
def isolated_data_catalog_dependencies(
    data_asset_repository: InMemoryDataAssetRepository,
) -> tuple[InMemoryDataCatalogRepository, InMemoryGxExecutionRunRepository]:
    repository = InMemoryDataCatalogRepository()
    execution_repository = InMemoryGxExecutionRunRepository()
    app.dependency_overrides[get_data_catalog_repository] = lambda: repository
    app.dependency_overrides[get_data_asset_repository] = lambda: data_asset_repository
    app.dependency_overrides[get_gx_execution_run_repository] = lambda: execution_repository

    yield repository, execution_repository

    app.dependency_overrides.pop(get_data_catalog_repository, None)
    app.dependency_overrides.pop(get_data_asset_repository, None)
    app.dependency_overrides.pop(get_gx_execution_run_repository, None)


def test_data_products_requires_auth(monkeypatch) -> None:
    suggestions_repository = _FakeDefinitionTaskSuggestionsRepository()
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get("/api/data-catalog/v1/data-products")

    assert response.status_code == 401


def test_data_products_returns_paginated_rows(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/data-catalog/v1/data-products?workspace=retail-banking&page=1&limit=10",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "prod-1"
    assert payload["data"][0]["business_key"] == "customer-order-management"


def test_data_products_can_filter_by_business_key(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/data-catalog/v1/data-products?businessKey=analytics-reporting",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "prod-4"
    assert payload["data"][0]["business_key"] == "analytics-reporting"


def test_data_objects_returns_rows(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/data-catalog/v1/data-objects",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload[0]["id"] == "obj-15"
    assert payload[0]["business_key"] == "campaign"


def test_data_objects_can_filter_by_business_key(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/data-catalog/v1/data-objects?businessKey=contact",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == "obj-2"
    assert payload[0]["business_key"] == "contact"


def test_data_sets_support_legacy_query_params(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/data-catalog/v1/data-sets?productId=prod-4&standalone=true",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "ds-5"
    assert payload["data"][0]["business_key"] == "data-warehouse"


def test_data_sets_can_filter_by_business_key(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/data-catalog/v1/data-sets?businessKey=crm-system",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "ds-1"
    assert payload["data"][0]["business_key"] == "crm-system"


def test_data_sets_expose_contract_download_url(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/data-catalog/v1/data-sets?businessKey=crm-system",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["data_contract_download_url"] == "/data-catalog/v1/data-sets/ds-1/contract"
    assert payload["data"][0]["tags"] == ["pii", "customer"]


def test_data_definition_task_history_returns_audit_events(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    suggestions_repository = _FakeDefinitionTaskSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: suggestions_repository
    request = NaturalLanguageDraftRequestEntity(
        request_id="request-1",
        job_id="job-1",
        current_workspace_id="retail-banking",
        search_scope="current",
        analysis_provider="llm",
        analysis_type=ANALYSIS_TYPE_DEFINITION_TASK,
        prompt="Define customer segments",
        requested_by_user_id="user-123",
        status="pending",
    )
    suggestions_repository.record_natural_language_request(request=request)
    suggestions_repository.update_natural_language_request(
        request_id="request-1",
        status="started",
        job_id="job-1",
        started_at="2026-04-27T00:00:01+00:00",
    )
    suggestions_repository.update_natural_language_request(
        request_id="request-1",
        status="completed",
        job_id="job-1",
        completed_at="2026-04-27T00:00:02+00:00",
        result={"status": "ok"},
    )

    response = client.get(
        "/api/data-catalog/v1/data-definition-tasks/requests/request-1/history",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "request-1"
    assert payload["count"] == 3
    assert payload["events"][0]["action"] == "status_changed"
    assert payload["events"][0]["to_status"] == "completed"
    assert payload["events"][-1]["action"] == "created"
def test_data_set_contract_roundtrip_updates_catalog_fields(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    export_response = client.get(
        "/api/data-catalog/v1/data-sets/ds-1/contract?format=json",
        headers=_auth_headers("dq:rules:read"),
    )

    assert export_response.status_code == 200
    contract = export_response.json()
    assert contract["kind"] == "DataContract"
    assert contract["id"] == "urn:dq:dataset:ds-1"
    assert contract["tags"] == ["pii", "customer"]

    import_contract = {
        "apiVersion": contract["apiVersion"],
        "kind": contract["kind"],
        "id": contract["id"],
        "name": "CRM System Updated",
        "status": "active",
        "owner": {"name": "carla.steward@example.com"},
        "contact": {"name": "Carla Steward", "email": "carla.steward@example.com"},
        "domain": "retail-banking",
        "description": {"purpose": "Updated CRM system dataset"},
        "tags": ["customer", "sensitive"],
        "extension": {
            "dq": {
                "product_id": "prod-4",
                "workspace_id": "retail-banking",
                "business_key": "crm-system-updated",
            }
        },
    }

    import_response = client.post(
        "/api/data-catalog/v1/data-sets/ds-1/contract/import",
        headers=_auth_headers("dq:rules:write"),
        json={"contract_text": yaml.safe_dump(import_contract, sort_keys=False)},
    )

    assert import_response.status_code == 200
    imported = import_response.json()
    assert imported["name"] == "CRM System Updated"
    assert imported["owner"] == "carla.steward@example.com"
    assert imported["description"] == "Updated CRM system dataset"
    assert imported["product_id"] == "prod-4"
    assert imported["workspace_id"] == "retail-banking"
    assert imported["business_key"] == "crm-system-updated"
    assert imported["tags"] == ["customer", "sensitive"]
    assert imported["data_contract_download_url"] == "/data-catalog/v1/data-sets/ds-1/contract"


def test_data_objects_catalog_filters_by_data_set(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/data-catalog/v1/data-objects-catalog?dataSetId=ds-1",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] >= 1
    assert any(row["id"] == "do-2" for row in payload["data"])


def test_data_objects_catalog_can_filter_by_business_key(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/data-catalog/v1/data-objects-catalog?businessKey=customer",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "do-1"
    assert payload["data"][0]["business_key"] == "customer"


def test_data_object_versions_sort_descending(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/data-catalog/v1/data-object-versions?objectId=do-1",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 2
    assert [row["version"] for row in payload["data"]] == [3, 2]


def test_attributes_catalog_filters_by_version(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/data-catalog/v1/attributes-catalog?versionId=dov-3",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 2
    assert [row["id"] for row in payload["data"]] == ["attr-10", "attr-11"]
    assert payload["data"][1]["is_business_key"] is False
    assert payload["data"][0]["is_business_key"] is True


def test_attributes_catalog_includes_data_asset_fields(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/data-catalog/v1/attributes-catalog",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    data_asset_rows = [row for row in payload["data"] if row["id"].startswith("data-asset::asset-1::asset-1-v1")]
    assert len(data_asset_rows) == 2
    assert {row["source_kind"] for row in data_asset_rows} == {"data_asset"}
    assert {row["workspace_id"] for row in data_asset_rows} == {"retail-banking"}
    assert any(row["name"] == "customer_id" for row in data_asset_rows)
    assert any(row["name"] == "customer_segment" for row in data_asset_rows)


def test_attributes_catalog_can_filter_business_key_attributes(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/data-catalog/v1/attributes-catalog?versionId=dov-3&businessKeyOnly=true",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "attr-10"
    assert payload["data"][0]["is_business_key"] is True


def test_data_deliveries_filters_by_version(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/data-catalog/v1/data-deliveries?versionId=2",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 2
    assert payload["data"][0]["id"] == "del-30"


def test_data_deliveries_can_filter_by_business_key(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/data-catalog/v1/data-deliveries?businessKey=analytics/Customer/v3/LOAD_DTS=20260221T083000000Z",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "del-28"
    assert payload["data"][0]["layer"] == "standardized"
    assert payload["data"][0]["delivery_location"] == "analytics/Customer/v3/LOAD_DTS=20260221T083000000Z"


def test_data_deliveries_filters_by_data_object_version_id(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/data-catalog/v1/data-deliveries?dataObjectVersionId=dov-3",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "del-28"
    assert payload["data"][0]["data_object_version_id"] == "dov-3"


def test_data_delivery_note_returns_rich_detail(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/data-catalog/v1/data-deliveries/del-31/note",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_delivery_id"] == "del-31"
    assert payload["delivery_status"] == "completed"
    assert payload["ingestor_name"] == "data-ingestor"
    assert payload["layer"] == "standardized"
    assert payload["storage_location"] == "S3"
    assert payload["delivery_location"] == "analytics/Customer/v1/LOAD_DTS=20260221T153000000Z"
    assert payload["object_storage_classification"] == "real_evidence"
    assert payload["evidence_classification"] == "real_evidence"
    assert payload["metadata_json"]["workspace_id"] == "retail-banking"
    assert payload["file_count"] == 3
    assert payload["file_names"] is None
    assert payload["storage_exists"] is None
    assert payload["storage_object_count"] is None


def test_data_delivery_note_includes_execution_summary_and_references(monkeypatch, isolated_data_catalog_dependencies) -> None:
    _, execution_repository = isolated_data_catalog_dependencies
    captured_query: dict[str, object] = {}

    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    original_list_runs = execution_repository.list_runs

    async def _capture_list_runs(query=None, **kwargs):
        captured_query["query"] = query
        return await original_list_runs(query=query, **kwargs)

    monkeypatch.setattr(execution_repository, "list_runs", _capture_list_runs)

    async def _seed_runs() -> None:
        await execution_repository.create_run(
            build_gx_execution_run_create_entity(
                {
                    "run_id": "gx-run-del-31",
                    "suite_id": "suite-customer-quality",
                    "suite_version": 2,
                    "rule_id": "rule-customer-completeness",
                    "rule_version_id": "rule-version-17",
                    "correlation_id": "corr-del-31",
                    "requested_by": "quality-bot",
                    "engine_target": "spark",
                    "engine_type": "spark",
                    "execution_shape": "single_suite",
                    "status": "succeeded",
                    "submitted_at": "2026-02-21T15:40:00Z",
                    "started_at": "2026-02-21T15:40:05Z",
                    "completed_at": "2026-02-21T15:42:30Z",
                    "execution_contract": {
                        "engine_type": "spark",
                        "resolvedDataDeliveryId": "del-31",
                        "resolvedDeliveryLocation": "analytics/Customer/v1/LOAD_DTS=20260221T153000000Z",
                    },
                    "handoff_payload": {
                        "engine_type": "spark",
                        "deliverySnapshot": {
                            "resolvedDataDeliveryId": "del-31",
                        }
                    },
                    "result_summary": {"passed": 12, "failed": 0},
                    "diagnostics": [],
                }
            )
        )
        await execution_repository.create_run(
            build_gx_execution_run_create_entity(
                {
                    "run_id": "gx-run-unrelated",
                    "suite_id": "suite-other",
                    "suite_version": 1,
                    "rule_id": "rule-other",
                    "rule_version_id": "rule-version-99",
                    "correlation_id": "corr-other",
                    "requested_by": "quality-bot",
                    "engine_target": "spark",
                    "engine_type": "spark",
                    "execution_shape": "single_suite",
                    "status": "failed",
                    "submitted_at": "2026-02-21T15:41:00Z",
                    "execution_contract": {
                        "engine_type": "spark",
                        "resolvedDataDeliveryId": "del-99",
                        "resolvedDeliveryLocation": "analytics/Other/v1/LOAD_DTS=20260221T153000000Z",
                    },
                    "result_summary": {"passed": 0, "failed": 3},
                    "diagnostics": [],
                    "failure_code": "RULE_FAILURE",
                    "failure_message": "Unrelated delivery should not appear in the note",
                }
            )
        )

    asyncio.run(_seed_runs())

    response = client.get(
        "/data-catalog/v1/data-deliveries/del-31/note",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_summary"]["total_execution_runs"] == 1
    assert payload["execution_summary"]["status_counts"] == {"succeeded": 1}
    assert payload["execution_summary"]["latest_execution_run_id"] == "gx-run-del-31"
    assert payload["execution_summary"]["latest_execution_status"] == "succeeded"
    assert len(payload["execution_references"]) == 1
    assert payload["execution_references"][0]["execution_run_id"] == "gx-run-del-31"
    assert payload["execution_references"][0]["execution_status"] == "succeeded"
    assert payload["execution_references"][0]["suite_id"] == "suite-customer-quality"
    assert isinstance(captured_query["query"], dict)
    assert not isinstance(captured_query["query"], GxExecutionRunListQueryEntity)
    assert captured_query["query"] == {}


def test_data_delivery_note_exposes_delivery_format_warning(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    original_get_data_delivery_note = InMemoryDataCatalogRepository.get_data_delivery_note

    def _get_data_delivery_note(self, delivery_id: str):
        if delivery_id == "del-31":
            return DataDeliveryNoteEntity(
                id="note-del-31",
                data_delivery_id="del-31",
                data_object_id="Customer",
                data_object_version_id="dov-3",
                version=1,
                delivered_at="2026-02-21T15:30:00Z",
                timestamp="2026-02-21T15:30:00Z",
                layer="standardized",
                storage_location="S3",
                delivery_location="analytics/Customer/v1/LOAD_DTS=20260221T153000000Z",
                delivery_status="completed",
                delivery_format="hudi",
                delivery_format_warning="Unsupported file format: hudi. The delivery note states a format this runtime cannot seed.",
                record_count=146200,
                size_bytes=46100000,
                attributes_count=10,
                file_count=3,
                file_names=None,
                ingestor_name="data-ingestor",
                ingestor_run_id="ing-20260221-1530",
                source_system="crm",
                source_snapshot_id="snap-20260221-1530",
                checksum="b2f3d8c2e1f4",
                checksum_algorithm="sha256",
                metadata_json={"workspace_id": "retail-banking"},
            )
        return original_get_data_delivery_note(self, delivery_id)

    monkeypatch.setattr(InMemoryDataCatalogRepository, "get_data_delivery_note", _get_data_delivery_note)

    response = client.get(
        "/data-catalog/v1/data-deliveries/del-31/note",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["delivery_format"] == "hudi"
    assert payload["delivery_format_warning"] == "Unsupported file format: hudi. The delivery note states a format this runtime cannot seed."


def test_data_delivery_note_backfills_missing_storage_details(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    class _Inspector:
        def inspect(self, delivery_location: str) -> dict[str, object]:
            assert delivery_location == "s3a://retail-banking/standardized/analytics/Customer/v1/LOAD_DTS=20260221T153000000Z"
            return {
                "storage_exists": True,
                "storage_object_count": 3,
                "file_names": ["part-0000.parquet", "part-0001.parquet", "_SUCCESS"],
            }

    original_get_data_delivery_note = InMemoryDataCatalogRepository.get_data_delivery_note

    def _get_data_delivery_note(self, delivery_id: str):
        if delivery_id == "del-31":
            return DataDeliveryNoteEntity(
                id="note-del-31",
                data_delivery_id="del-31",
                data_object_id="Customer",
                data_object_version_id="dov-3",
                version=1,
                delivered_at="2026-02-21T15:30:00Z",
                timestamp="2026-02-21T15:30:00Z",
                layer="standardized",
                storage_location="S3",
                delivery_location="analytics/Customer/v1/LOAD_DTS=20260221T153000000Z",
                delivery_status="completed",
                delivery_format="parquet",
                record_count=146200,
                size_bytes=46100000,
                attributes_count=10,
                file_count=None,
                file_names=None,
                ingestor_name="data-ingestor",
                ingestor_run_id="ing-20260221-1530",
                source_system="crm",
                source_snapshot_id="snap-20260221-1530",
                checksum="b2f3d8c2e1f4",
                checksum_algorithm="sha256",
                metadata_json={"workspace_id": "retail-banking"},
            )
        return original_get_data_delivery_note(self, delivery_id)

    monkeypatch.setattr(InMemoryDataCatalogRepository, "get_data_delivery_note", _get_data_delivery_note)
    monkeypatch.setattr(data_catalog_endpoints, "DeliveryInventoryInspector", lambda: _Inspector())

    response = client.get(
        "/data-catalog/v1/data-deliveries/del-31/note?include_storage_details=true",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file_count"] == 3
    assert payload["file_names"] == ["part-0000.parquet", "part-0001.parquet", "_SUCCESS"]
    assert payload["storage_exists"] is True
    assert payload["storage_object_count"] == 3
    assert payload["record_count"] == 146200
    assert payload["size_bytes"] == 46100000
    assert payload["checksum"] == "b2f3d8c2e1f4"


def test_data_delivery_note_does_not_hit_storage_by_default(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    inspector_calls: list[str] = []

    class _Inspector:
        def inspect(self, delivery_location: str) -> dict[str, object]:
            inspector_calls.append(delivery_location)
            return {
                "storage_exists": True,
                "storage_object_count": 3,
                "file_names": ["part-0000.parquet", "part-0001.parquet", "_SUCCESS"],
            }

    monkeypatch.setattr(data_catalog_endpoints, "DeliveryInventoryInspector", lambda: _Inspector())

    response = client.get(
        "/data-catalog/v1/data-deliveries/del-31/note",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    assert inspector_calls == []


def test_delivery_inventory_filters_by_workspace_and_reports_storage(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    inspected_locations: list[str] = []

    class _Inspector:
        def inspect(self, delivery_location: str) -> dict[str, object]:
            inspected_locations.append(delivery_location)
            return {
                "storage_exists": True,
                "storage_object_count": 3 if delivery_location.endswith("LOAD_DTS=20260221T153000000Z") else 1,
            }

    monkeypatch.setattr(data_catalog_endpoints, "DeliveryInventoryInspector", lambda: _Inspector())

    response = client.get(
        "/data-catalog/v1/delivery-inventory?workspace=retail-banking&dataObjectVersionId=dov-1",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "del-31"
    assert payload["data"][0]["version"] == 1
    assert payload["data"][0]["delivery_location"] == "analytics/Customer/v1/LOAD_DTS=20260221T153000000Z"
    assert payload["data"][0]["layer"] == "standardized"
    assert payload["data"][0]["storage_exists"] is True
    assert payload["data"][0]["storage_object_count"] == 3
    assert inspected_locations == ["s3a://retail-banking/standardized/analytics/Customer/v1/LOAD_DTS=20260221T153000000Z"]


def test_delivery_inventory_filters_by_classification(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    original_get_data_delivery_note = InMemoryDataCatalogRepository.get_data_delivery_note

    def _get_data_delivery_note(self, delivery_id: str):
        note = original_get_data_delivery_note(self, delivery_id)
        if note is not None:
            note.object_storage_classification = "synthetic_test"
            note.evidence_classification = "synthetic_result"
        return note

    monkeypatch.setattr(InMemoryDataCatalogRepository, "get_data_delivery_note", _get_data_delivery_note)

    class _Inspector:
        def inspect(self, delivery_location: str) -> dict[str, object]:
            return {"storage_exists": True, "storage_object_count": 1}

    monkeypatch.setattr(data_catalog_endpoints, "DeliveryInventoryInspector", lambda: _Inspector())

    # Filter by matching classification
    response = client.get(
        "/data-catalog/v1/delivery-inventory?workspace=retail-banking&dataObjectVersionId=dov-1&objectStorageClassification=synthetic_test&evidenceClassification=synthetic_result",
        headers=_auth_headers("dq:rules:read"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["id"] == "del-31"

    # Filter by non-matching classification
    response = client.get(
        "/data-catalog/v1/delivery-inventory?workspace=retail-banking&dataObjectVersionId=dov-1&objectStorageClassification=real_evidence",
        headers=_auth_headers("dq:rules:read"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["total"] == 0
    assert payload["data"] == []


def test_rule_attributes_returns_read_only_mapping(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/data-catalog/v1/rule-attributes",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0] == {"rule_id": "1", "attribute_id": "attr-23", "threshold_override": None}


def test_post_rule_attributes_returns_added_count(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/data-catalog/v1/rule-attributes",
        headers=_auth_headers("dq:rules:write"),
        json={"entries": [{"ruleId": "1", "attributeId": "attr-999-data-catalog"}]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["added"] == 1


def test_post_rule_attributes_requires_write_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/data-catalog/v1/rule-attributes",
        headers=_auth_headers("dq:rules:read"),
        json={"entries": [{"rule_id": "1", "attributeId": "attr-1000"}]},
    )

    assert response.status_code == 403


def test_attribute_rule_counts_returns_map(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/data-catalog/v1/attribute-rule-counts",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["attr-23"] == 1


def test_create_data_definition_task_accepts_async_queue_and_uses_snake_case_nested_payload(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    async def fake_enqueue_natural_language_draft_job(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(enqueued=True, request_id="dd-request-1")

    monkeypatch.setattr(
        data_catalog_endpoints,
        "enqueue_natural_language_draft_job",
        fake_enqueue_natural_language_draft_job,
    )
    app.dependency_overrides[get_suggestions_repository] = lambda: _FakeDefinitionTaskSuggestionsRepository()

    try:
        response = client.post(
            "/api/data-catalog/v1/data-definition-tasks",
            headers=_auth_headers("dq:rules:write"),
            json={
                "current_workspace_id": "retail-banking",
                "version_id": "version-1",
                "selected_attribute_ids": ["attr-1"],
                "user_input": "Generate a governed definition",
                "context_documents": [
                    {
                        "document_type": "policy",
                        "name": "Guidelines for Definitions of Business Terms",
                        "content": "Use canonical English definitions.",
                        "source_uri": "urn:policy:business-term-definition-guidelines:v1",
                    }
                ],
                "feedback_items": [
                    {
                        "feedback_id": "fb-1",
                        "source_role": "steward",
                        "comment": "Prefer concise business language.",
                        "target_ids": ["attr-1"],
                    }
                ],
                "board_approval": {
                    "board_name": "Data Definition Board",
                    "status": "pending",
                    "approval_notes": "Needs review",
                },
            },
        )
    finally:
        app.dependency_overrides.pop(get_suggestions_repository, None)

    assert response.status_code == 202
    assert response.json()["queued"] is True
    assert response.json()["request_id"] == "dd-request-1"
    assert response.json()["events_url"] == "/data-catalog/v1/data-definition-tasks/requests/dd-request-1/events"
    assert "accepted" in response.json()["message"].lower()
    task_payload = captured["request_body"].taskPayload
    assert task_payload["context_documents"][0]["document_type"] == "policy"
    assert task_payload["context_documents"][0]["source_uri"] == "urn:policy:business-term-definition-guidelines:v1"
    assert "documentType" not in task_payload["context_documents"][0]
    assert "sourceUri" not in task_payload["context_documents"][0]
    assert task_payload["feedback_items"][0]["feedback_id"] == "fb-1"
    assert task_payload["feedback_items"][0]["source_role"] == "steward"
    assert task_payload["board_approval"]["board_name"] == "Data Definition Board"
    assert task_payload["board_approval"]["approval_notes"] == "Needs review"


def test_data_definition_task_events_streams_terminal_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    record = {
        "request_id": "dd-task-1",
        "job_id": "job-1",
        "current_workspace_id": "retail-banking",
        "version_id": "version-1",
        "selected_attribute_ids": ["attr-1"],
        "prompt": "Generate data definitions",
        "requested_by_user_id": "user-123",
        "requested_at": "2026-05-26T12:00:00+00:00",
        "completed_at": "2026-05-26T12:01:00+00:00",
        "status": "completed",
        "analysis_type": "definition_task",
        "analysis_provider": "llm",
        "auto_import": False,
        "task_payload": {},
        "result": _definition_task_result(),
    }

    monkeypatch.setattr(data_catalog_endpoints, "load_request_record_from_settings", lambda settings, request_id: record)

    with client.stream(
        "GET",
        "/api/data-catalog/v1/data-definition-tasks/requests/dd-task-1/events",
        headers={**_auth_headers("dq:rules:read"), "X-Kong-Request-Id": "test-request-id"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: snapshot" in body
    assert '"request_id":"dd-task-1"' in body
    assert '"status":"completed"' in body
    assert '"registry_contract"' in body


def test_data_definition_approval_auto_imports_after_board_approval(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    record = {
        "request_id": "dd-task-1",
        "job_id": "job-1",
        "current_workspace_id": "retail-banking",
        "version_id": "version-1",
        "selected_attribute_ids": ["attr-1"],
        "prompt": "Generate data definitions",
        "requested_by_user_id": "user-123",
        "status": "completed",
        "analysis_type": "definition_task",
        "analysis_provider": "llm",
        "auto_import": False,
        "task_payload": {},
        "result": _definition_task_result(),
    }
    saved_records: list[dict] = []
    suggestions_repository = _FakeDefinitionTaskSuggestionsRepository()
    importer = _FakeOpenMetadataDefinitionImporter()

    monkeypatch.setattr(data_catalog_endpoints, "load_request_record_from_settings", lambda settings, request_id: record)
    monkeypatch.setattr(data_catalog_endpoints, "save_request_record_to_settings", lambda settings, saved_record: saved_records.append(dict(saved_record)))
    monkeypatch.setattr(data_catalog_endpoints, "_openmetadata_importer_from_settings", lambda: importer)
    app.dependency_overrides[get_suggestions_repository] = lambda: suggestions_repository
    try:
        response = client.post(
            "/api/data-catalog/v1/data-definition-tasks/requests/dd-task-1/approval",
            headers=_auth_headers("dq:rules:write"),
            json={
                "board_approval": {
                    "board_name": "Data Definition Board",
                    "status": "approved",
                    "approver_name": "Jane Steward",
                    "approval_notes": "Approved for OpenMetadata import",
                    "approved_at": "2026-05-26T16:00:00Z",
                }
            },
        )
    finally:
        app.dependency_overrides.pop(get_suggestions_repository, None)

    assert response.status_code == 200
    payload = response.json()
    result = payload["request"]["result"]
    assert payload["request"]["auto_import"] is True
    assert result["review_status"] == "approved"
    assert result["openmetadata_import_result"]["definition_count"] == 1
    assert saved_records[0]["auto_import"] is True
    assert suggestions_repository.update_calls[0]["result"]["openmetadata_import_result"]["definition_count"] == 1
    imported_term = importer.imported_contracts[0]["glossary_terms"][0]
    assert imported_term["extension"]["status"] == "approved"
    assert imported_term["extension"]["board_review_status"] == "approved"


def test_data_definition_pending_approval_does_not_import(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    record = {
        "request_id": "dd-task-2",
        "job_id": "job-2",
        "current_workspace_id": "retail-banking",
        "version_id": "version-1",
        "selected_attribute_ids": ["attr-1"],
        "prompt": "Generate data definitions",
        "requested_by_user_id": "user-123",
        "status": "completed",
        "analysis_type": "definition_task",
        "analysis_provider": "llm",
        "auto_import": False,
        "task_payload": {},
        "result": _definition_task_result(),
    }
    suggestions_repository = _FakeDefinitionTaskSuggestionsRepository()
    importer = _FakeOpenMetadataDefinitionImporter()

    monkeypatch.setattr(data_catalog_endpoints, "load_request_record_from_settings", lambda settings, request_id: record)
    monkeypatch.setattr(data_catalog_endpoints, "save_request_record_to_settings", lambda settings, saved_record: None)
    monkeypatch.setattr(data_catalog_endpoints, "_openmetadata_importer_from_settings", lambda: importer)
    app.dependency_overrides[get_suggestions_repository] = lambda: suggestions_repository
    try:
        response = client.post(
            "/api/data-catalog/v1/data-definition-tasks/requests/dd-task-2/approval",
            headers=_auth_headers("dq:rules:write"),
            json={
                "board_approval": {
                    "board_name": "Data Definition Board",
                    "status": "pending",
                    "approver_name": "Jane Steward",
                    "approval_notes": "Needs another review",
                }
            },
        )
    finally:
        app.dependency_overrides.pop(get_suggestions_repository, None)

    assert response.status_code == 200
    assert importer.imported_contracts == []
    assert suggestions_repository.update_calls[0]["result"]["review_status"] == "pending_board_review"


def test_data_definition_task_status_reports_running_with_worker_heartbeat(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    record = {
        "request_id": "dd-task-running-1",
        "job_id": "job-running-1",
        "current_workspace_id": "retail-banking",
        "version_id": "version-1",
        "selected_attribute_ids": ["attr-1"],
        "prompt": "Generate data definitions",
        "requested_by_user_id": "user-123",
        "requested_at": "2026-05-26T12:00:00+00:00",
        "started_at": "2026-05-26T12:01:00+00:00",
        "status": "started",
        "analysis_type": "definition_task",
        "analysis_provider": "llm",
        "auto_import": False,
        "task_payload": {},
        "result": None,
    }

    monkeypatch.setattr(data_catalog_endpoints, "load_request_record_from_settings", lambda settings, request_id: record)
    monkeypatch.setattr(data_catalog_endpoints, "load_request_worker_heartbeat_from_settings", lambda settings, request_id: {"status": "running"})

    response = client.get(
        "/api/data-catalog/v1/data-definition-tasks/requests/dd-task-running-1/status",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request"]["status"] == "started"
    assert payload["request"]["monitoring_state"] == "running"