import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import suggestions as suggestions_endpoints
import app.core.dependencies as dependencies_module
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_data_asset_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_incident_repository
from app.core.dependencies import get_profiling_repository
from app.core.dependencies import get_registry_definition_resolver
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_suggestions_repository
from app.domain.entities import AdminUserEntity
from app.domain.entities import AttributeCatalogEntity
from app.domain.entities import DataObjectCatalogEntity
from app.domain.entities import DataProductEntity
from app.domain.entities import DataSetEntity
from app.domain.entities import SuggestionActionResultEntity
from app.domain.entities import SuggestionDataSourceEntity
from app.domain.entities import NaturalLanguageDraftRequestEntity
from app.domain.entities import SuggestionMetricsClearResultEntity
from app.domain.entities import SuggestionProfilingRequestEntity
from app.domain.entities import SuggestionProfilingStartEntity
from app.domain.entities import SuggestionEntity
from app.domain.entities import RuleTagEntity
from app.domain.entities.admin import UserWorkspaceRoleEntity
from app.domain.interfaces.v1.suggestions_repository import SuggestionNotFoundError
from app.domain.interfaces.profiling_repository import ProfilingDataSourceNotFoundError
from app.domain.interfaces.profiling_repository import ProfilingEnqueueFailedError
from app.domain.interfaces.profiling_repository import ProfilingRateLimitError
from app.domain.interfaces.profiling_repository import ProfilingRequestNotFoundError
from app.infrastructure.repositories.postgres_profiling_repository import PostgresProfilingRepository
import app.infrastructure.repositories.postgres_profiling_repository as profiling_repo_module
from app.infrastructure.repositories.postgres_suggestions_repository import PostgresSuggestionsRepository
import app.infrastructure.repositories.postgres_suggestions_repository as suggestions_repo_module
from app.middleware.api_case_enforcement import _to_snake_payload
from app.main import app


def _suggestions_headers(auth_headers: callable, claims: dict[str, object], *scopes: str) -> dict[str, str]:
    return auth_headers(
        *scopes,
        sub=str(claims.get("sub") or "user-1"),
        preferred_username=str(claims.get("preferred_username") or "suggestions-user"),
        email=str(claims.get("email")) if claims.get("email") is not None else None,
    )


@pytest.fixture(autouse=True)
def _clear_suggestions_overrides() -> None:
    app.dependency_overrides.pop(get_suggestions_repository, None)
    app.dependency_overrides.pop(get_profiling_repository, None)
    app.dependency_overrides.pop(get_incident_repository, None)
    app.dependency_overrides.pop(get_registry_definition_resolver, None)
    app.dependency_overrides.pop(get_data_catalog_repository, None)
    app.dependency_overrides.pop(get_data_asset_repository, None)
    app.dependency_overrides.pop(get_rules_repository, None)
    app.dependency_overrides.pop(get_admin_repository, None)
    app.dependency_overrides.pop(get_approvals_repository, None)
    app.dependency_overrides[get_profiling_repository] = lambda: _FakePreviewProfilingRepository()
    app.dependency_overrides[get_incident_repository] = lambda: _FakePreviewIncidentRepository()
    app.dependency_overrides[get_registry_definition_resolver] = lambda: _FakeRegistryDefinitionResolver()
    yield
    app.dependency_overrides.pop(get_suggestions_repository, None)
    app.dependency_overrides.pop(get_profiling_repository, None)
    app.dependency_overrides.pop(get_incident_repository, None)
    app.dependency_overrides.pop(get_registry_definition_resolver, None)
    app.dependency_overrides.pop(get_data_catalog_repository, None)
    app.dependency_overrides.pop(get_data_asset_repository, None)
    app.dependency_overrides.pop(get_rules_repository, None)
    app.dependency_overrides.pop(get_admin_repository, None)
    app.dependency_overrides.pop(get_approvals_repository, None)


class _FakeSuggestionsRepository:
    def __init__(self) -> None:
        self.data_sources: list[SuggestionDataSourceEntity] = []
        self.suggestions: list[SuggestionEntity] = []
        self.profiling_requests: list[SuggestionProfilingRequestEntity] = []
        self.natural_language_requests: list[NaturalLanguageDraftRequestEntity] = []
        self.request_profiling_result = SuggestionProfilingStartEntity(
            profiling_request_id="req-default",
            message="Data profiling started. This may take a few minutes.",
            status="pending",
        )
        self.request_profiling_error: Exception | None = None
        self.update_result = SuggestionActionResultEntity(message="Suggestion accepted")
        self.update_error: Exception | None = None
        self.profiling_status_result = SuggestionProfilingRequestEntity(id="req-default")
        self.profiling_status_error: Exception | None = None
        self.clear_result = SuggestionMetricsClearResultEntity(
            message="Suggestions metrics cleared",
            deleted_count=0,
        )
        self.request_profiling_calls: list[dict] = []
        self.update_calls: list[dict] = []
        self.list_suggestions_calls: list[dict] = []
        self.list_profiling_requests_calls: list[dict] = []
        self.list_natural_language_requests_calls: list[dict] = []
        self.create_suggestion_calls: list[dict] = []
        self.preview_events: list[dict] = []

    def list_data_sources(self) -> list[SuggestionDataSourceEntity]:
        return list(self.data_sources)

    def get_data_source_name(self, data_source_id: str) -> str | None:
        for data_source in self.data_sources:
            if str(getattr(data_source, "data_source_id", "") or "").strip() == data_source_id:
                return str(getattr(data_source, "name", "") or "").strip() or None
        return None

    def create_suggestion(
        self,
        *,
        user_id: str,
        data_source_id: str,
        suggested_rule: dict,
        confidence_score: float | None,
        reason: str | None,
        rule_type: str | None,
        created_from_profiling_request_id: str | None = None,
    ) -> SuggestionEntity:
        self.create_suggestion_calls.append(
            {
                "user_id": user_id,
                "data_source_id": data_source_id,
                "suggested_rule": suggested_rule,
                "confidence_score": confidence_score,
                "reason": reason,
                "rule_type": rule_type,
                "created_from_profiling_request_id": created_from_profiling_request_id,
            }
        )
        entity = SuggestionEntity(
            id="nl-suggestion-1",
            user_id=user_id,
            data_source_id=data_source_id,
            suggested_rule=suggested_rule,
            confidence_score=confidence_score,
            reason=reason,
            rule_type=rule_type,
            created_from_profiling_request_id=created_from_profiling_request_id,
            status="pending",
            created_at="2026-04-27T00:00:00+00:00",
            expires_at=None,
        )
        self.suggestions.insert(0, entity)
        return entity

    def list_suggestions(
        self,
        *,
        user_id: str | None,
        data_source_id: str | None,
        status: str,
    ) -> list[SuggestionEntity]:
        self.list_suggestions_calls.append(
            {
                "user_id": user_id,
                "data_source_id": data_source_id,
                "status": status,
            }
        )
        return list(self.suggestions)

    def list_profiling_requests(
        self,
        *,
        user_id: str,
        data_source_id: str | None,
        limit: int,
    ) -> list[SuggestionProfilingRequestEntity]:
        self.list_profiling_requests_calls.append(
            {
                "user_id": user_id,
                "data_source_id": data_source_id,
                "limit": limit,
            }
        )
        return list(self.profiling_requests)

    def record_natural_language_request(
        self,
        *,
        request: NaturalLanguageDraftRequestEntity,
    ) -> NaturalLanguageDraftRequestEntity:
        self.natural_language_requests.insert(0, request)
        return request

    def update_natural_language_request(
        self,
        *,
        request_id: str,
        status: str,
        job_id: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        error_message: str | None = None,
        suggestion_id: str | None = None,
        result: dict | None = None,
    ) -> NaturalLanguageDraftRequestEntity:
        request = next((row for row in self.natural_language_requests if row.request_id == request_id), None)
        if request is None:
            request = NaturalLanguageDraftRequestEntity(
                request_id=request_id,
                job_id=job_id or "",
                current_workspace_id="",
                search_scope="current",
                analysis_provider="llm",
                analysis_type="preview",
                prompt="",
                requested_by_user_id=None,
            )
            self.natural_language_requests.insert(0, request)

        request.status = status
        if job_id is not None:
            request.job_id = job_id
        if started_at is not None:
            request.started_at = started_at
        if completed_at is not None:
            request.completed_at = completed_at
        request.error_message = error_message
        request.suggestion_id = suggestion_id
        if result is not None:
            request.result = dict(result)
        return request

    def list_natural_language_requests(
        self,
        *,
        user_id: str,
        workspace_id: str | None,
        limit: int,
    ) -> list[NaturalLanguageDraftRequestEntity]:
        self.list_natural_language_requests_calls.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "limit": limit,
            }
        )
        rows = [row for row in self.natural_language_requests if row.requested_by_user_id == user_id]
        if workspace_id:
            rows = [row for row in rows if row.current_workspace_id == workspace_id]
        return list(rows[: max(1, min(limit, 100))])

    def request_profiling(self, *, user_id: str, data_source_id: str) -> SuggestionProfilingStartEntity:
        self.request_profiling_calls.append({"user_id": user_id, "data_source_id": data_source_id})
        if self.request_profiling_error is not None:
            raise self.request_profiling_error
        return self.request_profiling_result

    def update_suggestion_status(
        self,
        *,
        user_id: str,
        suggestion_id: str,
        action: str,
        rule_id: str | None = None,
    ) -> SuggestionActionResultEntity:
        self.update_calls.append(
            {
                "user_id": user_id,
                "suggestion_id": suggestion_id,
                "action": action,
                "rule_id": rule_id,
            }
        )
        if self.update_error is not None:
            raise self.update_error
        return self.update_result

    def get_profiling_request_status(self, profiling_request_id: str) -> SuggestionProfilingRequestEntity:
        _ = profiling_request_id
        if self.profiling_status_error is not None:
            raise self.profiling_status_error
        return self.profiling_status_result

    def record_preview_event(
        self,
        *,
        user_id: str,
        workspace_id: str,
        action: str,
        result: str = "success",
        error_code: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.preview_events.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "action": action,
                "result": result,
                "error_code": error_code,
                "details": details,
            }
        )

    def clear_metrics(self) -> SuggestionMetricsClearResultEntity:
        return self.clear_result


_FakeProfilingRepository = _FakeSuggestionsRepository


class _FakePreviewProfilingRepository:
    def __init__(self) -> None:
        self.profiling_requests = [
            SimpleNamespace(status="completed"),
            SimpleNamespace(status="failed"),
        ]

    def get_data_source_name(self, data_source_id: str) -> str | None:
        _ = data_source_id
        return "Preview Source"

    def list_profiling_requests(self, *, user_id: str, data_source_id: str | None, limit: int):
        _ = user_id
        _ = data_source_id
        return list(self.profiling_requests[:limit])

    def request_profiling(self, *, user_id: str, data_source_id: str):
        _ = user_id
        _ = data_source_id
        raise AssertionError("not used")

    def get_profiling_request_status(self, profiling_request_id: str):
        _ = profiling_request_id
        raise AssertionError("not used")

    def find_active_profiling_request(self, data_source_id: str):
        _ = data_source_id
        return None

    def create_request(self, request):
        _ = request
        raise AssertionError("not used")

    def set_started(self, profiling_request_id: str, job_id: str) -> None:
        _ = profiling_request_id
        _ = job_id
        raise AssertionError("not used")

    def set_completed(self, profiling_request_id: str, success: bool, error_message: str | None = None) -> None:
        _ = profiling_request_id
        _ = success
        _ = error_message
        raise AssertionError("not used")


class _FakePreviewIncidentRepository:
    def list_incidents(
        self,
        *,
        workspace_id: str | None = None,
        incident_kind: str | None = None,
        status: str | None = None,
        run_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        _ = incident_kind
        _ = run_id
        _ = offset
        rows = [
            SimpleNamespace(incident_kind="schema_drift", status="open", workspace_id="retail-banking"),
            SimpleNamespace(incident_kind="volume_drop", status="closed", workspace_id="retail-banking"),
        ]
        if workspace_id:
            rows = [row for row in rows if row.workspace_id == workspace_id]
        if status:
            rows = [row for row in rows if row.status == status]
        return list(rows[:limit])

    def list_root_cause_suggestions(
        self,
        *,
        workspace_id: str | None = None,
        incident_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        _ = incident_id
        _ = status
        _ = offset
        rows = [SimpleNamespace(workspace_id="retail-banking"), SimpleNamespace(workspace_id="retail-banking")]
        if workspace_id:
            rows = [row for row in rows if row.workspace_id == workspace_id]
        return list(rows[:limit])

    def create_incident(self, entity):
        _ = entity
        raise AssertionError("not used")

    def get_incident(self, incident_id: str):
        _ = incident_id
        raise AssertionError("not used")

    def update_incident(self, entity):
        _ = entity
        raise AssertionError("not used")

    def create_root_cause_suggestion(self, entity):
        _ = entity
        raise AssertionError("not used")

    def get_root_cause_suggestion(self, suggestion_id: str):
        _ = suggestion_id
        raise AssertionError("not used")

    def update_root_cause_suggestion(self, entity):
        _ = entity
        raise AssertionError("not used")


class _FakeRegistryDefinitionResolver:
    async def resolve_definition(self, definition_id: str) -> dict[str, object]:
        return {
            "definition_id": definition_id,
            "definition_name": definition_id,
            "definition_type": "glossary_term",
        }

    async def list_definitions(
        self,
        *,
        query: str | None = None,
        definition_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        _ = definition_type
        _ = limit
        normalized_query = str(query or "").strip().lower()
        if "customer" in normalized_query or "pii" in normalized_query:
            return [
                {
                    "definition_id": "glossary-customer",
                    "definition_name": "Customer",
                    "definition_type": "glossary_term",
                }
            ]
        return []


class _FakeApprovalsRepository:
    def __init__(self) -> None:
        self.audit_events: list[dict[str, object]] = []

    def append_audit_event(
        self,
        *,
        approval_id: str,
        action: str,
        actor_id: str | None,
        details: dict,
    ) -> dict[str, object]:
        event = {
            "approval_id": approval_id,
            "action": action,
            "actor_id": actor_id,
            "details": dict(details),
        }
        self.audit_events.append(event)
        return event


class _FakeExecuteResult:
    def __init__(self, scalar_one_or_none=None, all_rows=None, rowcount=None) -> None:
        self._scalar_one_or_none = scalar_one_or_none
        self._all_rows = all_rows if all_rows is not None else []
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar_one_or_none

    def scalars(self):
        return self

    def all(self):
        return list(self._all_rows)


class _FakeSession:
    def __init__(self, execute_results: list[_FakeExecuteResult], get_map: dict[str, object] | None = None) -> None:
        self._execute_results = iter(execute_results)
        self._get_map = dict(get_map or {})
        self.added: list[object] = []
        self.commits = 0

    def execute(self, _statement):
        return next(self._execute_results)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.commits += 1

    def get(self, _model, key: str):
        return self._get_map.get(key)


class _SessionScopeStub:
    def __init__(self, sessions: list[_FakeSession]) -> None:
        self._sessions = iter(sessions)

    def __call__(self, _database_url: str):
        self._current = next(self._sessions)
        return self

    def __enter__(self) -> _FakeSession:
        return self._current

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type
        _ = exc
        _ = tb


class _FakeAdminRepository:
    def __init__(self, workspace_ids: list[str]) -> None:
        self.workspace_ids = list(workspace_ids)

    def get_current_user(self, user_id: str | None, claims: dict | None = None) -> AdminUserEntity | None:
        if not user_id:
            return None
        _ = claims
        return AdminUserEntity(
            id=user_id,
            name="Suggestions User",
            first_name="Suggestions",
            last_name="User",
            email="suggestions@example.com",
            workspaces=list(self.workspace_ids),
            workspace_roles=[
                UserWorkspaceRoleEntity(workspace_id=workspace_id, role="analyst")
                for workspace_id in self.workspace_ids
            ],
        )


class _FakeDataCatalogRepository:
    def list_data_products(self, workspace: str | None = None) -> list[DataProductEntity]:
        rows = [
            DataProductEntity(id="product-retail", name="Customer", workspace_id="retail-banking"),
            DataProductEntity(id="product-corporate", name="Registry", workspace_id="corporate-banking"),
        ]
        if workspace:
            return [row for row in rows if row.workspace_id == workspace]
        return rows

    def list_data_sets(self, product_id: str | None = None, workspace: str | None = None) -> list[DataSetEntity]:
        rows = [
            DataSetEntity(id="dataset-retail", product_id="product-retail", name="Retail Core", workspace_id="retail-banking"),
            DataSetEntity(id="dataset-corporate", product_id="product-corporate", name="Corporate Core", workspace_id="corporate-banking"),
        ]
        if product_id:
            rows = [row for row in rows if row.product_id == product_id]
        if workspace:
            rows = [row for row in rows if row.workspace_id == workspace]
        return rows

    def list_data_objects_catalog(self, data_set_id: str | None = None) -> list[DataObjectCatalogEntity]:
        rows = [
            DataObjectCatalogEntity(id="object-retail", dataset_id="dataset-retail", name="customer_master"),
            DataObjectCatalogEntity(id="object-corporate", dataset_id="dataset-corporate", name="customer_registry"),
        ]
        if data_set_id:
            rows = [row for row in rows if row.dataset_id == data_set_id]
        return rows

    def get_data_object_version(self, version_id: str):
        versions = {
            "version-retail": SimpleNamespace(
                id="version-retail",
                data_object_id="object-retail",
                storage_uri="s3://retail/customer_master.parquet",
                storage_format="parquet",
                attribute_count=3,
            ),
            "version-corporate": SimpleNamespace(
                id="version-corporate",
                data_object_id="object-corporate",
                storage_uri="s3://corporate/customer_registry.parquet",
                storage_format="parquet",
                attribute_count=2,
            ),
        }
        return versions.get(version_id)

    def list_attributes_catalog(self, version_id: str | None = None) -> list[AttributeCatalogEntity]:
        rows = [
            AttributeCatalogEntity(
                id="attr-retail-customer-id",
                name="customer_id",
                type="string",
                is_primary_key=True,
                is_business_key=True,
                data_object_id="object-retail",
                version_id="version-retail",
            ),
            AttributeCatalogEntity(
                id="attr-retail-customer-status",
                name="customer_status",
                type="string",
                data_object_id="object-retail",
                version_id="version-retail",
            ),
            AttributeCatalogEntity(
                id="attr-retail-customer-segment",
                name="customer_segment",
                type="string",
                data_object_id="object-retail",
                version_id="version-retail",
            ),
            AttributeCatalogEntity(
                id="attr-retail-email",
                name="email_address",
                type="string",
                data_object_id="object-retail",
                version_id="version-retail",
            ),
            AttributeCatalogEntity(
                id="attr-retail-ssn",
                name="ssn",
                type="string",
                data_object_id="object-retail",
                version_id="version-retail",
            ),
            AttributeCatalogEntity(
                id="attr-corporate-customer-id",
                name="customer_id",
                type="string",
                is_business_key=True,
                data_object_id="object-corporate",
                version_id="version-corporate",
            ),
            AttributeCatalogEntity(
                id="attr-corporate-customer-status",
                name="customer_status",
                type="string",
                data_object_id="object-corporate",
                version_id="version-corporate",
            ),
        ]
        if version_id:
            rows = [row for row in rows if row.version_id == version_id]
        return rows

    def list_attribute_definition_mappings(self, version_id: str | None = None, attribute_id: str | None = None):
        _ = version_id
        _ = attribute_id
        return []


class _FakeDataAssetRepository:
    def list_data_assets(self, workspace_id: str | None = None):
        _ = workspace_id
        return []


class _FakeRulesRepository:
    async def list_rule_records(self, **kwargs):
        _ = kwargs
        return [
            SimpleNamespace(id="rule-1", tagIds=["tag-pii", "tag-customer"]),
            SimpleNamespace(id="rule-2", tagIds=["tag-finance"]),
        ]

    async def get_tags_by_ids(self, tag_ids: list[str]):
        mapping = {
            "tag-pii": RuleTagEntity(id="tag-pii", name="PII"),
            "tag-customer": RuleTagEntity(id="tag-customer", name="Customer"),
            "tag-finance": RuleTagEntity(id="tag-finance", name="Finance"),
        }
        return [mapping[tag_id] for tag_id in tag_ids if tag_id in mapping]


class _EmptyFakeDataCatalogRepository(_FakeDataCatalogRepository):
    def list_data_products(self, workspace: str | None = None) -> list[DataProductEntity]:
        del workspace
        return []

    def list_data_sets(self, product_id: str | None = None, workspace: str | None = None) -> list[DataSetEntity]:
        del product_id, workspace
        return []

    def list_data_objects_catalog(self, data_set_id: str | None = None) -> list[DataObjectCatalogEntity]:
        del data_set_id
        return []

    def list_attributes_catalog(self, version_id: str | None = None) -> list[AttributeCatalogEntity]:
        del version_id
        return []


def test_suggestions_fail_fast_without_database(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    monkeypatch.setattr(dependencies_module, "get_settings", lambda: SimpleNamespace(database_url=None))
    monkeypatch.setattr(dependencies_module, "_get_database_url", lambda _settings: None)

    response = client.get(
        "/api/data-catalog/v1/suggestions",
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:read"),
    )

    assert response.status_code == 503
    payload = response.json()
    assert "dq_db_internal_url or dq_db_local_url" in payload["detail"].lower()


def test_tag_suggestions_aggregate_previous_usage(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    class _TagSuggestionCatalogRepository(_FakeDataCatalogRepository):
        def list_data_products(self, workspace: str | None = None) -> list[DataProductEntity]:
            rows = [
                DataProductEntity(id="product-retail", name="Customer", workspace_id="retail-banking", tags=["customer", "pii"]),
                DataProductEntity(id="product-corporate", name="Registry", workspace_id="corporate-banking", tags=["finance"]),
            ]
            if workspace:
                return [row for row in rows if row.workspace_id == workspace]
            return rows

        def list_data_sets(self, product_id: str | None = None, workspace: str | None = None) -> list[DataSetEntity]:
            rows = [
                DataSetEntity(id="dataset-retail", product_id="product-retail", name="Retail Core", workspace_id="retail-banking", tags=["pii"]),
                DataSetEntity(id="dataset-corporate", product_id="product-corporate", name="Corporate Core", workspace_id="corporate-banking", tags=["finance"]),
            ]
            if product_id:
                rows = [row for row in rows if row.product_id == product_id]
            if workspace:
                rows = [row for row in rows if row.workspace_id == workspace]
            return rows

        def list_data_objects_catalog(self, data_set_id: str | None = None) -> list[DataObjectCatalogEntity]:
            rows = [
                DataObjectCatalogEntity(id="object-retail", dataset_id="dataset-retail", name="customer_master", tags=["customer", "pii"]),
                DataObjectCatalogEntity(id="object-corporate", dataset_id="dataset-corporate", name="customer_registry", tags=["finance"]),
            ]
            if data_set_id:
                rows = [row for row in rows if row.dataset_id == data_set_id]
            return rows

        def list_data_object_versions(self, object_id: str | None = None) -> list[object]:
            _ = object_id
            return []

        def list_attributes_catalog(self, version_id: str | None = None) -> list[AttributeCatalogEntity]:
            rows = [
                AttributeCatalogEntity(
                    id="attr-retail-customer-id",
                    name="customer_id",
                    type="string",
                    is_primary_key=True,
                    is_business_key=True,
                    data_object_id="object-retail",
                    version_id="version-retail",
                    tags=["customer", "pii"],
                ),
                AttributeCatalogEntity(
                    id="attr-corporate-customer-status",
                    name="customer_status",
                    type="string",
                    data_object_id="object-corporate",
                    version_id="version-corporate",
                    tags=["finance"],
                ),
            ]
            if version_id:
                rows = [row for row in rows if row.version_id == version_id]
            return rows

    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_rules_repository] = lambda: _FakeRulesRepository()
    app.dependency_overrides[get_data_catalog_repository] = lambda: _TagSuggestionCatalogRepository()
    app.dependency_overrides[get_data_asset_repository] = lambda: _FakeDataAssetRepository()

    response = client.get(
        "/api/data-catalog/v1/suggestions/tags?query=pi",
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["query"] == "pi"
    assert payload["count"] >= 1
    assert payload["tags"][0]["name"] in {"PII", "pii"}
    assert any(tag["name"] in {"PII", "pii"} for tag in payload["tags"])


def test_suggestions_list_returns_snake_case_contract(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
    suggestions_list_row: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    row = _to_snake_payload(dict(suggestions_list_row))
    row["user_id"] = str(suggestions_auth_claims.get("sub") or row.get("user_id") or "user-1")
    repository.suggestions = [SuggestionEntity.model_validate(row)]
    app.dependency_overrides[get_suggestions_repository] = lambda: repository

    response = client.get(
        "/api/data-catalog/v1/suggestions?status=pending",
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["count"] == 1
    assert payload["suggestions"][0]["data_source_id"] == "source-1"
    assert payload["suggestions"][0]["confidence_score"] == 0.92


def test_dq7_dsl_assistant_preview_returns_implemented_runtime_support_rows(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository

    response = client.get(
        "/api/data-catalog/v1/suggestions/dq7-dsl-assistant?check_type=PRESENT&current_workspace_id=retail-banking",
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["check_type"] == "PRESENT"
    assert payload["construct_family"] == "row_assertion"
    assert payload["capability_summary"] == "Row-level predicate checks over one or more selected attributes."
    assert payload["compiler_hint"] == "Current implemented runtime: GX predicate lowering with fail-fast validation."
    assert [item["engine"] for item in payload["support"]] == ["GX"]
    assert payload["support"][0]["engine"] == "GX"
    assert payload["support"][0]["support"] == "native"
    assert payload["support"][0]["notes"] == "Implemented through the GX lowerer for supported row predicates and evidence policy."
    rendered_support = str(payload["support"])
    assert "SodaCL" not in rendered_support
    assert "SQL" not in rendered_support
    assert "PySpark" not in rendered_support
    assert "Custom worker" not in rendered_support
    assert len(repository.preview_events) == 1
    event = repository.preview_events[0]
    assert event["user_id"] == str(suggestions_auth_claims["sub"])
    assert event["workspace_id"] == "retail-banking"
    assert event["action"] == "dq7_dsl_assistant_preview"
    assert event["result"] == "success"
    assert event["error_code"] is None
    assert event["details"] == {
        "check_type": "PRESENT",
        "construct_family": "row_assertion",
    }


@pytest.mark.parametrize(
    "prompt, expected_expression",
    [
        ("percentage must be above 10%", "discount_percent > 10"),
        ("percentage must be below 10%", "discount_percent < 10"),
    ],
)
def test_natural_language_preview_accepts_threshold_prompt(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
    prompt: str,
    expected_expression: str,
) -> None:
    class _RangePreviewCatalogRepository(_FakeDataCatalogRepository):
        def list_attributes_catalog(self, version_id: str | None = None) -> list[AttributeCatalogEntity]:
            rows = list(super().list_attributes_catalog(version_id))
            rows.append(
                AttributeCatalogEntity(
                    id="attr-retail-discount-percent",
                    name="discount_percent",
                    type="decimal",
                    data_object_id="object-retail",
                    version_id="version-retail",
                )
            )
            return rows

    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: _RangePreviewCatalogRepository()
    app.dependency_overrides[get_admin_repository] = lambda: _FakeAdminRepository(["retail-banking", "corporate-banking"])

    response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews",
        json={
            "prompt": prompt,
            "search_scope": "all_across_workspaces",
            "current_workspace_id": "retail-banking",
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["target_terms"] == ["discount_percent"]
    assert payload["draft_rule_preview"]["dsl"]["rule"]["kind"] == "row_assertion"
    assert payload["draft_rule_preview"]["dsl"]["rule"]["measure"]["predicate"]["expression"] == expected_expression


def test_natural_language_preview_returns_ranked_candidates_and_snake_case_contract(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: _FakeDataCatalogRepository()
    app.dependency_overrides[get_admin_repository] = lambda: _FakeAdminRepository(["retail-banking", "corporate-banking"])

    response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews",
        json={
            "prompt": "I want a uniqueness rule for attribute customer_id",
            "search_scope": "all_across_workspaces",
            "current_workspace_id": "retail-banking",
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["target_terms"] == ["customer_id"]
    assert payload["candidate_attributes"][0]["attribute_id"] == "attr-retail-customer-id"
    assert payload["candidate_attributes"][1]["workspace_id"] == "corporate-banking"
    assert payload["metadata_facts"]["signal_sources"] == [
        "schema",
        "tags",
        "glossary_terms",
        "profiling_requests",
        "historical_incidents",
    ]
    assert payload["metadata_facts"]["glossary_term_hits"] == ["Customer"]
    assert payload["metadata_facts"]["profiling_request_count"] == 2
    assert payload["metadata_facts"]["profiling_request_statuses"] == ["completed", "failed"]
    assert payload["metadata_facts"]["incident_count"] == 2
    assert payload["metadata_facts"]["incident_kinds"] == ["schema_drift", "volume_drop"]
    assert payload["metadata_facts"]["incident_root_cause_suggestion_count"] == 2
    assert payload["metadata_summary"] == (
        "The preview considered schema, tags, glossary_terms, profiling_requests, historical_incidents "
        "as supporting metadata signals."
    )
    assert payload["draft_rule_preview"]["workspace_id"] == "retail-banking"
    assert payload["draft_rule_preview"]["dsl"]["schema_version"] == "2.0.0"
    assert payload["draft_rule_preview"]["dsl"]["rule"]["kind"] == "metric_threshold"
    assert repository.preview_events == [
        {
            "user_id": str(suggestions_auth_claims["sub"]),
            "workspace_id": "retail-banking",
            "action": "preview_clicked",
            "result": "success",
            "error_code": None,
            "details": {"search_scope": "all_across_workspaces", "analysis_provider": "rapidfuzz"},
        }
    ]


def test_natural_language_preview_queues_llm_requests(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: _FakeDataCatalogRepository()
    app.dependency_overrides[get_admin_repository] = lambda: _FakeAdminRepository(["retail-banking", "corporate-banking"])

    captured: dict[str, object] = {}

    async def _fake_enqueue_natural_language_draft_job(*, request_body, settings, suggestions_repository, correlation_id, requested_by_user_id, accessible_workspace_ids, selected_attribute_ids=None):
        captured["request_body"] = request_body
        captured["selected_attribute_ids"] = list(selected_attribute_ids or [])
        captured["correlation_id"] = correlation_id
        captured["requested_by_user_id"] = requested_by_user_id
        captured["accessible_workspace_ids"] = sorted(accessible_workspace_ids)
        captured["suggestions_repository"] = suggestions_repository
        return SimpleNamespace(request_id="preview-request-1")

    monkeypatch.setattr(suggestions_endpoints, "enqueue_natural_language_draft_job", _fake_enqueue_natural_language_draft_job)

    response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews",
        json={
            "prompt": "I want a uniqueness rule for attribute customer_id",
            "search_scope": "all_across_workspaces",
            "current_workspace_id": "retail-banking",
            "analysis_provider": "llm",
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["queued"] is True
    assert payload["request_id"] == "preview-request-1"
    assert payload["message"] == "LLM preview request started. Check Recent LLM Analysis Requests for progress."
    assert captured["selected_attribute_ids"] == []
    assert captured["suggestions_repository"] is repository
    assert getattr(captured["request_body"], "analysisProvider") == "llm"
    assert repository.preview_events == [
        {
            "user_id": str(suggestions_auth_claims["sub"]),
            "workspace_id": "retail-banking",
            "action": "preview_clicked",
            "result": "success",
            "error_code": None,
            "details": {"search_scope": "all_across_workspaces", "analysis_provider": "llm"},
        },
        {
            "user_id": str(suggestions_auth_claims["sub"]),
            "workspace_id": "retail-banking",
            "action": "preview_queued",
            "result": "success",
            "error_code": None,
            "details": {
                "search_scope": "all_across_workspaces",
                "analysis_provider": "llm",
                "request_id": "preview-request-1",
            },
        },
    ]


def test_natural_language_preview_history_is_read_from_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _FakeSuggestionsRepository()
    repository.natural_language_requests = [
        NaturalLanguageDraftRequestEntity(
            request_id="preview-request-1",
            job_id="job-1",
            current_workspace_id="retail-banking",
            search_scope="all_across_workspaces",
            analysis_provider="llm",
            analysis_type="preview",
            prompt="I want a uniqueness rule for attribute customer_id",
            selected_attribute_ids=[],
            accessible_workspace_ids=["retail-banking", "corporate-banking"],
                requested_by_user_id="user-1",
            requested_at="2026-05-10T00:00:00+00:00",
            started_at="2026-05-10T00:00:01+00:00",
            completed_at="2026-05-10T00:00:02+00:00",
            status="completed",
            result={"candidate_attributes": [], "draft_rule_preview": {"name": "Preview"}},
        )
    ]
    monkeypatch.setattr(suggestions_endpoints, "get_user_id", lambda: "user-1")

    response = asyncio.run(
        suggestions_endpoints.list_natural_language_rule_draft_requests(
            workspace_id="retail-banking",
            limit=20,
            repository=repository,
        )
    )

    payload = json.loads(response.body.decode())
    assert payload["success"] is True
    assert payload["count"] == 1
    assert payload["requests"][0]["request_id"] == "preview-request-1"
    assert payload["requests"][0]["analysis_type"] == "preview"
    assert payload["requests"][0]["status"] == "completed"


def test_natural_language_steward_persists_metadata_explanation(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: _FakeDataCatalogRepository()
    app.dependency_overrides[get_admin_repository] = lambda: _FakeAdminRepository(["retail-banking", "corporate-banking"])

    response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews",
        json={
            "prompt": "Explain the stewarded metadata and list fixes",
            "assistant_mode": "steward",
            "target_type": "data_object_version",
            "target_id": "version-retail",
            "search_scope": "current",
            "current_workspace_id": "retail-banking",
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["assistant_mode"] == "steward"
    assert payload["target_type"] == "data_object_version"
    assert payload["target_id"] == "version-retail"
    assert payload["target_label"] == "customer_master"
    assert payload["metadata_summary"].startswith("Data object version 'customer_master'")
    assert payload["suggested_fixes"] == [
        "Map the unmapped attributes to glossary definitions to improve metadata explainability."
    ]
    assert repository.natural_language_requests[0].analysis_type == "steward"
    assert repository.natural_language_requests[0].status == "completed"
    assert repository.natural_language_requests[0].result is not None
    assert repository.natural_language_requests[0].result["assistant_mode"] == "steward"


def test_natural_language_preview_rejects_unauthorized_cross_workspace_scope(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: _FakeDataCatalogRepository()
    app.dependency_overrides[get_admin_repository] = lambda: _FakeAdminRepository(["retail-banking"])

    response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews",
        json={
            "prompt": "I want a uniqueness rule for attribute customer_id",
            "search_scope": "all_across_workspaces",
            "current_workspace_id": "retail-banking",
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"] == "unauthorized_search_scope"
    assert [event["action"] for event in repository.preview_events] == ["preview_clicked", "preview_error"]
    assert repository.preview_events[-1]["result"] == "failure"
    assert repository.preview_events[-1]["error_code"] == "cross_workspace_access_denied"


def test_natural_language_draft_creation_persists_suggestion(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: _FakeDataCatalogRepository()
    app.dependency_overrides[get_admin_repository] = lambda: _FakeAdminRepository(["retail-banking", "corporate-banking"])

    response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews/create-suggestion",
        json={
            "prompt": "  I want a uniqueness rule for attribute customer_id  ",
            "search_scope": "all",
            "current_workspace_id": "retail-banking",
            "selected_attribute_ids": ["attr-retail-customer-id"],
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["suggestion"]["data_source_id"] == "nl-preview:retail-banking"
    assert payload["suggestion"]["suggested_rule"]["check_type"] == "UNIQUENESS"
    assert payload["suggestion"]["suggested_rule"]["check_type_params"]["attributes"] == ["customer_id"]
    assert payload["suggestion"]["suggested_rule"]["dsl"]["schema_version"] == "2.0.0"
    assert payload["suggestion"]["suggested_rule"]["dsl"]["rule"]["kind"] == "metric_threshold"
    assert payload["suggestion"]["suggested_rule"]["prompt"] == "I want a uniqueness rule for attribute customer_id"
    assert payload["suggestion"]["suggested_rule"]["original_prompt_text"] == "  I want a uniqueness rule for attribute customer_id  "
    assert payload["suggestion"]["suggested_rule"]["selected_attribute_ids"] == ["attr-retail-customer-id"]
    assert payload["suggestion"]["suggested_rule"]["parent_context_snapshot"][0]["parent_path"] == [
        "Customer",
        "Retail Core",
        "customer_master",
    ]
    assert repository.create_suggestion_calls[0]["data_source_id"] == "nl-preview:retail-banking"
    assert repository.preview_events[-1]["action"] == "draft_created"
    assert repository.preview_events[-1]["details"]["attribute_count"] == 1


def test_accept_suggestion_records_the_created_rule_id(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    approvals_repository = _FakeApprovalsRepository()
    repository.update_result = SuggestionActionResultEntity(message="Suggestion accepted")
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_approvals_repository] = lambda: approvals_repository

    response = client.post(
        "/api/data-catalog/v1/suggestions/sug-1/accept",
        json={"rule_id": "rule-1", "workspace_id": "retail-banking"},
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 200
    assert repository.update_calls[0]["action"] == "accept"
    assert repository.update_calls[0]["rule_id"] == "rule-1"
    assert approvals_repository.audit_events[0]["action"] == "suggestion.accepted"
    assert approvals_repository.audit_events[0]["details"]["workspace_id"] == "retail-banking"
    assert approvals_repository.audit_events[0]["details"]["rule_id"] == "rule-1"


def test_natural_language_preview_returns_condition_and_role_aware_candidates(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    app.dependency_overrides[get_suggestions_repository] = lambda: _FakeSuggestionsRepository()
    app.dependency_overrides[get_data_catalog_repository] = lambda: _FakeDataCatalogRepository()
    app.dependency_overrides[get_admin_repository] = lambda: _FakeAdminRepository(["retail-banking", "corporate-banking"])

    response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews",
        json={
            "prompt": "When a customer is active, a valid email address must be filled in",
            "search_scope": "all_across_workspaces",
            "current_workspace_id": "retail-banking",
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["parsed_condition"] == {
        "attribute_term": "status",
        "operator": "equals",
        "value": "active",
        "same_version_required": True,
    }
    assert payload["draft_rule_preview"]["dsl"]["schema_version"] == "2.0.0"
    assert payload["draft_rule_preview"]["dsl"]["rule"]["kind"] == "row_assertion"
    assert any(
        candidate["attribute_id"] == "attr-retail-email" and "target" in candidate["match_roles"]
        for candidate in payload["candidate_attributes"]
    )
    assert any(
        candidate["attribute_id"] == "attr-retail-customer-status" and "condition" in candidate["match_roles"]
        for candidate in payload["candidate_attributes"]
    )


def test_natural_language_conditional_draft_creation_requires_same_object_version(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: _FakeDataCatalogRepository()
    app.dependency_overrides[get_admin_repository] = lambda: _FakeAdminRepository(["retail-banking", "corporate-banking"])

    response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews/create-suggestion",
        json={
            "prompt": "When a customer is active, a valid email address must be filled in",
            "search_scope": "all_across_workspaces",
            "current_workspace_id": "retail-banking",
            "selected_attribute_ids": ["attr-retail-email", "attr-corporate-customer-status"],
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "invalid_natural_language_draft"
    assert "same data object version" in payload["message"]
    assert repository.create_suggestion_calls == []


def test_natural_language_conditional_regex_draft_creation_persists_condition_params(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: _FakeDataCatalogRepository()
    app.dependency_overrides[get_admin_repository] = lambda: _FakeAdminRepository(["retail-banking", "corporate-banking"])

    response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews/create-suggestion",
        json={
            "prompt": "If customer segment is Retail then the SSN must be filled in and valid",
            "search_scope": "all",
            "current_workspace_id": "retail-banking",
            "selected_attribute_ids": ["attr-retail-customer-segment", "attr-retail-ssn"],
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["suggestion"]["suggested_rule"]["check_type"] == "REGEX"
    assert payload["suggestion"]["suggested_rule"]["dsl"]["schema_version"] == "2.0.0"
    assert payload["suggestion"]["suggested_rule"]["dsl"]["rule"]["kind"] == "row_assertion"
    params = repository.create_suggestion_calls[0]["suggested_rule"]["check_type_params"]
    assert params["attribute"] == "ssn"
    assert params["requirePresent"] is True
    assert params["condition"] == {
        "attribute": "customer_segment",
        "operator": "equals",
        "value": "Retail",
    }
    assert params["pattern"] == r"^\d{3}-\d{2}-\d{4}$"


def test_natural_language_preview_fails_closed_for_incomplete_allowlist_prompt(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: _FakeDataCatalogRepository()
    app.dependency_overrides[get_admin_repository] = lambda: _FakeAdminRepository(["retail-banking"])

    response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews",
        json={
            "prompt": "Validate that country_code only uses allowed ISO country values",
            "search_scope": "all",
            "current_workspace_id": "retail-banking",
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "invalid_natural_language_preview"
    assert repository.preview_events[-1]["action"] == "preview_error"
    assert repository.preview_events[-1]["result"] == "failure"


def test_natural_language_preview_rejects_blank_prompt_with_explicit_error_code(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: _FakeDataCatalogRepository()
    app.dependency_overrides[get_admin_repository] = lambda: _FakeAdminRepository(["retail-banking"])

    response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews",
        json={
            "prompt": "   ",
            "search_scope": "current",
            "current_workspace_id": "retail-banking",
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "blank_prompt"
    assert payload["message"] == "Preview prompt cannot be blank."
    assert repository.preview_events[-1]["error_code"] == "blank_prompt"


def test_natural_language_preview_rejects_missing_metadata_dependencies_with_explicit_error_code(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: _EmptyFakeDataCatalogRepository()
    app.dependency_overrides[get_admin_repository] = lambda: _FakeAdminRepository(["retail-banking"])

    response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews",
        json={
            "prompt": "I want a uniqueness rule for attribute customer_id",
            "search_scope": "current",
            "current_workspace_id": "retail-banking",
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "missing_metadata_dependencies"
    assert "Preview metadata dependencies are unavailable" in payload["message"]
    assert repository.preview_events[-1]["error_code"] == "missing_metadata_dependencies"


def test_natural_language_preview_telemetry_endpoint_records_selection_and_cancel(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    app.dependency_overrides[get_suggestions_repository] = lambda: repository

    selection_response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews/telemetry",
        json={
            "action": "attributes_selected",
            "current_workspace_id": "retail-banking",
            "selected_attribute_count": 2,
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    cancel_response = client.post(
        "/api/data-catalog/v1/suggestions/natural-language-rule-previews/telemetry",
        json={
            "action": "preview_cancelled",
            "current_workspace_id": "retail-banking",
            "selected_attribute_count": 1,
        },
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:create", "dq:rules:write"),
    )

    assert selection_response.status_code == 200
    assert cancel_response.status_code == 200
    assert [event["action"] for event in repository.preview_events] == ["attributes_selected", "preview_cancelled"]
    assert repository.preview_events[0]["details"] == {"selected_attribute_count": 2}


def test_request_profiling_returns_rate_limit_payload(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
    suggestions_rate_limit_payload: dict[str, object],
) -> None:
    repository = _FakeProfilingRepository()
    payload = _to_snake_payload(dict(suggestions_rate_limit_payload))
    repository.request_profiling_error = ProfilingRateLimitError(
        last_requested_at=str(payload["last_requested_at"]),
        minutes_remaining=int(payload["minutes_remaining"]),
    )
    app.dependency_overrides[get_profiling_repository] = lambda: repository

    response = client.post(
        "/api/data-catalog/v1/profiling/requests?data_source_id=source-1&workspace_id=retail-banking",
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:profiling:request"),
    )

    assert response.status_code == 429
    payload = response.json()
    assert payload["status"] == 429
    assert payload["minutes_remaining"] == 12
    assert payload["last_requested_at"] == "2026-03-29T09:00:00+00:00"


def test_request_profiling_records_workspace_audit_event(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeProfilingRepository()
    approvals_repository = _FakeApprovalsRepository()
    repository.request_profiling_result = SuggestionProfilingStartEntity(
        profiling_request_id="req-1",
        message="Data profiling started.",
        status="pending",
    )
    app.dependency_overrides[get_profiling_repository] = lambda: repository
    app.dependency_overrides[get_approvals_repository] = lambda: approvals_repository

    response = client.post(
        "/api/data-catalog/v1/profiling/requests?data_source_id=source-1&workspace_id=retail-banking",
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:profiling:request"),
    )

    assert response.status_code == 200
    assert repository.request_profiling_calls[0] == {"user_id": suggestions_auth_claims["sub"], "data_source_id": "source-1"}
    assert approvals_repository.audit_events[0]["action"] == "profiling.requested"
    assert approvals_repository.audit_events[0]["details"]["workspace_id"] == "retail-banking"
    assert approvals_repository.audit_events[0]["details"]["profiling_request_id"] == "req-1"


def test_apply_suggestion_accepts_snake_case_rule_id(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
    suggestions_apply_payload: dict[str, object],
    suggestions_apply_success_payload: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    approvals_repository = _FakeApprovalsRepository()
    repository.update_result = SuggestionActionResultEntity.model_validate(suggestions_apply_success_payload)
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_approvals_repository] = lambda: approvals_repository

    request_payload = dict(suggestions_apply_payload)
    request_payload["workspace_id"] = "retail-banking"

    response = client.post(
        "/api/data-catalog/v1/suggestions/sug-1/apply",
        json=request_payload,
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:edit"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert repository.update_calls[0]["action"] == "apply"
    assert repository.update_calls[0]["rule_id"] == suggestions_apply_payload["rule_id"]
    assert approvals_repository.audit_events[0]["action"] == "suggestion.applied"
    assert approvals_repository.audit_events[0]["details"]["workspace_id"] == "retail-banking"


def test_suggestions_helpers_cover_conversion_and_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    assert suggestions_repo_module._to_iso(None) is None

    naive = datetime(2026, 3, 29, 10, 0, 0)
    aware = datetime(2026, 3, 29, 10, 0, 0, tzinfo=UTC)
    assert suggestions_repo_module._to_iso(naive).endswith("+00:00")
    assert suggestions_repo_module._to_iso(aware).endswith("+00:00")

    assert suggestions_repo_module._to_float(None) is None
    assert suggestions_repo_module._to_float(Decimal("0.25")) == 0.25

    monkeypatch.setattr(suggestions_endpoints, "get_scopes", lambda: ["dq:profiling:request"])
    monkeypatch.setattr(
        suggestions_endpoints,
        "has_required_scope",
        lambda scopes, required: "dq:profiling:request" in scopes and bool(required),
    )
    assert suggestions_endpoints._can_request_profiling() is True


def test_postgres_repository_list_helpers_map_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    source_row = SimpleNamespace(
        data_source_id="src-1",
        name="Source",
        source_type="postgres",
        record_count=123,
        last_profiled_at=now,
    )
    suggestion_row = SimpleNamespace(
        id="sug-1",
        user_id="user-1",
        data_source_id="src-1",
        suggested_rule={"name": "rule"},
        confidence_score=Decimal("0.75"),
        reason="quality",
        rule_type="completeness",
        created_from_profiling_request_id="req-1",
        status="pending",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    user_row = SimpleNamespace(id="user-1", external_id="external-user-1")
    profiling_request_row = SimpleNamespace(
        id="req-1",
        data_source_id="src-1",
        requested_by_user_id="user-1",
        requested_at=now,
        started_at=now + timedelta(minutes=1),
        completed_at=None,
        status="started",
        error_message=None,
        result_metadata_id=None,
        job_id="job-1",
    )

    repository = PostgresSuggestionsRepository("postgresql://stub")
    profiling_repository = PostgresProfilingRepository("postgresql://stub")
    monkeypatch.setattr(
        suggestions_repo_module,
        "session_scope",
        _SessionScopeStub(
            [
                _FakeSession([_FakeExecuteResult(all_rows=[source_row])]),
                _FakeSession([_FakeExecuteResult(all_rows=[suggestion_row])]),
                _FakeSession(
                    [
                        _FakeExecuteResult(scalar_one_or_none=user_row),
                        _FakeExecuteResult(all_rows=[profiling_request_row]),
                    ]
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        profiling_repo_module,
        "session_scope",
        _SessionScopeStub(
            [
                _FakeSession(
                    [
                        _FakeExecuteResult(scalar_one_or_none=None),
                        _FakeExecuteResult(scalar_one_or_none=user_row),
                        _FakeExecuteResult(all_rows=[profiling_request_row]),
                    ]
                ),
            ]
        ),
    )

    sources = repository.list_data_sources()
    assert sources[0].data_source_id == "src-1"
    assert str(sources[0].last_profiled_at).endswith("+00:00")

    suggestions = repository.list_suggestions(
        user_id="user-1",
        data_source_id="src-1",
        status="pending",
    )
    assert suggestions[0].id == "sug-1"
    assert suggestions[0].confidence_score == 0.75

    profiling_requests = profiling_repository.list_profiling_requests(
        user_id="external-user-1",
        data_source_id="src-1",
        limit=10,
    )
    assert profiling_requests[0].id == "req-1"
    assert profiling_requests[0].requested_by_user_id == "user-1"
    assert profiling_requests[0].job_id == "job-1"


def test_postgres_list_suggestions_without_optional_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    row = SimpleNamespace(
        id="sug-2",
        user_id="user-2",
        data_source_id="src-2",
        suggested_rule={"name": "rule-2"},
        confidence_score=None,
        reason=None,
        rule_type=None,
        created_from_profiling_request_id=None,
        status="pending",
        created_at=None,
        expires_at=None,
    )
    repository = PostgresSuggestionsRepository("postgresql://stub")
    monkeypatch.setattr(
        suggestions_repo_module,
        "session_scope",
        _SessionScopeStub([_FakeSession([_FakeExecuteResult(all_rows=[row])])]),
    )

    suggestions = repository.list_suggestions(user_id=None, data_source_id=None, status="")

    assert suggestions[0].id == "sug-2"
    assert suggestions[0].confidence_score is None


def test_postgres_request_profiling_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresProfilingRepository("postgresql://stub")

    missing_source_session = _FakeSession(
        [
            _FakeExecuteResult(scalar_one_or_none=None),
            _FakeExecuteResult(scalar_one_or_none=None),
            _FakeExecuteResult(scalar_one_or_none=None),
        ]
    )
    monkeypatch.setattr(profiling_repo_module, "session_scope", _SessionScopeStub([missing_source_session]))
    with pytest.raises(ProfilingDataSourceNotFoundError):
        repository.request_profiling(user_id="user-1", data_source_id="src-missing")

    now = datetime.now(UTC)
    recent = SimpleNamespace(requested_at=now - timedelta(minutes=5))
    source = SimpleNamespace(data_source_id="src-1", name="Source 1", source_type="postgres")
    recent_session = _FakeSession(
        [
            _FakeExecuteResult(scalar_one_or_none=None),
            _FakeExecuteResult(scalar_one_or_none=None),
            _FakeExecuteResult(scalar_one_or_none=source),
            _FakeExecuteResult(scalar_one_or_none=recent),
        ]
    )
    monkeypatch.setattr(profiling_repo_module, "session_scope", _SessionScopeStub([recent_session]))
    with pytest.raises(ProfilingRateLimitError) as exc_info:
        repository.request_profiling(user_id="user-1", data_source_id="src-1")
    assert exc_info.value.minutes_remaining >= 1

    old = SimpleNamespace(requested_at=now - timedelta(hours=26))
    success_session = _FakeSession(
        [
            _FakeExecuteResult(scalar_one_or_none=None),
            _FakeExecuteResult(scalar_one_or_none=None),
            _FakeExecuteResult(scalar_one_or_none=source),
            _FakeExecuteResult(scalar_one_or_none=old),
        ]
    )
    monkeypatch.setattr(profiling_repo_module, "session_scope", _SessionScopeStub([success_session]))
    monkeypatch.setattr(repository, "_enqueue_profiling_request", lambda **_kwargs: None)
    payload = repository.request_profiling(user_id="user-1", data_source_id="src-1")
    assert payload.status == "pending"
    assert success_session.commits == 1
    assert len(success_session.added) == 2

    enqueue_failed_session = _FakeSession(
        [
            _FakeExecuteResult(scalar_one_or_none=None),
            _FakeExecuteResult(scalar_one_or_none=None),
            _FakeExecuteResult(scalar_one_or_none=source),
            _FakeExecuteResult(scalar_one_or_none=old),
        ]
    )
    monkeypatch.setattr(profiling_repo_module, "session_scope", _SessionScopeStub([enqueue_failed_session]))
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        repository,
        "_enqueue_profiling_request",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("redis down")),
    )
    monkeypatch.setattr(repository, "_mark_request_enqueue_failed", lambda **kwargs: captured.update(kwargs))
    with pytest.raises(ProfilingEnqueueFailedError) as exc_info:
        repository.request_profiling(user_id="user-1", data_source_id="src-1")
    assert exc_info.value.profiling_request_id
    assert captured["error_message"] == "redis down"


def test_postgres_update_status_and_profiling_status_and_clear_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresSuggestionsRepository("postgresql://stub")
    profiling_repository = PostgresProfilingRepository("postgresql://stub")

    missing_session = _FakeSession(
        [
            _FakeExecuteResult(scalar_one_or_none=None),
            _FakeExecuteResult(scalar_one_or_none=None),
            _FakeExecuteResult(scalar_one_or_none=None),
        ]
    )
    monkeypatch.setattr(suggestions_repo_module, "session_scope", _SessionScopeStub([missing_session]))
    with pytest.raises(SuggestionNotFoundError):
        repository.update_suggestion_status(
            user_id="user-1",
            suggestion_id="missing",
            action="accept",
        )

    suggestion = SimpleNamespace(id="sug-1", status="pending", data_source_id="nl-preview:retail-banking")
    update_session = _FakeSession(
        [
            _FakeExecuteResult(scalar_one_or_none=None),
            _FakeExecuteResult(scalar_one_or_none=None),
            _FakeExecuteResult(scalar_one_or_none=suggestion),
        ]
    )
    monkeypatch.setattr(suggestions_repo_module, "session_scope", _SessionScopeStub([update_session]))
    payload = repository.update_suggestion_status(
        user_id="user-1",
        suggestion_id="sug-1",
        action="dismiss",
    )
    assert payload.message == "Suggestion dismissed"
    assert suggestion.status == "dismissed"
    assert update_session.commits == 1

    status_missing_session = _FakeSession([_FakeExecuteResult(scalar_one_or_none=None)])
    monkeypatch.setattr(profiling_repo_module, "session_scope", _SessionScopeStub([status_missing_session]))
    with pytest.raises(ProfilingRequestNotFoundError):
        profiling_repository.get_profiling_request_status("missing")

    row = SimpleNamespace(
        id="req-1",
        data_source_id="src-1",
        requested_by_user_id="user-1",
        requested_at=datetime.now(UTC),
        started_at=None,
        completed_at=None,
        status="pending",
        error_message=None,
        result_metadata_id=None,
        job_id=None,
    )
    status_ok_session = _FakeSession([_FakeExecuteResult(scalar_one_or_none=row)])
    monkeypatch.setattr(profiling_repo_module, "session_scope", _SessionScopeStub([status_ok_session]))
    payload = profiling_repository.get_profiling_request_status("req-1")
    assert payload.id == "req-1"

    clear_session = _FakeSession([_FakeExecuteResult(rowcount=3), _FakeExecuteResult(rowcount=2)])
    monkeypatch.setattr(suggestions_repo_module, "session_scope", _SessionScopeStub([clear_session]))
    cleared = repository.clear_metrics()
    assert cleared.deleted_count == 5
    assert clear_session.commits == 1


def test_suggestions_endpoints_cover_remaining_auth_and_paths(
    client: TestClient,
    auth_headers: callable,
    suggestions_auth_claims: dict[str, object],
) -> None:
    repository = _FakeSuggestionsRepository()
    profiling_repository = _FakeProfilingRepository()
    repository.data_sources = [SuggestionDataSourceEntity(data_source_id="src-1", name="Source")]
    profiling_repository.profiling_status_result = SuggestionProfilingRequestEntity(id="req-1")
    profiling_repository.profiling_requests = [SuggestionProfilingRequestEntity(id="req-2", status="pending")]
    repository.clear_result = SuggestionMetricsClearResultEntity(
        message="Suggestions metrics cleared",
        deleted_count=0,
    )
    app.dependency_overrides[get_suggestions_repository] = lambda: repository
    app.dependency_overrides[get_profiling_repository] = lambda: profiling_repository

    data_sources_response = client.get(
        "/api/data-catalog/v1/suggestions/data-sources",
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:read"),
    )
    assert data_sources_response.status_code == 200
    assert data_sources_response.json()["can_request_profiling"] is False

    unauth_profile = client.post(
        "/api/data-catalog/v1/profiling/requests?data_source_id=source-1&workspace_id=retail-banking",
        headers=auth_headers("dq:profiling:request", sub="", preferred_username=""),
    )
    assert unauth_profile.status_code == 401

    unauth_accept = client.post(
        "/api/data-catalog/v1/suggestions/sug-1/accept",
        headers=auth_headers("dq:rules:edit", sub="", preferred_username=""),
    )
    unauth_dismiss = client.post(
        "/api/data-catalog/v1/suggestions/sug-1/dismiss",
        headers=auth_headers("dq:rules:edit", sub="", preferred_username=""),
    )
    unauth_apply = client.post(
        "/api/data-catalog/v1/suggestions/sug-1/apply",
        json={},
        headers=auth_headers("dq:rules:edit", sub="", preferred_username=""),
    )
    assert unauth_accept.status_code == 401
    assert unauth_dismiss.status_code == 401
    assert unauth_apply.status_code == 401

    profiling_status = client.get(
        "/api/data-catalog/v1/profiling/requests/req-1/status",
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:read"),
    )
    assert profiling_status.status_code == 200
    assert profiling_status.json()["request"]["id"] == "req-1"

    profiling_requests = client.get(
        "/api/data-catalog/v1/profiling/requests?limit=5",
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:read"),
    )
    assert profiling_requests.status_code == 200
    assert profiling_requests.json()["profiling_requests"][0]["id"] == "req-2"

    unauth_profiling_requests = client.get(
        "/api/data-catalog/v1/profiling/requests",
        headers=auth_headers("dq:rules:read", sub="", preferred_username=""),
    )
    assert unauth_profiling_requests.status_code == 401

    clear_response = client.post(
        "/api/data-catalog/v1/suggestions/metrics/clear",
        headers=_suggestions_headers(auth_headers, suggestions_auth_claims, "dq:rules:edit"),
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["deleted_count"] == 0
