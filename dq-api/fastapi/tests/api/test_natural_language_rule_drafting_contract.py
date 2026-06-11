from __future__ import annotations

from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguageDraftRulePreviewView
from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguageParsedConditionView
from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguagePreviewCandidateView
from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguageRulePreviewCreateSuggestionRequestView
from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguageRulePreviewRequestView
from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguageRulePreviewResponseView
from app.application.services.natural_language_rule_drafting import ResolvedCandidate
from app.application.services.natural_language_rule_drafting import build_preview_rule_dsl_v2_document
from app.application.services.natural_language_rule_drafting import serialize_candidate


def _build_candidate() -> ResolvedCandidate:
    return ResolvedCandidate(
        attribute_id="attr-retail-customer-id",
        attribute_name="customer_id",
        version_id="version-retail",
        data_object_id="object-retail",
        data_object_name="customer_master",
        data_set_id="dataset-retail",
        data_set_name="Retail Core",
        data_product_id="product-retail",
        data_product_name="Customer",
        workspace_id="retail-banking",
        parent_path=["Customer", "Retail Core", "customer_master"],
        confidence_score=0.92,
        match_reasons=["Exact attribute-name match"],
        current_context=True,
        match_roles=["target"],
    )


def test_natural_language_rule_preview_contract_serializes_snake_case() -> None:
    request = NaturalLanguageRulePreviewRequestView.model_validate(
        {
            "prompt": "I want a uniqueness rule for attribute customer_id",
            "search_scope": "current",
            "current_workspace_id": "retail-banking",
            "analysis_provider": "llm",
        }
    )
    create_request = NaturalLanguageRulePreviewCreateSuggestionRequestView.model_validate(
        {
            "prompt": "I want a uniqueness rule for attribute customer_id",
            "search_scope": "current",
            "current_workspace_id": "retail-banking",
            "selected_attribute_ids": ["attr-retail-customer-id"],
            "analysis_provider": "llm",
        }
    )

    candidate = _build_candidate()
    preview = NaturalLanguageRulePreviewResponseView.model_validate(
        {
            "success": True,
            "target_terms": ["customer_id"],
            "search_scope": "current",
            "candidate_attributes": [serialize_candidate(candidate)],
            "parsed_condition": None,
            "requires_steward_confirmation": True,
            "draft_rule_preview": {
                "name": "Uniqueness draft for customer_id",
                "workspace_id": "retail-banking",
                "dimension": "Uniqueness",
                "summary": "Select one or more candidate attributes to create a uniqueness draft suggestion.",
                "dsl": build_preview_rule_dsl_v2_document(
                    prompt="I want a uniqueness rule for attribute customer_id",
                    check_type="UNIQUENESS",
                    selected_candidates=[candidate],
                ),
            },
        }
    )

    assert request.model_dump(by_alias=True, mode="json") == {
        "prompt": "I want a uniqueness rule for attribute customer_id",
        "search_scope": "current",
        "current_workspace_id": "retail-banking",
        "analysis_provider": "llm",
    }
    assert create_request.model_dump(by_alias=True, mode="json") == {
        "prompt": "I want a uniqueness rule for attribute customer_id",
        "search_scope": "current",
        "current_workspace_id": "retail-banking",
        "selected_attribute_ids": ["attr-retail-customer-id"],
        "analysis_provider": "llm",
    }

    preview_payload = preview.model_dump(by_alias=True, mode="json")
    assert preview_payload["success"] is True
    assert preview_payload["target_terms"] == ["customer_id"]
    assert preview_payload["search_scope"] == "current"
    assert preview_payload["candidate_attributes"][0]["attribute_id"] == "attr-retail-customer-id"
    assert preview_payload["candidate_attributes"][0]["match_roles"] == ["target"]
    assert preview_payload["parsed_condition"] is None
    assert preview_payload["requires_steward_confirmation"] is True
    assert preview_payload["draft_rule_preview"]["workspace_id"] == "retail-banking"
    assert preview_payload["draft_rule_preview"]["dsl"]["schema_version"] == "2.0.0"
    assert preview_payload["draft_rule_preview"]["dsl"]["rule"]["kind"] == "metric_threshold"


def test_natural_language_rule_preview_condition_model_uses_snake_case() -> None:
    condition = NaturalLanguageParsedConditionView.model_validate(
        {
            "attribute_term": "status",
            "operator": "equals",
            "value": "active",
            "same_version_required": True,
        }
    )
    candidate = NaturalLanguagePreviewCandidateView.model_validate(serialize_candidate(_build_candidate()))
    draft = NaturalLanguageDraftRulePreviewView.model_validate(
        {
            "name": "Format / Regex draft for email",
            "workspace_id": "retail-banking",
            "dimension": "Validity",
            "summary": "Conditional format / regex draft",
            "dsl": build_preview_rule_dsl_v2_document(
                prompt="When a customer is active, a valid email address must be filled in",
                check_type="REGEX",
                selected_candidates=[_build_candidate()],
            ),
        }
    )

    preview = NaturalLanguageRulePreviewResponseView.model_validate(
        {
            "success": True,
            "target_terms": ["email"],
            "search_scope": "all_across_workspaces",
            "candidate_attributes": [candidate.model_dump(by_alias=True, mode="json")],
            "parsed_condition": condition.model_dump(by_alias=True, mode="json"),
            "requires_steward_confirmation": True,
            "draft_rule_preview": draft.model_dump(by_alias=True, mode="json"),
        }
    )

    assert preview.model_dump(by_alias=True, mode="json")["parsed_condition"] == {
        "attribute_term": "status",
        "operator": "equals",
        "value": "active",
        "same_version_required": True,
    }
