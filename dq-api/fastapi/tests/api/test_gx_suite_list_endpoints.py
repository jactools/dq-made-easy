from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.core.config import get_settings
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_validation_artifact_repository
from app.infrastructure.repositories.in_memory_app_config_repository import InMemoryAppConfigRepository
from app.infrastructure.repositories.in_memory_validation_artifact_repository import InMemoryValidationArtifactRepository
from app.main import app


@pytest.fixture(autouse=True)
def isolated_gx_suite_dependencies(monkeypatch: pytest.MonkeyPatch) -> InMemoryValidationArtifactRepository:
    app_config_repository = InMemoryAppConfigRepository()
    repository = InMemoryValidationArtifactRepository()

    monkeypatch.setenv("DQ_DB_LOCAL_URL", "")
    get_settings.cache_clear()
    monkeypatch.setattr(main_module, "get_app_config_repository", lambda: app_config_repository)
    app.dependency_overrides[get_app_config_repository] = lambda: app_config_repository
    app.dependency_overrides[get_validation_artifact_repository] = lambda: repository

    yield repository

    app.dependency_overrides.pop(get_validation_artifact_repository, None)
    app.dependency_overrides.pop(get_app_config_repository, None)
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _gx_artifact() -> dict:
    return {
        "validation_artifact_id": "gx-suite-1",
        "validation_artifact_version": 1,
        "artifact_contract_version": "v1",
        "engine_type": "gx",
        "assignment_scope": {"data_object_id": "obj-1", "dataset_id": "ds-1", "data_product_id": "prod-1"},
        "resolved_execution_scope": {"data_object_version_ids": ["dov-1"]},
        "compiled_from": {"rule_ids": ["r-1"], "compiler_version": "v1", "generated_at": "2026-01-01T00:00:00Z"},
        "execution_hints": {"recommended_engine_target": "pyspark", "primary_key_fields": []},
        "run_planning": {
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "grouping_key": "data_object_version_id",
            "traceability": {
                "rule_id": "r-1",
                "rule_version_id": "rv-1",
                "validation_artifact_id": "gx-suite-1",
                "validation_artifact_version": 1,
            },
        },
        "engine_artifact": {
            "engine_type": "gx",
            "artifact_kind": "gx_expectation_suite",
            "artifact_schema_version": "gx-artifact-envelope/v1",
            "payload": {
                "suiteId": "gx-suite-1",
                "suiteVersion": 1,
                "artifactVersion": "v1",
                "assignmentScope": {"dataObjectId": "obj-1", "datasetId": "ds-1", "dataProductId": "prod-1"},
                "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-1"]},
                "gxSuite": {"expectation_suite_name": "dq_suite", "expectations": [], "meta": {}},
                "compiledFrom": {"ruleIds": ["r-1"], "compilerVersion": "v1", "generatedAt": "2026-01-01T00:00:00Z"},
                "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": []},
            },
        },
    }


def _non_gx_artifact() -> dict:
    return {
        **_gx_artifact(),
        "validation_artifact_id": "soda-art-1",
        "engine_type": "soda",
        "engine_artifact": {
            "engine_type": "soda",
            "artifact_kind": "soda_scan",
            "artifact_schema_version": "soda-scan/v1",
            "payload": {"scanName": "soda-art-1", "checks": []},
        },
        "run_planning": {
            "engine_target": "soda",
            "execution_shape": "single_object",
            "grouping_key": "data_object_version_id",
            "traceability": {
                "rule_id": "r-1",
                "rule_version_id": "rv-1",
                "validation_artifact_id": "soda-art-1",
                "validation_artifact_version": 1,
            },
        },
    }


def test_list_gx_suites_returns_structured_400_for_missing_primary_scope_filter(client, auth_headers) -> None:
    response = client.get(
        "/api/rulebuilder/v1/gx/suites?page=1&limit=10",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 400

    payload = response.json()
    assert payload["title"] == "HTTP Error"
    assert payload["status"] == 400
    assert payload["instance"] == "/api/rulebuilder/v1/gx/suites"
    assert isinstance(payload["correlation_id"], str)

    detail = payload["detail"]
    assert detail["message"] == "Invalid GX retrieval query"
    assert detail["errors"][0]["msg"] == (
        "Value error, Exactly one primary scope filter is required: "
        "dataObjectId, dataObjectVersionId, datasetId, or dataProductId"
    )
    assert detail["errors"][0]["ctx"]["error"] == (
        "Exactly one primary scope filter is required: "
        "dataObjectId, dataObjectVersionId, datasetId, or dataProductId"
    )
    assert isinstance(detail["errors"][0]["ctx"]["error"], str)


def test_list_gx_suites_for_rule_filters_non_gx_artifacts(
    client: TestClient,
    auth_headers,
    isolated_gx_suite_dependencies: InMemoryValidationArtifactRepository,
) -> None:
    asyncio.run(isolated_gx_suite_dependencies.save_artifact(envelope=_gx_artifact(), status="active"))
    asyncio.run(isolated_gx_suite_dependencies.save_artifact(envelope=_non_gx_artifact(), status="active"))

    response = client.get(
        "/api/rulebuilder/v1/gx/suites/by-rule/r-1",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["suite_id"] == "gx-suite-1"