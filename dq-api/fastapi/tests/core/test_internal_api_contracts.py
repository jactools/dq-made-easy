from __future__ import annotations

from pathlib import Path

import pytest

from dq_utils.internal_api_contracts import InternalApiContractRegistry
from dq_utils.internal_api_contracts import InternalApiContractValidationError


@pytest.fixture
def internal_api_contract_registry() -> InternalApiContractRegistry:
    repo_root = Path(__file__).resolve().parents[4]
    return InternalApiContractRegistry(repo_root / "docs" / "contracts" / "internal-api")


def test_internal_api_contract_registry_resolves_support_request_contract(
    internal_api_contract_registry: InternalApiContractRegistry,
) -> None:
    operation = internal_api_contract_registry.get_operation("POST", "/api/system/v1/support/requests")

    assert operation is not None
    assert operation.operation_id == "create_support_request_api_system_v1_support_requests_post"
    assert operation.request_body_required is True
    assert operation.request_body_schema_ref == "#/$defs/SupportRequestView"


def test_internal_api_contract_registry_resolves_master_data_contract(
    internal_api_contract_registry: InternalApiContractRegistry,
) -> None:
    operation = internal_api_contract_registry.get_operation("GET", "/api/master-data/v1/master-records")

    assert operation is not None
    assert operation.operation_id == "get_master_records_api_master_data_v1_master_records_get"
    assert operation.request_body_required is False


def test_internal_api_contract_registry_rejects_camel_case_test_payload(
    internal_api_contract_registry: InternalApiContractRegistry,
) -> None:
    with pytest.raises(InternalApiContractValidationError) as exc_info:
        internal_api_contract_registry.validate_request_payload(
            "POST",
            "/api/rulebuilder/v1/rules/{rule_id}/test-with-data",
            {"testData": [{"email": "valid@example.com"}]},
        )

    error = exc_info.value
    assert error.operation.operation_id == "test_rule_with_data_api_rulebuilder_v1_rules__rule_id__test_with_data_post"
    assert any(issue.message == "'test_data' is a required property" for issue in error.issues)
