from __future__ import annotations

import asyncio

import httpx
import pytest

from app.application.services.natural_language_rule_drafting import build_natural_language_rule_draft_suggestion_payload
from app.application.services.natural_language_rule_drafting import build_ranked_preview_candidate_attributes
from app.application.services.natural_language_rule_drafting import build_natural_language_rule_preview_payload
from app.application.services.natural_language_rule_drafting import build_natural_language_rule_preview_payload_for_provider
from app.application.services.natural_language_rule_drafting import resolve_authorized_preview_search_scope
from app.domain.entities.data_catalog import AttributeCatalogEntity
from app.domain.entities.data_catalog import DataObjectCatalogEntity
from app.domain.entities.data_catalog import DataProductEntity
from app.domain.entities.data_catalog import DataSetEntity


class _PreviewCatalogRepository:
    def __init__(self) -> None:
        self._data_products = [
            DataProductEntity(id="product-retail", name="Retail Banking", workspace_id="retail-banking"),
            DataProductEntity(id="product-corporate", name="Corporate Banking", workspace_id="corporate-banking"),
        ]
        self._data_sets = [
            DataSetEntity(id="dataset-retail", product_id="product-retail", name="Customer Records", workspace_id="retail-banking"),
            DataSetEntity(id="dataset-corporate", product_id="product-corporate", name="Customer Registry", workspace_id="corporate-banking"),
        ]
        self._data_objects = [
            DataObjectCatalogEntity(id="object-retail", dataset_id="dataset-retail", name="customer_master", latest_version_id="version-retail"),
            DataObjectCatalogEntity(id="object-corporate", dataset_id="dataset-corporate", name="customer_registry", latest_version_id="version-corporate"),
        ]
        self._attributes = [
            AttributeCatalogEntity(
                id="attr-retail-customer-id",
                name="customer_id",
                type="string",
                data_object_id="object-retail",
                version_id="version-retail",
                is_primary_key=True,
            ),
            AttributeCatalogEntity(
                id="attr-retail-email",
                name="customer_email",
                type="string",
                data_object_id="object-retail",
                version_id="version-retail",
            ),
            AttributeCatalogEntity(
                id="attr-retail-discount-percent",
                name="discount_percent",
                type="decimal",
                data_object_id="object-retail",
                version_id="version-retail",
            ),
            AttributeCatalogEntity(
                id="attr-corporate-customer-id",
                name="customer_id",
                type="string",
                data_object_id="object-corporate",
                version_id="version-corporate",
                is_primary_key=True,
            ),
            AttributeCatalogEntity(
                id="attr-corporate-customer-status",
                name="customer_status",
                type="string",
                data_object_id="object-corporate",
                version_id="version-corporate",
            ),
        ]

    def list_data_products(self, workspace: str | None = None):
        del workspace
        return list(self._data_products)

    def list_data_objects(self):
        raise AssertionError("not used")

    def list_data_sets(self, product_id: str | None = None, workspace: str | None = None):
        del workspace
        if product_id is None:
            return list(self._data_sets)
        return [row for row in self._data_sets if row.product_id == product_id]

    def list_rule_attributes(self):
        raise AssertionError("not used")

    def add_rule_attributes(self, entries: list[dict]):
        raise AssertionError("not used")

    def get_attribute_rule_counts(self):
        raise AssertionError("not used")

    def list_data_objects_catalog(self, data_set_id: str | None = None):
        if data_set_id is None:
            return list(self._data_objects)
        return [row for row in self._data_objects if row.dataset_id == data_set_id]

    def list_data_object_versions(self, object_id: str | None = None):
        del object_id
        raise AssertionError("not used")

    def get_data_object_version(self, version_id: str):
        del version_id
        raise AssertionError("not used")

    def list_attributes_catalog(self, version_id: str | None = None):
        if version_id is None:
            return list(self._attributes)
        return [row for row in self._attributes if row.version_id == version_id]

    def list_attribute_definition_mappings(self, version_id: str | None = None, attribute_id: str | None = None):
        del version_id, attribute_id
        raise AssertionError("not used")

    def upsert_attribute_definition_mapping(self, *, attribute_id: str, definition_id: str | None, mapping_state: str, mapped_by: str | None):
        del attribute_id, definition_id, mapping_state, mapped_by
        raise AssertionError("not used")

    def list_data_deliveries(self, version_id: str | None = None, workspace: str | None = None):
        del version_id, workspace
        raise AssertionError("not used")

    def get_data_delivery_note(self, delivery_id: str):
        del delivery_id
        raise AssertionError("not used")

    def create_materialized_delivery_note(self, payload: dict[str, object]):
        del payload
        raise AssertionError("not used")


class _EmptyPreviewCatalogRepository(_PreviewCatalogRepository):
    def __init__(self) -> None:
        self._data_products = []
        self._data_sets = []
        self._data_objects = []
        self._attributes = []


@pytest.fixture()
def preview_catalog_repository() -> _PreviewCatalogRepository:
    return _PreviewCatalogRepository()


@pytest.fixture()
def empty_preview_catalog_repository() -> _EmptyPreviewCatalogRepository:
    return _EmptyPreviewCatalogRepository()


@pytest.fixture()
def accessible_workspace_ids() -> set[str]:
    return {"retail-banking", "corporate-banking"}


@pytest.fixture()
def single_workspace_ids() -> set[str]:
    return {"retail-banking"}


def test_build_natural_language_rule_preview_payload_ranks_candidates_and_builds_dsl(
    preview_catalog_repository: _PreviewCatalogRepository,
    accessible_workspace_ids: set[str],
) -> None:
    payload = build_natural_language_rule_preview_payload(
        prompt="I want a uniqueness rule for attribute customer_id",
        search_scope="all_across_workspaces",
        current_workspace_id="retail-banking",
        accessible_workspace_ids=accessible_workspace_ids,
        catalog_repository=preview_catalog_repository,
    )

    assert payload["success"] is True
    assert payload["target_terms"] == ["customer_id"]
    assert payload["candidate_attributes"][0]["attribute_id"] == "attr-retail-customer-id"
    assert payload["candidate_attributes"][1]["workspace_id"] == "corporate-banking"
    assert payload["draft_rule_preview"]["workspace_id"] == "retail-banking"
    assert payload["draft_rule_preview"]["dsl"]["schema_version"] == "2.0.0"
    assert payload["draft_rule_preview"]["dsl"]["rule"]["kind"] == "metric_threshold"


def test_build_natural_language_rule_preview_payload_rejects_blank_prompt(
    preview_catalog_repository: _PreviewCatalogRepository,
    accessible_workspace_ids: set[str],
) -> None:
    with pytest.raises(ValueError, match="Preview prompt cannot be blank"):
        build_natural_language_rule_preview_payload(
            prompt="   ",
            search_scope="current",
            current_workspace_id="retail-banking",
            accessible_workspace_ids=accessible_workspace_ids,
            catalog_repository=preview_catalog_repository,
        )


def test_build_natural_language_rule_preview_payload_rejects_missing_workspace(
    preview_catalog_repository: _PreviewCatalogRepository,
    accessible_workspace_ids: set[str],
) -> None:
    with pytest.raises(ValueError, match="A current workspace is required to generate a preview"):
        build_natural_language_rule_preview_payload(
            prompt="I want a uniqueness rule for attribute customer_id",
            search_scope="current",
            current_workspace_id="   ",
            accessible_workspace_ids=accessible_workspace_ids,
            catalog_repository=preview_catalog_repository,
        )


def test_build_natural_language_rule_preview_payload_rejects_missing_metadata_dependencies(
    empty_preview_catalog_repository: _EmptyPreviewCatalogRepository,
    accessible_workspace_ids: set[str],
) -> None:
    with pytest.raises(ValueError, match="Preview metadata dependencies are unavailable"):
        build_natural_language_rule_preview_payload(
            prompt="I want a uniqueness rule for attribute customer_id",
            search_scope="current",
            current_workspace_id="retail-banking",
            accessible_workspace_ids=accessible_workspace_ids,
            catalog_repository=empty_preview_catalog_repository,
        )


def test_build_ranked_preview_candidate_attributes_filters_to_current_workspace(
    preview_catalog_repository: _PreviewCatalogRepository,
    accessible_workspace_ids: set[str],
) -> None:
    candidates = build_ranked_preview_candidate_attributes(
        catalog_repository=preview_catalog_repository,
        check_type="UNIQUENESS",
        target_term="customer_id",
        search_scope="current",
        current_workspace_id="retail-banking",
        allowed_workspace_ids=accessible_workspace_ids,
    )

    assert [candidate["attribute_id"] for candidate in candidates] == ["attr-retail-customer-id"]
    assert candidates[0]["workspace_id"] == "retail-banking"
    assert candidates[0]["parent_path"] == ["Retail Banking", "Customer Records", "customer_master"]
    assert candidates[0]["match_reasons"][0] == "Exact attribute-name match"


def test_build_ranked_preview_candidate_attributes_orders_current_workspace_first(
    preview_catalog_repository: _PreviewCatalogRepository,
    accessible_workspace_ids: set[str],
) -> None:
    candidates = build_ranked_preview_candidate_attributes(
        catalog_repository=preview_catalog_repository,
        check_type="UNIQUENESS",
        target_term="customer_id",
        search_scope="all_across_workspaces",
        current_workspace_id="retail-banking",
        allowed_workspace_ids=accessible_workspace_ids,
    )

    assert [candidate["attribute_id"] for candidate in candidates[:2]] == [
        "attr-retail-customer-id",
        "attr-corporate-customer-id",
    ]
    assert candidates[0]["current_context"] is True
    assert candidates[0]["match_roles"] == ["target"]
    assert candidates[1]["current_context"] is False
    assert candidates[1]["match_roles"] == ["target"]


def test_resolve_authorized_preview_search_scope_limits_non_cross_workspace_modes(
    accessible_workspace_ids: set[str],
) -> None:
    current_scope = resolve_authorized_preview_search_scope(
        search_scope="current",
        current_workspace_id="retail-banking",
        accessible_workspace_ids=accessible_workspace_ids,
    )

    all_scope = resolve_authorized_preview_search_scope(
        search_scope="all",
        current_workspace_id="retail-banking",
        accessible_workspace_ids=accessible_workspace_ids,
    )

    assert current_scope.search_scope == "current"
    assert current_scope.current_workspace_id == "retail-banking"
    assert current_scope.allowed_workspace_ids == {"retail-banking"}
    assert all_scope.search_scope == "all"
    assert all_scope.allowed_workspace_ids == {"retail-banking"}


def test_resolve_authorized_preview_search_scope_expands_cross_workspace_scope_when_allowed(
    accessible_workspace_ids: set[str],
) -> None:
    resolved = resolve_authorized_preview_search_scope(
        search_scope="all_across_workspaces",
        current_workspace_id="retail-banking",
        accessible_workspace_ids=accessible_workspace_ids,
    )

    assert resolved.search_scope == "all_across_workspaces"
    assert resolved.current_workspace_id == "retail-banking"
    assert resolved.allowed_workspace_ids == accessible_workspace_ids


def test_resolve_authorized_preview_search_scope_rejects_cross_workspace_scope_without_access(
    single_workspace_ids: set[str],
) -> None:
    with pytest.raises(PermissionError, match="Cross-workspace attribute search is not available for this user"):
        resolve_authorized_preview_search_scope(
            search_scope="all_across_workspaces",
            current_workspace_id="retail-banking",
            accessible_workspace_ids=single_workspace_ids,
        )


def test_build_natural_language_rule_preview_payload_infers_catalog_term_from_prompt(
    preview_catalog_repository: _PreviewCatalogRepository,
    accessible_workspace_ids: set[str],
) -> None:
    payload = build_natural_language_rule_preview_payload(
        prompt="percentage must be above 10%",
        search_scope="all_across_workspaces",
        current_workspace_id="retail-banking",
        accessible_workspace_ids=accessible_workspace_ids,
        catalog_repository=preview_catalog_repository,
    )

    assert payload["target_terms"] == ["discount_percent"]
    assert payload["draft_rule_preview"]["dsl"]["rule"]["kind"] == "row_assertion"
    assert payload["draft_rule_preview"]["dsl"]["rule"]["measure"]["predicate"]["expression"] == "discount_percent > 10"


def test_build_natural_language_rule_draft_suggestion_payload_preserves_selected_snapshot(
    preview_catalog_repository: _PreviewCatalogRepository,
    accessible_workspace_ids: set[str],
) -> None:
    preview_payload = build_natural_language_rule_preview_payload(
        prompt="I want a uniqueness rule for attribute customer_id",
        search_scope="all_across_workspaces",
        current_workspace_id="retail-banking",
        accessible_workspace_ids=accessible_workspace_ids,
        catalog_repository=preview_catalog_repository,
    )

    draft_payload = build_natural_language_rule_draft_suggestion_payload(
        prompt="  I want a uniqueness rule for attribute customer_id  ",
        search_scope="all_across_workspaces",
        current_workspace_id="retail-banking",
        selected_attribute_ids=["attr-retail-customer-id"],
        preview_payload=preview_payload,
    )

    assert draft_payload["data_source_id"] == "nl-preview:retail-banking"
    assert draft_payload["rule_type"] == "UNIQUENESS"
    assert draft_payload["confidence_score"] == 0.99
    assert draft_payload["reason"] == "Natural-language draft created from all_across_workspaces scope after steward confirmation."
    assert draft_payload["suggested_rule"]["selected_attribute_ids"] == ["attr-retail-customer-id"]
    assert draft_payload["suggested_rule"]["selected_attributes"][0]["parent_path"] == ["Retail Banking", "Customer Records", "customer_master"]
    assert draft_payload["suggested_rule"]["parent_context_snapshot"][0] == {
        "attribute_id": "attr-retail-customer-id",
        "workspace_id": "retail-banking",
        "parent_path": ["Retail Banking", "Customer Records", "customer_master"],
        "data_object_id": "object-retail",
        "data_object_name": "customer_master",
        "data_set_id": "dataset-retail",
        "data_set_name": "Customer Records",
        "data_product_id": "product-retail",
        "data_product_name": "Retail Banking",
        "current_context": True,
    }
    assert draft_payload["suggested_rule"]["draft_summary"] == "Uniqueness draft"
    assert draft_payload["suggested_rule"]["prompt"] == "I want a uniqueness rule for attribute customer_id"
    assert draft_payload["suggested_rule"]["original_prompt_text"] == "  I want a uniqueness rule for attribute customer_id  "


def test_build_natural_language_rule_draft_suggestion_payload_rejects_multi_object_selection(
    preview_catalog_repository: _PreviewCatalogRepository,
    accessible_workspace_ids: set[str],
) -> None:
    preview_payload = build_natural_language_rule_preview_payload(
        prompt="I want a uniqueness rule for attribute customer_id",
        search_scope="all_across_workspaces",
        current_workspace_id="retail-banking",
        accessible_workspace_ids=accessible_workspace_ids,
        catalog_repository=preview_catalog_repository,
    )

    with pytest.raises(ValueError, match="same data object version"):
        build_natural_language_rule_draft_suggestion_payload(
            prompt="I want a uniqueness rule for attribute customer_id",
            search_scope="all_across_workspaces",
            current_workspace_id="retail-banking",
            selected_attribute_ids=["attr-retail-customer-id", "attr-corporate-customer-id"],
            preview_payload=preview_payload,
        )


def test_build_natural_language_rule_preview_payload_rejects_unsupported_check_type(
    preview_catalog_repository: _PreviewCatalogRepository,
    accessible_workspace_ids: set[str],
) -> None:
    with pytest.raises(ValueError, match="supports uniqueness, present, regex, range, allowlist, and freshness checks only"):
        build_natural_language_rule_preview_payload(
            prompt="Please review this record",
            search_scope="all",
            current_workspace_id="retail-banking",
            accessible_workspace_ids=accessible_workspace_ids,
            catalog_repository=preview_catalog_repository,
        )


def test_build_natural_language_rule_preview_payload_rejects_unauthorized_cross_workspace_scope(
    preview_catalog_repository: _PreviewCatalogRepository,
    single_workspace_ids: set[str],
) -> None:
    with pytest.raises(PermissionError, match="Cross-workspace attribute search is not available for this user"):
        build_natural_language_rule_preview_payload(
            prompt="I want a uniqueness rule for attribute customer_id",
            search_scope="all_across_workspaces",
            current_workspace_id="retail-banking",
            accessible_workspace_ids=single_workspace_ids,
            catalog_repository=preview_catalog_repository,
        )


def test_build_natural_language_rule_preview_payload_for_provider_uses_llm_context(
    monkeypatch: pytest.MonkeyPatch,
    preview_catalog_repository: _PreviewCatalogRepository,
    accessible_workspace_ids: set[str],
) -> None:
    async def _fake_fetch_llm_rules(*, prompt: str, llm_service_url: str) -> list[str]:
        assert prompt == "Please make this a uniqueness rule"
        assert llm_service_url == "https://dq-made-easy-llm:8000"
        return ["customer_id"]

    monkeypatch.setattr(
        "app.application.services.natural_language_rule_drafting.fetch_llm_rules",
        _fake_fetch_llm_rules,
    )

    payload = asyncio.run(
        build_natural_language_rule_preview_payload_for_provider(
            prompt="Please make this a uniqueness rule",
            search_scope="current",
            current_workspace_id="retail-banking",
            accessible_workspace_ids=accessible_workspace_ids,
            catalog_repository=preview_catalog_repository,
            analysis_provider="llm",
            llm_service_url="https://dq-made-easy-llm:8000",
        )
    )

    assert payload["target_terms"] == ["customer_id"]
    assert payload["candidate_attributes"][0]["attribute_id"] == "attr-retail-customer-id"


def test_fetch_llm_rules_uses_a_user_facing_unavailable_message(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_text("dummy ca bundle\n", encoding="utf-8")
    monkeypatch.setenv("DQ_LLM_CA_BUNDLE", str(ca_bundle))

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def post(self, *args, **kwargs):
            del args, kwargs
            raise httpx.RequestError(
                "connect failed",
                request=httpx.Request("POST", "https://dq-made-easy-llm:8000/extract_rules"),
            )

    monkeypatch.setattr(
        "app.application.services.natural_language_rule_drafting.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    with pytest.raises(
        Exception,
        match="The AI analysis service is unavailable right now. Try the local analysis engine or again later.",
    ):
        asyncio.run(
            __import__("app.application.services.natural_language_rule_drafting", fromlist=["fetch_llm_rules"]).fetch_llm_rules(
                prompt="Please make this a uniqueness rule",
                llm_service_url="https://dq-made-easy-llm:8000",
            )
        )
