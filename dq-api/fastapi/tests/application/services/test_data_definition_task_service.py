from __future__ import annotations

import pytest

from app.application.services.data_definition_task_service import apply_board_approval_to_result
from app.application.services.data_definition_task_service import build_data_definition_generation_request
from app.application.services.data_definition_task_service import DataDefinitionTaskError
from app.application.services.data_definition_task_service import data_definition_llm_timeout_seconds
from app.application.services.data_definition_task_service import merge_import_result
from app.application.services.data_definition_task_service import require_approved_openmetadata_import_contract
from app.application.services.data_definition_task_service import validate_data_definition_task_result
from app.domain.entities.data_catalog import AttributeCatalogEntity
from app.domain.entities.data_catalog import DataObjectCatalogEntity
from app.domain.entities.data_catalog import DataObjectVersionEntity
from app.domain.entities.data_catalog import DataProductEntity
from app.domain.entities.data_catalog import DataSetEntity


class FakeCatalogRepository:
    def list_data_products(self, workspace: str | None = None) -> list[DataProductEntity]:
        products = [DataProductEntity(id="product-1", name="Finance", workspace_id="workspace-1")]
        if workspace is None:
            return products
        return [item for item in products if item.workspace_id == workspace]

    def list_data_objects(self) -> list:
        return []

    def list_data_sets(self, product_id: str | None = None, workspace: str | None = None) -> list[DataSetEntity]:
        return [DataSetEntity(id="dataset-1", product_id="product-1", name="Retail Loans", workspace_id="workspace-1")]

    def list_rule_attributes(self) -> list:
        return []

    def add_rule_attributes(self, entries: list[dict]):
        raise NotImplementedError()

    def get_attribute_rule_counts(self) -> dict[str, int]:
        return {}

    def list_data_objects_catalog(self, data_set_id: str | None = None) -> list[DataObjectCatalogEntity]:
        return [DataObjectCatalogEntity(id="object-1", dataset_id="dataset-1", name="Facility")]

    def get_attribute_catalog(self, attribute_id: str):
        return None

    def list_data_object_versions(self, object_id: str | None = None) -> list[DataObjectVersionEntity]:
        return [DataObjectVersionEntity(id="version-1", data_object_id="object-1", version=3, storage_uri="s3://bucket/facility", storage_format="parquet")]

    def get_data_object_version(self, version_id: str) -> DataObjectVersionEntity | None:
        if version_id != "version-1":
            return None
        return DataObjectVersionEntity(id="version-1", data_object_id="object-1", version=3, storage_uri="s3://bucket/facility", storage_format="parquet")

    def list_attributes_catalog(self, version_id: str | None = None) -> list[AttributeCatalogEntity]:
        return [
            AttributeCatalogEntity(
                id="attr-1",
                name="facility_id",
                type="string",
                nullable=False,
                version_id="version-1",
                definition_id="def.existing.facility_id",
                definition_mapping_status="explicit",
                is_primary_key=True,
                is_cde=True,
                masking_method="tokenize",
                encryption_required=True,
            ),
            AttributeCatalogEntity(
                id="attr-2",
                name="booking_country",
                type="string",
                nullable=True,
                version_id="version-1",
                definition_mapping_status="unmapped",
            ),
        ]

    def list_attribute_definition_mappings(self, version_id: str | None = None, attribute_id: str | None = None) -> list:
        return []

    def upsert_attribute_definition_mapping(self, *, attribute_id: str, definition_id: str | None, mapping_state: str, mapped_by: str | None):
        raise NotImplementedError()

    def upsert_attribute_protection_policy(self, *, attribute_id: str, masking_method: str, encryption_required: bool, encryption_key_id: str | None, configured_by: str | None):
        raise NotImplementedError()

    def list_data_deliveries(self, version_id: str | None = None, workspace: str | None = None) -> list:
        return []

    def get_data_delivery_note(self, delivery_id: str):
        return None

    def create_materialized_delivery_note(self, payload: dict):
        raise NotImplementedError()


def _definition_payload(**overrides) -> dict:
    payload = {
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
    payload.update(overrides)
    return payload


def _openmetadata_term_payload(**overrides) -> dict:
    extension = {
        "concept_key": "def.attribute.retail_loans.facility.facility_id",
        "definition_id": "def.attribute.retail_loans.facility.facility_id",
        "target_id": "attr-1",
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
        "provenance": "{}",
    }
    extension.update(overrides.pop("extension", {}))
    payload = {
        "name": "def_attribute_retail_loans_facility_facility_id",
        "displayName": "Facility Identifier",
        "description": "An identifier that uniquely distinguishes a lending facility within the finance domain",
        "extension": extension,
    }
    payload.update(overrides)
    return payload


def test_build_data_definition_generation_request_uses_catalog_context() -> None:
    payload = build_data_definition_generation_request(
        task_payload={
            "task_id": "task-123",
            "current_workspace_id": "workspace-1",
            "version_id": "version-1",
            "selected_attribute_ids": ["attr-1", "attr-2"],
            "user_input": "Draft BCBS 239 aligned terms",
            "policies": ["Use ISO 11179 naming"],
        },
        catalog_repository=FakeCatalogRepository(),
    )

    assert payload["task_id"] == "task-123"
    assert payload["domain_name"] == "Finance"
    assert payload["policies"] == ["Use ISO 11179 naming"]
    assert [target["target_id"] for target in payload["targets"]] == ["attr-1", "attr-2"]
    assert payload["targets"][0]["metadata"]["definition_id"] == "def.existing.facility_id"
    assert payload["targets"][0]["metadata"]["encryption_required"] is True
    assert payload["targets"][0]["logical_path"] == "Finance/Retail Loans/Facility/v3/facility_id"


def test_data_definition_llm_timeout_uses_live_generation_budget(monkeypatch) -> None:
    monkeypatch.delenv("DQ_DATA_DEFINITION_LLM_TIMEOUT_SECONDS", raising=False)

    assert data_definition_llm_timeout_seconds() == 300.0


def test_data_definition_llm_timeout_requires_positive_number(monkeypatch) -> None:
    monkeypatch.setenv("DQ_DATA_DEFINITION_LLM_TIMEOUT_SECONDS", "0")

    with pytest.raises(DataDefinitionTaskError, match="must be a positive number"):
        data_definition_llm_timeout_seconds()


def test_apply_board_approval_to_result_promotes_contracts_to_approved() -> None:
    original_result = {
        "review_status": "pending_board_review",
        "board_review_packet": {"review_status": "pending_board_review", "decision_required": True},
        "registry_contract": {
            "definitions": [
                _definition_payload()
            ]
        },
        "openmetadata_import_contract": {
            "definitions_manifest": {
                "definitions": [
                    _definition_payload()
                ]
            },
            "glossary_terms": [
                _openmetadata_term_payload()
            ],
        },
    }

    updated = apply_board_approval_to_result(
        result=original_result,
        approval_payload={
            "board_name": "Data Definition Board",
            "status": "approved",
            "approver_name": "Jane Steward",
            "approval_notes": "Approved for import",
            "approved_at": "2026-05-26T15:00:00Z",
        },
    )

    assert updated["review_status"] == "approved"
    assert updated["board_review_packet"]["decision_required"] is False
    assert updated["registry_contract"]["definitions"][0]["status"] == "approved"
    assert updated["openmetadata_import_contract"]["definitions_manifest"]["definitions"][0]["status"] == "approved"
    assert updated["openmetadata_import_contract"]["glossary_terms"][0]["extension"]["status"] == "approved"
    assert original_result["review_status"] == "pending_board_review"


def test_validate_data_definition_task_result_rejects_guideline_violations() -> None:
    with pytest.raises(DataDefinitionTaskError, match="violates business term guidelines"):
        validate_data_definition_task_result(
            result={
                "registry_contract": {
                    "definitions": [
                        _definition_payload(
                            business_definition="Facility Identifier must be used to identify a lending facility."
                        )
                    ]
                }
            }
        )


def test_validate_data_definition_task_result_accepts_generated_contract_shapes() -> None:
    validate_data_definition_task_result(
        result={
            "registry_contract": {
                "definitions": [
                    _definition_payload()
                ]
            },
            "openmetadata_import_contract": {
                "definitions_manifest": {
                    "definitions": [
                        _definition_payload()
                    ]
                },
                "glossary_terms": [
                    _openmetadata_term_payload()
                ],
            },
        }
    )


def test_validate_data_definition_task_result_rejects_missing_governance_metadata() -> None:
    with pytest.raises(DataDefinitionTaskError, match="primary_domain is required"):
        validate_data_definition_task_result(
            result={
                "registry_contract": {
                    "definitions": [
                        _definition_payload(primary_domain="")
                    ]
                }
            }
        )


def test_validate_data_definition_task_result_rejects_duplicate_concepts() -> None:
    with pytest.raises(DataDefinitionTaskError, match="duplicate concept"):
        validate_data_definition_task_result(
            result={
                "registry_contract": {
                    "definitions": [
                        _definition_payload(target_id="attr-1"),
                        _definition_payload(target_id="attr-2"),
                    ]
                }
            }
        )


def test_require_approved_openmetadata_import_contract_returns_valid_contract() -> None:
    import_contract = {
        "definitions_manifest": {
            "definitions": [
                _definition_payload()
            ]
        },
        "glossary_terms": [
            _openmetadata_term_payload()
        ],
    }

    resolved = require_approved_openmetadata_import_contract(
        result={
            "review_status": "approved",
            "openmetadata_import_contract": import_contract,
        }
    )

    assert resolved is import_contract


def test_require_approved_openmetadata_import_contract_rejects_pending_review() -> None:
    with pytest.raises(DataDefinitionTaskError, match="Only approved tasks can be imported"):
        require_approved_openmetadata_import_contract(
            result={
                "review_status": "pending_board_review",
                "openmetadata_import_contract": {},
            }
        )


def test_merge_import_result_appends_import_trace() -> None:
    updated = merge_import_result(
        result={"orchestration_trace": []},
        import_report={"definition_count": 2},
    )

    assert updated["openmetadata_import_result"]["definition_count"] == 2
    assert updated["orchestration_trace"][-1]["name"] == "import_openmetadata_contract"