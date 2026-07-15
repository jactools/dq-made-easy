from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "dq-llm" / "entrypoint.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("dq_llm_entrypoint", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeChatClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._responses:
            raise AssertionError("No fake responses remaining")
        return self._responses.pop(0)


def test_generate_data_definitions_bundle_builds_openmetadata_contract() -> None:
    module = _load_module()
    request_model = module.DataDefinitionRequest(
        task_id="dd-task-001",
        steward_name="Jane Steward",
        board_name="Data Definition Board",
        domain_name="Retail Banking",
        source_system="core_banking",
        user_input="Draft a board-review-ready definition.",
        policies=["Support BCBS 239 traceability."],
        targets=[
            module.DefinitionTarget(
                data_set_name="credit_risk",
                data_object_name="customer_exposure",
                attribute_name="exposure_amount",
                data_type="decimal(18,2)",
                nullable=False,
                sample_values=["10500.00"],
                metadata={"regulatory_tags": ["bcbs239"], "sensitivity": "confidential"},
            )
        ],
        feedback_items=[
            module.ReviewFeedback(
                feedback_id="fb-001",
                source_role="data_definition_board",
                author_name="Board Reviewer",
                comment="Clarify that the amount is reportable exposure in EUR.",
                target_ids=["attr.credit_risk.customer_exposure.exposure_amount"],
            )
        ],
    )
    chat_client = FakeChatClient(
        [
            """
            {
              "definitions": [
                {
                  "target_id": "attr.credit_risk.customer_exposure.exposure_amount",
                  "definition_name": "Customer Exposure Amount",
                  "business_definition": "An amount representing reportable customer exposure within BCBS 239 reporting scope",
                  "synonyms": ["Exposure amount"],
                  "representation_term": "amount",
                  "value_domain": {"data_type": "decimal(18,2)", "nullable": false, "unit": "EUR"},
                  "examples": ["10500.00"],
                  "constraints": ["Value must be non-negative."],
                  "open_questions": ["Confirm whether contingent exposure is included."],
                  "board_notes": "Needs board confirmation on inclusion boundaries."
                }
              ],
              "board_review_summary": "Initial draft ready for board review.",
              "approval_criteria": ["Meaning and scope are explicit."]
            }
            """,
            """
            {
              "definitions": [
                {
                  "target_id": "attr.credit_risk.customer_exposure.exposure_amount",
                  "definition_name": "Customer Reportable Exposure Amount",
                  "business_definition": "An amount representing total EUR reportable customer exposure recognized within BCBS 239 reporting scope",
                  "synonyms": ["Exposure amount", "Reportable exposure"],
                  "representation_term": "amount",
                  "value_domain": {"data_type": "decimal(18,2)", "nullable": false, "unit": "EUR"},
                  "examples": ["10500.00"],
                  "constraints": ["Value must be non-negative."],
                  "open_questions": [],
                  "board_notes": "Board feedback incorporated."
                }
              ],
              "board_review_summary": "Board feedback has been incorporated into the revised draft.",
              "approval_criteria": ["Meaning and scope are explicit.", "Unit of measure is stated."]
            }
            """,
        ]
    )

    bundle = module.generate_data_definitions_bundle(
        request_model,
        chat_client,
        provider_name="huggingface",
        model_name="Qwen/Qwen2.5-7B-Instruct",
    )

    assert bundle["provider"] == "huggingface"
    assert bundle["model_name"] == "Qwen/Qwen2.5-7B-Instruct"
    assert bundle["review_status"] == "board_feedback_incorporated"
    assert len(chat_client.prompts) == 2
    definition = bundle["registry_contract"]["definitions"][0]
    assert definition["definition_id"] == (
        "def.attribute.credit_risk.customer_exposure.exposure_amount"
    )
    assert definition["business_definition"].startswith(
        "An amount representing total EUR reportable customer exposure"
    )
    assert definition["concept_key"] == "def.attribute.credit_risk.customer_exposure.exposure_amount"
    assert definition["primary_domain"] == "Retail Banking"
    assert definition["definition_owner"] == "Jane Steward"
    assert definition["homonym_context"] == {
        "primary_domain": "Retail Banking",
        "object_class": "customer_exposure",
        "property": "exposure_amount",
        "logical_path": "Retail Banking/credit_risk/customer_exposure/exposure_amount",
    }
    assert definition["source_references"][0]["logical_path"] == (
        "Retail Banking/credit_risk/customer_exposure/exposure_amount"
    )
    assert {policy["name"] for policy in definition["policy_documents"]} >= {
        "Guidelines for Definitions of Business Terms",
        "BCBS 239 Principles for Effective Risk Data Aggregation and Risk Reporting",
        "Support BCBS 239 traceability.",
    }
    extension = bundle["openmetadata_import_contract"]["glossary_terms"][0]["extension"]
    assert extension["definition_id"] == (
        "def.attribute.credit_risk.customer_exposure.exposure_amount"
    )
    assert extension["primary_domain"] == "Retail Banking"
    assert extension["definition_owner"] == "Jane Steward"
    assert json.loads(extension["homonym_context"])["property"] == "exposure_amount"
    assert json.loads(extension["source_references"])[0]["source_system"] == "core_banking"
    assert "homonym context" in chat_client.prompts[0]
    assert bundle["board_review_packet"]["approval_criteria"] == [
        "Meaning and scope are explicit.",
        "Unit of measure is stated.",
    ]


def test_generate_data_definitions_bundle_rejects_invalid_json() -> None:
    module = _load_module()
    request_model = module.DataDefinitionRequest(
        task_id="dd-task-002",
        targets=[
            module.DefinitionTarget(
                data_set_name="credit_risk",
                data_object_name="customer_exposure",
                attribute_name="exposure_amount",
            )
        ],
    )
    chat_client = FakeChatClient(["not-json"])

    with pytest.raises(module.LLMServiceResponseError, match="invalid JSON"):
        module.generate_data_definitions_bundle(
            request_model,
            chat_client,
            provider_name="huggingface",
            model_name="Qwen/Qwen2.5-7B-Instruct",
        )


def test_generate_data_definitions_bundle_requires_definition_for_each_target() -> None:
    module = _load_module()
    request_model = module.DataDefinitionRequest(
        task_id="dd-task-003",
        targets=[
            module.DefinitionTarget(
                data_set_name="credit_risk",
                data_object_name="customer_exposure",
                attribute_name="exposure_amount",
            ),
            module.DefinitionTarget(
                data_set_name="credit_risk",
                data_object_name="customer_exposure",
                attribute_name="exposure_currency",
            ),
        ],
    )
    chat_client = FakeChatClient(
        [
            """
            {
              "definitions": [
                {
                  "target_id": "attr.credit_risk.customer_exposure.exposure_amount",
                  "definition_name": "Exposure Amount",
                  "business_definition": "Amount of exposure."
                }
              ]
            }
            """
        ]
    )

    with pytest.raises(module.LLMServiceResponseError, match="missing required target_ids"):
        module.generate_data_definitions_bundle(
            request_model,
            chat_client,
            provider_name="huggingface",
            model_name="Qwen/Qwen2.5-7B-Instruct",
        )