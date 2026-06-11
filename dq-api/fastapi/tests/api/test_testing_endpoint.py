from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.api.v1 import testing_data_requests_api
from app.domain.entities import rule_testing_context as testing_context
from app.core.config import get_settings
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_testing_repository
from app.infrastructure.repositories.in_memory_data_catalog_repository import InMemoryDataCatalogRepository
from app.infrastructure.repositories.in_memory_rules_repository import InMemoryRulesRepository
from app.infrastructure.repositories.in_memory_testing_repository import InMemoryTestingRepository
from app.main import app

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("clone_payload")


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
    return {
        "Authorization": f"Bearer {token}",
        "X-Kong-Request-Id": "test-request-id",
    }


def _queued_test_data_result(version_id: str, sample_count: int) -> dict[str, object]:
    return {
        "request_id": "tdr-test-1",
        "job_id": "tdj-test-1",
        "status": "completed",
        "target_type": "data_object_version",
        "target_id": version_id,
        "sample_count": sample_count,
        "requested_at": "2026-04-05T12:00:00Z",
        "started_at": "2026-04-05T12:00:01Z",
        "completed_at": "2026-04-05T12:00:02Z",
        "error_message": None,
        "correlation_id": "corr-test-1",
        "result": {
            "version_id": version_id,
            "version_name": 1,
            "data_object_id": "do-1",
            "attribute_count": 1,
            "sample_count": sample_count,
            "samples": [{"email": f"user{i + 1}@example.com"} for i in range(sample_count)],
            "attributes": [{"name": "email", "type": "text", "nullable": True, "format": "", "is_primary_key": False}],
            "generated_at": "2026-04-05T12:00:02Z",
        },
    }


async def _compiled_execution_context(*_args, **_kwargs) -> dict[str, object]:
    return {
        "ruleId": "rule-email-format",
        "ruleVersionId": "rv-email-1",
        "ruleVersionNumber": 1,
        "sourceRuleExpression": "email contains '@'",
        "artifactKey": "artifact-email-1",
        "compilerVersion": "dq-7.3.0",
        "compilerRevision": 1,
        "compileStatus": "compiled",
        "schemaVersion": "1",
        "executionContract": {"engineTarget": "dq-engine"},
        "compiledExpression": "email contains '@'",
        "handoffReady": True,
    }


def setup_module() -> None:
    get_settings.cache_clear()


def teardown_module() -> None:
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_testing_dependencies() -> None:
    testing_repository = InMemoryTestingRepository()
    rules_repository = InMemoryRulesRepository()
    data_catalog_repository = InMemoryDataCatalogRepository()

    app.dependency_overrides[get_testing_repository] = lambda: testing_repository
    app.dependency_overrides[get_rules_repository] = lambda: rules_repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: data_catalog_repository

    yield

    app.dependency_overrides.pop(get_testing_repository, None)
    app.dependency_overrides.pop(get_rules_repository, None)
    app.dependency_overrides.pop(get_data_catalog_repository, None)


def test_batch_test_requests_requires_test_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get("/api/rulebuilder/v1/batch-test-requests")

    assert response.status_code == 401


def test_batch_test_requests_list_returns_seeded_rows(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/rulebuilder/v1/batch-test-requests?page=1&limit=10",
        headers=_auth_headers("dq:rules:test"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["data"], list)
    assert len(payload["data"]) >= 1
    assert payload["pagination"]["total"] >= 1
    assert payload["pagination"]["page"] == 1
    assert payload["pagination"]["limit"] == 10


def test_batch_test_request_by_id_defaults_to_null(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get("/rulebuilder/v1/batch-test-requests/test-123", headers=_auth_headers("dq:rules:test"))

    assert response.status_code == 200
    assert response.json() is None


def test_create_batch_test_request_returns_items(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/batch-test-requests",
        headers=_auth_headers("dq:rules:test"),
        json={
            "rule_ids": ["rule-email-format", "rule-phone-format"],
            "requested_by": "qa-user",
            "workspace": "retail-banking",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["status"] == "pending"
    assert payload[0]["requested_by"] == "qa-user"


def test_create_batch_test_request_requires_test_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/batch-test-requests",
        headers=_auth_headers("dq:rules:read"),
        json={"rule_ids": ["rule-email-format"]},
    )

    assert response.status_code == 403


def test_run_batch_test_request_returns_running_status(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/batch-test-requests/test-123/run",
        headers=_auth_headers("dq:rules:test"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "test-123"
    assert payload["status"] == "running"
    assert payload["execution_context"] is None


def test_run_batch_test_request_includes_scheduler_handoff_for_existing_request(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()
    monkeypatch.setattr(testing_context, "build_execution_context", _compiled_execution_context)

    create_response = client.post(
        "/api/rulebuilder/v1/batch-test-requests",
        headers=_auth_headers("dq:rules:test"),
        json={"rule_ids": ["rule-email-format"]},
    )
    assert create_response.status_code == 200
    request_id = create_response.json()[0]["id"]

    run_response = client.post(
        f"/api/rulebuilder/v1/batch-test-requests/{request_id}/run",
        headers=_auth_headers("dq:rules:test"),
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["id"] == request_id
    assert payload["status"] == "completed"
    assert isinstance(payload["execution_context"], dict)
    assert payload["execution_context"]["correlation_id"]
    assert isinstance(payload["execution_context"]["scheduler_handoff"], dict)
    assert payload["execution_context"]["scheduler_handoff"]["correlation_id"]
    assert payload["execution_context"]["scheduler_handoff"]["correlation_id"] == payload["execution_context"]["correlation_id"]
    assert payload["execution_context"]["scheduler_handoff"]["batch_request_id"] == request_id
    assert payload["execution_context"]["scheduler_handoff"]["handoff_status"] == "accepted"
    assert payload["execution_context"]["scheduler_handoff"]["executor_target"] == "dq-engine"
    assert payload["execution_context"]["scheduler_handoff"]["handoff_id"]
    assert payload["execution_context"]["scheduler_handoff"]["submitted_at"]

    get_response = client.get(
        f"/api/rulebuilder/v1/batch-test-requests/{request_id}",
        headers=_auth_headers("dq:rules:test"),
    )
    assert get_response.status_code == 200
    assert get_response.json()["execution_correlation_id"] == payload["execution_context"]["correlation_id"]


def test_run_batch_test_request_persists_running_status_for_existing_request(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()
    monkeypatch.setattr(testing_context, "build_execution_context", _compiled_execution_context)

    create_response = client.post(
        "/api/rulebuilder/v1/batch-test-requests",
        headers=_auth_headers("dq:rules:test"),
        json={"rule_ids": ["rule-email-format"]},
    )
    assert create_response.status_code == 200
    request_id = create_response.json()[0]["id"]

    run_response = client.post(
        f"/api/rulebuilder/v1/batch-test-requests/{request_id}/run",
        headers=_auth_headers("dq:rules:test"),
    )
    assert run_response.status_code == 200

    get_response = client.get(
        f"/api/rulebuilder/v1/batch-test-requests/{request_id}",
        headers=_auth_headers("dq:rules:test"),
    )
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "completed"
    assert get_response.json()["completed_at"]
    assert get_response.json()["proof_id"]
    assert get_response.json()["execution_correlation_id"]


def test_run_batch_test_request_persists_failed_status_for_forced_failure(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()
    monkeypatch.setattr(testing_context, "build_execution_context", _compiled_execution_context)

    def _boom(self, rule_id: str, version_id: str, sample_count: int = 10, compiled_expression=None):
        raise RuntimeError("executor offline")

    monkeypatch.setattr(InMemoryTestingRepository, "run_rule_with_generated_data", _boom)

    create_response = client.post(
        "/api/rulebuilder/v1/batch-test-requests",
        headers=_auth_headers("dq:rules:test"),
        json={"rule_ids": ["rule-email-format"]},
    )
    assert create_response.status_code == 200
    request_id = create_response.json()[0]["id"]

    run_response = client.post(
        f"/api/rulebuilder/v1/batch-test-requests/{request_id}/run",
        headers=_auth_headers("dq:rules:test"),
    )
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "failed"

    get_response = client.get(
        f"/api/rulebuilder/v1/batch-test-requests/{request_id}",
        headers=_auth_headers("dq:rules:test"),
    )
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["status"] == "failed"
    assert payload["completed_at"]
    assert payload["proof_id"] is None
    assert payload["test_data_config"]["execution_failure"]["reason"] == "executor-runtime-error"
    assert payload["test_data_config"]["execution_failure"]["error_type"] == "RuntimeError"
    assert payload["test_data_config"]["execution_failure"]["error_code"] == "EXECUTOR_RUNTIME_ERROR"
    assert payload["test_data_config"]["execution_failure"]["correlation_id"]
    assert payload["execution_correlation_id"] == payload["test_data_config"]["execution_failure"]["correlation_id"]


def test_run_batch_test_request_requires_test_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/batch-test-requests/test-123/run",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 403


def test_generate_test_data_for_version_returns_payload(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    async def _enqueue(**_kwargs):
        return {"request_id": "tdr-test-1"}

    async def _wait(_request_id: str):
        return _queued_test_data_result("dov-23", 2)

    monkeypatch.setattr(testing_data_requests_api, "bind_queued_test_data_request_enqueuer", lambda _request: _enqueue)
    monkeypatch.setattr(testing_data_requests_api, "wait_for_test_data_request_result", _wait)

    response = client.post(
        "/api/rulebuilder/v1/data-object-versions/dov-23/generate-test-data",
        headers=_auth_headers("dq:rules:test"),
        json={"sample_count": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["version_id"] == "dov-23"
    assert payload["sample_count"] == 2
    assert len(payload["samples"]) == 2


def test_test_data_request_events_stream_terminal_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    async def _read_record(_redis_url: str, _request_id: str):
        return _queued_test_data_result("dov-23", 2)

    monkeypatch.setattr(testing_data_requests_api, "resolve_test_data_redis_url", lambda: "redis://queue")
    monkeypatch.setattr(testing_data_requests_api, "read_test_data_request_record", _read_record)

    response = client.get(
        "/api/rulebuilder/v1/test-data/requests/tdr-test-1/events",
        headers=_auth_headers("dq:rules:test"),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: snapshot" in response.text
    assert '"request_id":"tdr-test-1"' in response.text
    assert '"status":"completed"' in response.text


def test_test_data_materialization_events_stream_terminal_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    record = {
        "request_id": "tdm-test-1",
        "job_id": "tdmj-test-1",
        "request_contract": None,
        "status": "completed",
        "data_object_version_id": "dov-23",
        "target_data_object_version_ids": ["dov-23"],
        "sample_count": 10,
        "output_format": "parquet",
        "output_uri": "s3a://dq-test-data/dov-23",
        "requested_at": "2026-04-05T12:00:00Z",
        "started_at": "2026-04-05T12:00:01Z",
        "completed_at": "2026-04-05T12:00:02Z",
        "error_message": None,
        "correlation_id": "corr-test-1",
        "queue_key": "queue:test-data-materialization",
        "processing_queue_key": "queue:test-data-materialization:processing",
        "selection": None,
        "result": {"row_count": 10},
    }

    async def _read_record(_redis_url: str, _request_id: str):
        return record

    monkeypatch.setattr(testing_data_requests_api, "resolve_test_data_redis_url", lambda: "redis://queue")
    monkeypatch.setattr(testing_data_requests_api, "read_test_data_materialization_record", _read_record)

    response = client.get(
        "/api/rulebuilder/v1/test-data/materializations/tdm-test-1/events",
        headers=_auth_headers("dq:rules:test"),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: snapshot" in response.text
    assert '"request_id":"tdm-test-1"' in response.text
    assert '"status":"completed"' in response.text


def test_generate_test_data_for_version_requires_test_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/data-object-versions/dov-23/generate-test-data",
        headers=_auth_headers("dq:rules:read"),
        json={"sample_count": 2},
    )

    assert response.status_code == 403


def test_test_rule_with_data_returns_execution_summary(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    monkeypatch.setattr(testing_context, "build_execution_context", _compiled_execution_context)

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test-with-data",
        headers=_auth_headers("dq:rules:test"),
        json={
            "test_data": [
                {"email": "valid@example.com"},
                {"email": "invalid_email"},
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rule_id"] == "rule-email-format"
    assert payload["total_tests"] == 2
    assert payload["passed_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["execution_context"]["rule_id"] == "rule-email-format"
    assert payload["execution_context"]["rule_version_id"]
    assert payload["execution_context"]["rule_version_number"] >= 1
    assert payload["execution_context"]["source_rule_expression"] == "email contains '@'"
    assert payload["execution_context"]["executed_expression"] == payload["expression"]
    assert payload["execution_context"]["handoff_ready"] is True
    assert payload["execution_context"]["executed_expression_source"] == "compiled-artifact"


def test_test_rule_with_data_prefers_compiled_artifact_after_validate(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    monkeypatch.setattr(testing_context, "build_execution_context", _compiled_execution_context)

    run_response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test-with-data",
        headers=_auth_headers("dq:rules:test"),
        json={
            "test_data": [
                {"email": "valid@example.com"},
                {"email": "invalid_email"},
            ]
        },
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["execution_context"]["handoff_ready"] is True
    assert payload["execution_context"]["compiled_expression"]
    assert payload["execution_context"]["source_rule_expression"] == "email contains '@'"
    assert payload["execution_context"]["executed_expression"] == payload["expression"]
    assert payload["execution_context"]["executed_expression_source"] == "compiled-artifact"


def test_test_rule_with_data_requires_test_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test-with-data",
        headers=_auth_headers("dq:rules:read"),
        json={"test_data": [{"email": "valid@example.com"}]},
    )

    assert response.status_code == 403


def test_log_test_action_returns_proof_payload(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    monkeypatch.setattr(testing_context, "build_execution_context", _compiled_execution_context)

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test",
        headers=_auth_headers("dq:rules:test"),
        json={
            "coverage": 0.95,
            "passed": True,
            "records_tested_count": 100,
            "failures_found": 5,
            "proof_data": {"suite": "smoke"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rule_id"] == "rule-email-format"
    assert payload["records_tested_count"] == 100
    assert payload["failures_found"] == 5
    assert payload["success_rate"] == 95.0
    assert payload["proof_data"]["execution_trace"]["execution_id"]
    assert payload["proof_data"]["execution_trace"]["correlation_id"]
    assert payload["proof_data"]["execution_trace"]["result_status"] == "passed"
    assert "artifact_key" in payload["proof_data"]["execution_trace"]
    assert payload["execution_context"]["source_rule_expression"] == "email contains '@'"
    assert payload["execution_trace"]["execution_id"]
    assert payload["execution_trace"]["correlation_id"]
    assert payload["execution_trace"]["result_status"] == "passed"


def test_log_test_action_requires_test_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test",
        headers=_auth_headers("dq:rules:read"),
        json={
            "coverage": 0.95,
            "passed": True,
            "records_tested_count": 100,
            "failures_found": 5,
        },
    )

    assert response.status_code == 403


def test_test_rule_with_generated_data_returns_execution_summary(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    async def _enqueue(**_kwargs):
        return {"request_id": "tdr-test-2"}

    async def _wait(_request_id: str):
        return _queued_test_data_result("dov-23", 3)

    monkeypatch.setattr(testing_data_requests_api, "bind_queued_test_data_request_enqueuer", lambda _request: _enqueue)
    monkeypatch.setattr(testing_data_requests_api, "wait_for_test_data_request_result", _wait)
    monkeypatch.setattr(testing_context, "build_execution_context", _compiled_execution_context)

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test-with-generated-data",
        headers=_auth_headers("dq:rules:test"),
        json={"version_id": "dov-23", "sample_count": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rule_id"] == "rule-email-format"
    assert payload["test_data_source"] == "dov-23"
    assert payload["total_tests"] == 3
    assert payload["stored_proof"]["status"] == ("passed" if payload["rule_passed"] else "failed")
    assert payload["stored_proof"]["proof_data"]["data_object_name"] == "Contact"
    assert payload["stored_proof"]["proof_data"]["version_name"] == 3
    assert payload["stored_proof"]["execution_context"]["source_rule_expression"] == "email contains '@'"
    assert payload["execution_context"]["executed_expression_source"] == "compiled-artifact"


def test_start_rule_test_with_generated_data_persists_pending_proof(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    monkeypatch.setattr(testing_context, "build_execution_context", _compiled_execution_context)

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test-runs/start",
        headers=_auth_headers("dq:rules:test"),
        json={"version_id": "dov-23", "sample_count": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["proof_data"]["request_status"] == "pending"

    proofs_response = client.get(
        "/api/rulebuilder/v1/test-proofs/rule-email-format",
        headers=_auth_headers("dq:rules:test"),
    )

    assert proofs_response.status_code == 200
    proof = next((row for row in proofs_response.json() if row["id"] == payload["id"]), None)
    assert proof is not None
    assert proof["status"] == "pending"


def test_test_rule_with_generated_data_persists_failed_proof_when_generation_times_out(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    async def _enqueue(**_kwargs):
        return {"request_id": "tdr-timeout-1", "correlation_id": "corr-timeout-1"}

    async def _wait(_request_id: str):
        raise HTTPException(status_code=504, detail="Timed out waiting for queued test data generation")

    monkeypatch.setattr(testing_data_requests_api, "bind_queued_test_data_request_enqueuer", lambda _request: _enqueue)
    monkeypatch.setattr(testing_data_requests_api, "wait_for_test_data_request_result", _wait)
    monkeypatch.setattr(testing_context, "build_execution_context", _compiled_execution_context)

    start_response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test-runs/start",
        headers=_auth_headers("dq:rules:test"),
        json={"version_id": "dov-23", "sample_count": 3},
    )

    assert start_response.status_code == 200
    started_proof_id = start_response.json()["id"]

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test-with-generated-data",
        headers=_auth_headers("dq:rules:test"),
        json={"version_id": "dov-23", "sample_count": 3, "proof_id": started_proof_id},
    )

    assert response.status_code == 504
    payload = response.json()
    assert payload["detail"]["message"] == "Timed out waiting for queued test data generation"
    assert payload["detail"]["proof_id"] == started_proof_id

    proofs_response = client.get(
        "/api/rulebuilder/v1/test-proofs/rule-email-format",
        headers=_auth_headers("dq:rules:test"),
    )

    assert proofs_response.status_code == 200
    proof = next((row for row in proofs_response.json() if row["id"] == payload["detail"]["proof_id"]), None)
    assert proof is not None
    assert proof["status"] == "failed"
    assert proof["records_tested_count"] == 0
    assert proof["proof_data"]["error"] == "Timed out waiting for queued test data generation"
    assert proof["execution_trace"]["result_status"] == "failed"


def test_start_rule_test_with_generated_data_fails_when_active_compiler_artifact_missing(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    async def _missing_context(*_args, **_kwargs):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "active_compiler_artifact_required",
                "message": "An active compiler artifact with a compiled expression is required before testing this rule. Validate the current rule version and try again.",
            },
        )

    monkeypatch.setattr(testing_context, "build_execution_context", _missing_context)

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test-runs/start",
        headers=_auth_headers("dq:rules:test"),
        json={"version_id": "dov-23", "sample_count": 3},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["detail"]["error"] == "active_compiler_artifact_required"


def test_start_rule_test_with_generated_data_succeeds_for_freshly_validated_rule(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    create_response = client.post(
        "/api/rulebuilder/v1/rules",
        headers=_auth_headers("dq:rules:create"),
        json={
            "name": "Fresh Testable Regex Rule",
            "description": "Should be testable immediately after validation",
            "dimension": "validity",
            "active": False,
            "workspace": "default",
            "dsl": {
                "schemaVersion": "1.0.0",
                "source": {
                    "kind": "check_type",
                    "checkType": "REGEX",
                    "checkTypeParams": {
                        "checkType": "REGEX",
                        "attribute": "email",
                        "pattern": "^[^@]+@[^@]+\\.[^@]+$",
                        "flags": "",
                    },
                },
            },
        },
    )
    assert create_response.status_code == 200
    rule_id = create_response.json()["id"]

    validate_response = client.post(
        f"/api/rulebuilder/v1/rules/{rule_id}/validate",
        headers=_auth_headers("dq:rules:write"),
    )
    assert validate_response.status_code == 200
    assert validate_response.json()["compiled_expression"].strip() != ""

    response = client.post(
        f"/api/rulebuilder/v1/rules/{rule_id}/test-runs/start",
        headers=_auth_headers("dq:rules:test"),
        json={"version_id": "dov-23", "sample_count": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["execution_trace"]["rule_version_id"]
    assert payload["execution_trace"]["artifact_key"]


def test_test_rule_with_generated_data_requires_test_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test-with-generated-data",
        headers=_auth_headers("dq:rules:read"),
        json={"version_id": "dov-23", "sample_count": 3},
    )

    assert response.status_code == 403


def test_test_proofs_returns_rows(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/test-proofs/rule-email-format",
        headers=_auth_headers("dq:rules:test"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert any(row["id"] == "tp-001" for row in payload)


def test_test_proofs_exposes_persisted_execution_trace(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    monkeypatch.setattr(testing_context, "build_execution_context", _compiled_execution_context)

    store_response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test",
        headers=_auth_headers("dq:rules:test"),
        json={
            "coverage": 0.95,
            "passed": True,
            "records_tested_count": 20,
            "failures_found": 1,
            "proof_data": {"suite": "traceability"},
        },
    )
    assert store_response.status_code == 200
    stored_proof_id = store_response.json()["proof_id"]

    list_response = client.get(
        "/api/rulebuilder/v1/test-proofs/rule-email-format",
        headers=_auth_headers("dq:rules:test"),
    )
    assert list_response.status_code == 200
    proofs = list_response.json()

    matching = next((row for row in proofs if row.get("id") == stored_proof_id), None)
    assert matching is not None
    assert matching["execution_context"]["source_rule_expression"] == "email contains '@'"
    assert matching["proof_data"]["execution_trace"]["execution_id"]
    assert matching["proof_data"]["execution_trace"]["correlation_id"]
    assert matching["proof_data"]["execution_trace"]["result_status"] == "passed"
    assert "artifact_key" in matching["proof_data"]["execution_trace"]
    assert matching["execution_trace"]["execution_id"]
    assert matching["execution_trace"]["correlation_id"]
    assert matching["execution_trace"]["result_status"] == "passed"


def test_log_test_action_persists_metrics_and_diagnostics(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    monkeypatch.setattr(testing_context, "build_execution_context", _compiled_execution_context)

    response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test",
        headers=_auth_headers("dq:rules:test"),
        json={
            "coverage": 0.81,
            "passed": False,
            "records_tested_count": 100,
            "failures_found": 19,
            "proof_data": {"suite": "phase6"},
            "metrics": {
                "matchCount": 81,
                "mismatchCount": 19,
                "eligibleJoinedRows": 100,
                "matchRate": 81.0,
                "actualityDateMismatchCount": 7,
                "nullOrMissingJoinKeyCount": 3,
            },
            "diagnostics": [
                {
                    "failureClass": "actuality_date_drift",
                    "count": 7,
                    "sampleFailures": [
                        {
                            "failureClass": "actuality_date_drift",
                            "rowIdentifier": "id=42",
                            "details": "Actuality-date delta exceeds contract tolerance",
                        }
                    ],
                    "maxSampleSize": 5,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"] is not None
    assert payload["metrics"]["match_count"] == 81
    assert payload["metrics"]["actuality_date_mismatch_count"] == 7
    assert payload["diagnostics"] is not None
    assert payload["diagnostics"][0]["failure_class"] == "actuality_date_drift"
    assert payload["diagnostics"][0]["count"] == 7


def test_test_proofs_list_includes_metrics_and_diagnostics(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    monkeypatch.setattr(testing_context, "build_execution_context", _compiled_execution_context)

    store_response = client.post(
        "/api/rulebuilder/v1/rules/rule-email-format/test",
        headers=_auth_headers("dq:rules:test"),
        json={
            "coverage": 0.9,
            "passed": True,
            "records_tested_count": 20,
            "failures_found": 2,
            "proof_data": {"suite": "phase6-list"},
            "metrics": {
                "matchCount": 18,
                "mismatchCount": 2,
                "eligibleJoinedRows": 20,
                "matchRate": 90.0,
                "actualityDateMismatchCount": 1,
                "nullOrMissingJoinKeyCount": 0,
            },
            "diagnostics": [
                {
                    "failureClass": "value_mismatch",
                    "count": 2,
                    "sampleFailures": [
                        {
                            "failureClass": "value_mismatch",
                            "rowIdentifier": "id=5",
                            "details": "Compared attribute values differ",
                            "affectedAttributes": ["amount"],
                        }
                    ],
                    "maxSampleSize": 5,
                }
            ],
        },
    )
    assert store_response.status_code == 200
    stored_proof_id = store_response.json()["proof_id"]

    list_response = client.get(
        "/api/rulebuilder/v1/test-proofs/rule-email-format",
        headers=_auth_headers("dq:rules:test"),
    )
    assert list_response.status_code == 200
    proofs = list_response.json()

    matching = next((row for row in proofs if row.get("id") == stored_proof_id), None)
    assert matching is not None
    assert matching["metrics"] is not None
    assert matching["metrics"]["match_rate"] == 90.0
    assert matching["diagnostics"] is not None
    assert matching["diagnostics"][0]["failure_class"] == "value_mismatch"


def test_test_proofs_requires_test_scope(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    response = client.get(
        "/api/rulebuilder/v1/test-proofs/rule-email-format",
        headers=_auth_headers("dq:rules:read"),
    )

    assert response.status_code == 403
