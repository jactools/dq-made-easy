from __future__ import annotations

from fastapi.testclient import TestClient


def test_internal_api_contract_validation_rejects_camel_case_request_keys(
    client: TestClient,
    auth_headers: callable,
) -> None:
    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test-with-data",
        headers=auth_headers("dq:rules:test"),
        json={"testData": [{"email": "valid@example.com"}]},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"]["error"] == "contract_schema_validation_failed"
    assert payload["detail"]["path"] == "/api/rulebuilder/v1/rules/{rule_id}/test-with-data"
    assert payload["detail"]["operation_id"] == "test_rule_with_data_api_rulebuilder_v1_rules__rule_id__test_with_data_post"
    assert any(
        issue["message"] == "'test_data' is a required property"
        for issue in payload["detail"]["validation_errors"]
    )


def test_internal_api_contract_validation_rejects_invalid_json_payload(
    client: TestClient,
    auth_headers: callable,
) -> None:
    response = client.post(
        "/api/system/v1/support/requests",
        headers={
            **auth_headers("dq:rules:read", email="admin@example.com"),
            "Content-Type": "application/json",
        },
        content='{"title": "broken"',
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["error"] == "invalid_json_payload"
    assert payload["detail"]["path"] == "/api/system/v1/support/requests"
    assert payload["detail"]["operation_id"] == "create_support_request_api_system_v1_support_requests_post"


def test_internal_api_contract_validation_rejects_json_body_without_request_schema(
    client: TestClient,
    auth_headers: callable,
) -> None:
    response = client.post(
        "/api/admin/v1/rules/rule-email-format/recover",
        headers=auth_headers("dq:users:manage"),
        json={"unexpected": True},
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["detail"]["error"] == "internal_api_contract_missing_request_schema"
    assert payload["detail"]["path"] == "/api/admin/v1/rules/{rule_id}/recover"
    assert payload["detail"]["operation_id"] == "recover_removed_rule_api_admin_v1_rules__rule_id__recover_post"
