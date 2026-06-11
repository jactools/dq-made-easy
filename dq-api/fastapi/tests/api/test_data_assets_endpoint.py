from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
import yaml

from app.core.config import get_settings
from app.core.dependencies import get_data_asset_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_incident_repository
from app.core.dependencies import get_monitor_schedule_repository
from app.core.dependencies import get_rules_repository
from app.domain.entities.incident import IncidentEntity
from app.domain.entities.monitor_schedule import MonitorScheduleEntity
from app.domain.entities.rule import RuleEntity
from app.infrastructure.repositories import InMemoryAppConfigRepository
from app.infrastructure.repositories import InMemoryDataAssetRepository
from app.infrastructure.repositories import InMemoryDataCatalogRepository
from app.infrastructure.repositories import InMemoryApprovalsRepository
from app.infrastructure.repositories import InMemoryIncidentRepository
from app.infrastructure.repositories import InMemoryMonitorScheduleRepository
from app.infrastructure.repositories import InMemoryRulesRepository
from app.main import app
import app.api.v1.endpoints.data_assets as data_assets_module
import app.main as main_module


@pytest.fixture(autouse=True)
def data_assets_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DQ_DB_LOCAL_URL", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def data_asset_repository() -> InMemoryDataAssetRepository:
    repository = InMemoryDataAssetRepository()
    repository.create_data_asset(
        {
            "id": "asset-1",
            "name": "Customer health",
            "workspace_id": "ws-1",
            "status": "draft",
            "source_object_version_ids": ["dov-1"],
            "business_context": {
                "dataset_id": "dataset-1",
                "data_product_id": "product-1",
                "domain": "Customer",
                "owner": "data-owner@example.com",
                "purpose": "Track customer health for operational reporting",
                "steward": "data-steward@example.com",
                "criticality": "high",
                "tags": ["customer", "golden-record"],
                "business_definitions": ["Customer health metric used for support prioritization"],
                "lineage_references": ["dov-1", "dataset-1"],
                "validation_suites": ["validation-suite-customer-health"],
                "validation_plans": ["validation-plan-customer-health-daily"],
                "consumers": ["Support", "Analytics"],
            },
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
                    "nullable": False,
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


@pytest.fixture
def lineage_repositories() -> dict[str, object]:
    data_catalog_repository = InMemoryDataCatalogRepository()
    data_catalog_repository._data_products = [
        {
            "id": "product-1",
            "name": "Customer Intelligence",
            "description": "",
            "owner": "",
            "created_at": "2026-05-20T00:00:00Z",
            "icon": "",
            "workspace_id": "ws-1",
            "odcs_data_product_id": None,
            "business_key": "",
        }
    ]
    data_catalog_repository._data_sets = [
        {
            "id": "dataset-1",
            "product_id": "product-1",
            "name": "Customer Events",
            "description": "",
            "owner": "",
            "created_at": "2026-05-20T00:00:00Z",
            "workspace_id": "ws-1",
            "business_key": "",
        }
    ]
    data_catalog_repository._data_objects = [
        {
            "id": "object-1",
            "name": "Customer Event",
            "description": "",
            "status": "active",
            "created_at": "2026-05-20T00:00:00Z",
            "business_key": "",
        }
    ]
    data_catalog_repository._data_objects_catalog = [
        {
            "id": "object-1",
            "dataset_id": "dataset-1",
            "name": "Customer Event",
            "description": "",
            "icon": "",
            "created_at": "2026-05-20T00:00:00Z",
            "latest_version_id": "dov-1",
            "business_key": "",
        }
    ]
    data_catalog_repository._data_object_versions = [
        {
            "id": "dov-1",
            "data_object_id": "object-1",
            "version": 1,
            "created_at": "2026-05-20T00:00:00Z",
            "schema_hash": "schema-hash",
            "attribute_count": 1,
            "storage_uri": None,
            "storage_format": "csv",
            "storage_options_json": None,
        }
    ]
    data_catalog_repository.create_materialized_delivery_note(
        {
            "data_delivery_id": "delivery-1",
            "data_object_id": "object-1",
            "data_object_version_id": "dov-1",
            "version": 1,
            "delivered_at": "2026-05-25T10:00:00Z",
            "delivery_status": "completed",
            "metadata_json": {
                "object_storage_classification": "real_evidence",
                "evidence_classification": "real_evidence",
            },
        }
    )

    rules_repository = InMemoryRulesRepository()
    rules_repository._rules = {
        "rule-1": RuleEntity(
            id="rule-1",
            name="Customer event completeness",
            description="",
            expression="count(*) > 0",
            dimension="Completeness",
            active=True,
            createdByUserId="user-1",
            tagIds=[],
            checkType="row_count",
            checkTypeParams={"dataObjectVersionId": "dov-1"},
            dsl={"sourceDataObjectVersionId": "dov-1"},
        )
    }
    rules_repository._rule_details = {
        "rule-1": {
            "workspace": "ws-1",
            "generated": False,
            "is_template": False,
            "template_id": None,
            "suggestion_id": None,
            "comments": None,
            "dsl": {"sourceDataObjectVersionId": "dov-1"},
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "manual_override_by": None,
            "manual_override_at": None,
            "reusableFilterIds": [],
            "reusableFilters": [],
            "check_type": "row_count",
            "check_type_params": {"dataObjectVersionId": "dov-1"},
        }
    }
    rules_repository._rule_versions = {
        "rule-1": [{"id": "rule-1-v1", "createdAt": "2026-05-20T00:00:00Z"}]
    }
    rules_repository._rollback_history = {}
    rules_repository._status_history = {}

    monitor_schedule_repository = InMemoryMonitorScheduleRepository()
    monitor_schedule_repository.upsert_monitor_schedule(
        MonitorScheduleEntity(
            id="monitor-1",
            scope_kind="data_asset",
            scope_id="asset-1",
            workspace_id="ws-1",
            monitor_type="scheduled_monitor",
            cron_expression="0 * * * *",
            timezone="UTC",
            window_minutes=1440,
            enabled=True,
            signals=[],
        )
    )
    monitor_schedule_repository.upsert_monitor_schedule(
        MonitorScheduleEntity(
            id="monitor-2",
            scope_kind="source_dataset",
            scope_id="dataset-1",
            workspace_id="ws-1",
            monitor_type="scheduled_monitor",
            cron_expression="0 * * * *",
            timezone="UTC",
            window_minutes=1440,
            enabled=True,
            signals=[],
        )
    )

    incident_repository = InMemoryIncidentRepository()
    incident_repository.create_incident(
        IncidentEntity(
            id="incident-1",
            incident_kind="functional_violation",
            status="open",
            title="Customer health drift",
            description=None,
            severity="high",
            run_id=None,
            run_plan_id=None,
            workspace_id="ws-1",
            scope_kind="data_asset",
            scope_id="asset-1",
            failure_code=None,
            failure_message=None,
            violated_rule_ids=["rule-1"],
            violation_count=1,
            itsm_ticket_id=None,
            itsm_ticket_number=None,
            assigned_to=None,
            resolved_at=None,
            comments=[],
            resolution_history=[],
            created_by=None,
            updated_by=None,
        )
    )

    return {
        "data_catalog_repository": data_catalog_repository,
        "rules_repository": rules_repository,
        "monitor_schedule_repository": monitor_schedule_repository,
        "incident_repository": incident_repository,
    }


@pytest.fixture
def approvals_repository() -> InMemoryApprovalsRepository:
    return InMemoryApprovalsRepository()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    data_asset_repository: InMemoryDataAssetRepository,
    approvals_repository: InMemoryApprovalsRepository,
    lineage_repositories: dict[str, object],
) -> TestClient:
    app_config_repository = InMemoryAppConfigRepository()
    monkeypatch.setattr(main_module, "get_app_config_repository", lambda: app_config_repository)
    app.dependency_overrides[get_app_config_repository] = lambda: app_config_repository
    app.dependency_overrides[get_data_asset_repository] = lambda: data_asset_repository
    app.dependency_overrides[get_approvals_repository] = lambda: approvals_repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: lineage_repositories["data_catalog_repository"]
    app.dependency_overrides[get_rules_repository] = lambda: lineage_repositories["rules_repository"]
    app.dependency_overrides[get_monitor_schedule_repository] = lambda: lineage_repositories["monitor_schedule_repository"]
    app.dependency_overrides[get_incident_repository] = lambda: lineage_repositories["incident_repository"]
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_list_data_assets_returns_repository_rows(client: TestClient, auth_headers) -> None:
    response = client.get("/rulebuilder/v1/data-assets", headers=auth_headers("dq:rules:read"))

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == "asset-1"
    assert payload[0]["workspace_id"] == "ws-1"
    assert payload[0]["business_context"]["domain"] == "Customer"
    assert payload[0]["data_contract_download_url"] == "/data-assets/asset-1/contract"


def test_create_data_asset_persists_business_context(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/rulebuilder/v1/data-assets",
        headers=auth_headers("dq:rules:write"),
        json={
            "id": "asset-2",
            "name": "Risk profile",
            "workspace_id": "ws-1",
            "business_context": {
                "dataset_id": "dataset-2",
                "data_product_id": "product-2",
                "domain": "Risk",
                "owner": "risk-owner@example.com",
                "purpose": "Track customer risk exposure",
                "steward": "risk@example.com",
                "criticality": "medium",
                "tags": ["risk", "regulated"],
                "business_definitions": ["Risk profile identifies customer exposure bands"],
                "lineage_references": ["dataset-2", "policy-17"],
                "consumers": ["Risk", "Compliance"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["business_context"]["dataset_id"] == "dataset-2"
    assert payload["business_context"]["owner"] == "risk-owner@example.com"
    assert payload["business_context"]["domain"] == "Risk"
    assert payload["business_context"]["business_definitions"] == ["Risk profile identifies customer exposure bands"]
    assert payload["business_context"]["lineage_references"] == ["dataset-2", "policy-17"]
    assert payload["business_context"]["tags"] == ["risk", "regulated"]
    assert payload["business_context"]["consumers"] == ["Risk", "Compliance"]


def test_get_data_asset_lineage_returns_related_nodes(
    client: TestClient,
    auth_headers,
    data_asset_repository: InMemoryDataAssetRepository,
) -> None:
    response = client.get(
        "/rulebuilder/v1/data-assets/asset-1/lineage",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_asset"]["id"] == "asset-1"
    assert payload["impact_summary"]["contract_change_count"] >= 0
    assert payload["business_context_overlay"]["domain"] == "Customer"
    assert payload["classification_view"]["classification"] in {"public", "internal", "restricted"}
    assert isinstance(payload["anomaly_annotations"], list)
    assert payload["snapshot_id"]
    assert payload["captured_at"]
    assert any(node["kind"] == "data_object_version" and node["id"] == "dov-1" for node in payload["upstream_nodes"])
    assert any(node["kind"] == "data_object" and node["id"] == "object-1" for node in payload["upstream_nodes"])
    assert any(node["kind"] == "data_set" and node["id"] == "dataset-1" for node in payload["upstream_nodes"])
    assert any(node["kind"] == "data_product" and node["id"] == "product-1" for node in payload["upstream_nodes"])
    assert any(node["kind"] == "rule" and node["id"] == "rule-1" for node in payload["downstream_nodes"])
    assert any(node["kind"] == "monitor_schedule" for node in payload["downstream_nodes"])
    assert any(node["kind"] == "incident" for node in payload["downstream_nodes"])
    assert payload["impact_summary"]["impacted_rule_ids"] == ["rule-1"]
    assert sorted(payload["impact_summary"]["impacted_monitor_scope_ids"]) == ["asset-1", "dataset-1"]
    assert payload["impact_summary"]["impacted_incident_ids"] == ["incident-1"]
    assert payload["impact_summary"]["notes"]
    snapshots = data_asset_repository.list_data_asset_lineage_snapshots("asset-1")
    assert len(snapshots) == 1
    assert snapshots[0].classification_view is not None


def test_get_data_asset_governance_discovery_prioritizes_real_evidence(
    client: TestClient,
    auth_headers,
    data_asset_repository: InMemoryDataAssetRepository,
    lineage_repositories: dict[str, object],
) -> None:
    data_catalog_repository = lineage_repositories["data_catalog_repository"]
    assert data_catalog_repository is not None

    response = client.get(
        "/rulebuilder/v1/data-assets/asset-1/governance-discovery",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "asset-1"
    assert payload["priority"] == "high"
    assert "real_evidence" in payload["evidence_classifications"]
    assert "real_evidence" in payload["object_storage_classifications"]
    assert payload["snapshot_id"]
    assert payload["captured_at"]

    snapshots = data_asset_repository.list_data_asset_lineage_snapshots("asset-1")
    assert any(snapshot.snapshot_kind == "governance_discovery" for snapshot in snapshots)


def test_get_data_asset_version_returns_nested_version(client: TestClient, auth_headers) -> None:
    response = client.get(
        "/rulebuilder/v1/data-assets/asset-1/versions/asset-1-v1",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "asset-1-v1"
    assert payload["data_asset_id"] == "asset-1"
    assert payload["derived_fields"][0]["name"] == "customer_segment"


def test_download_data_asset_contract_returns_odcs_yaml(
    client: TestClient,
    auth_headers,
    data_asset_repository: InMemoryDataAssetRepository,
) -> None:
    response = client.get(
        "/rulebuilder/v1/data-assets/asset-1/contract",
        headers=auth_headers("dq:rules:read"),
    )

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="asset-1.odcs.yaml"'
    contract = yaml.safe_load(response.text)
    assert contract["apiVersion"] == "v3.1.0"
    assert contract["kind"] == "DataContract"
    assert contract["id"] == "urn:dq:contract:asset-1"
    assert contract["name"] == "Customer health"
    assert contract["domain"] == "Customer"
    assert contract["owner"]["name"] == "data-owner@example.com"
    assert contract["tags"] == ["customer", "golden-record", "dq-made-easy", "data-asset", "odcs"]
    assert contract["extension"]["dq"]["dataset_id"] == "dataset-1"
    assert contract["extension"]["dq"]["data_product_id"] == "product-1"
    assert contract["extension"]["dq"]["business_definitions"] == ["Customer health metric used for support prioritization"]
    assert contract["extension"]["dq"]["lineage_references"] == ["dov-1", "dataset-1"]
    assert contract["extension"]["dq"]["validation_suites"] == ["validation-suite-customer-health"]
    assert contract["extension"]["dq"]["validation_plans"] == ["validation-plan-customer-health-daily"]
    assert contract["schema"][0]["properties"][0]["name"] == "customer_id"

    stored_contract = data_asset_repository.get_latest_data_asset_contract_version("asset-1")
    assert stored_contract is not None
    assert stored_contract.version == 1
    assert stored_contract.generated_where == "/rulebuilder/v1/data-assets/asset-1/contract"


def test_import_data_asset_contract_updates_business_context(
    client: TestClient,
    auth_headers,
    data_asset_repository: InMemoryDataAssetRepository,
) -> None:
    contract_payload = {
        "apiVersion": "v3.1.0",
        "kind": "DataContract",
        "id": "urn:dq:contract:asset-1",
        "name": "Customer health updated",
        "status": "active",
        "owner": {"name": "data.owner@example.com"},
        "contact": {"name": "Customer Steward", "email": "data.owner@example.com"},
        "domain": "Customer",
        "description": {"purpose": "Updated customer health asset"},
        "tags": ["customer", "golden-record"],
        "extension": {
            "dq": {
                "dataset_id": "dataset-2",
                "data_product_id": "product-2",
                "business_definitions": ["Customer health metric"],
                "lineage_references": ["dov-1", "upstream-job-9"],
                    "validation_suites": ["validation-suite-customer-health"],
                    "validation_plans": ["validation-plan-customer-health-daily"],
                "ownership": {
                    "owner": "data.owner@example.com",
                    "steward": "Customer Steward",
                    "domain": "Customer",
                    "criticality": "high",
                },
            }
        },
    }

    response = client.post(
        "/rulebuilder/v1/data-assets/asset-1/contract/import",
        headers=auth_headers("dq:rules:write"),
        json={"contract_text": yaml.safe_dump(contract_payload, sort_keys=False)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Customer health updated"
    assert payload["description"] == "Updated customer health asset"
    assert payload["business_context"]["dataset_id"] == "dataset-2"
    assert payload["business_context"]["data_product_id"] == "product-2"
    assert payload["business_context"]["owner"] == "data.owner@example.com"
    assert payload["business_context"]["steward"] == "Customer Steward"
    assert payload["business_context"]["criticality"] == "high"
    assert payload["business_context"]["business_definitions"] == ["Customer health metric"]
    assert payload["business_context"]["lineage_references"] == ["dov-1", "upstream-job-9"]
    assert payload["business_context"]["validation_suites"] == ["validation-suite-customer-health"]
    assert payload["business_context"]["validation_plans"] == ["validation-plan-customer-health-daily"]

    updated_asset = data_asset_repository.get_data_asset("asset-1")
    assert updated_asset is not None
    assert updated_asset.business_context is not None
    assert updated_asset.business_context.dataset_id == "dataset-2"
    assert updated_asset.business_context.validation_suites == ["validation-suite-customer-health"]
    assert updated_asset.business_context.validation_plans == ["validation-plan-customer-health-daily"]


def test_analyze_data_asset_contract_reports_diff_and_conformance(
    client: TestClient,
    auth_headers,
) -> None:
    client.get("/rulebuilder/v1/data-assets/asset-1/contract", headers=auth_headers("dq:rules:read"))

    response = client.get("/rulebuilder/v1/data-assets/asset-1/contract/analysis", headers=auth_headers("dq:rules:read"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data_asset_id"] == "asset-1"
    assert payload["conformance"]["ok"] is True
    assert payload["comparison"] is None
    assert payload["latest_contract_version"]["review_status"] == "pending"


def test_validate_data_asset_contract_conformance_detects_type_mismatch(
    client: TestClient,
    auth_headers,
) -> None:
    contract_response = client.get("/rulebuilder/v1/data-assets/asset-1/contract", headers=auth_headers("dq:rules:read"))
    candidate_contract_yaml = contract_response.text.replace("logicalType: string", "logicalType: integer", 1)

    response = client.post(
        "/rulebuilder/v1/data-assets/asset-1/contract/conformance",
        headers=auth_headers("dq:rules:edit", "dq:rules:write"),
        json={"contract_yaml": candidate_contract_yaml},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["conformance"]["ok"] is False
    assert payload["conformance"]["summary"]["breaking_issues"] >= 1


def test_review_data_asset_contract_updates_latest_version(
    client: TestClient,
    auth_headers,
    data_asset_repository: InMemoryDataAssetRepository,
    approvals_repository: InMemoryApprovalsRepository,
) -> None:
    client.get("/rulebuilder/v1/data-assets/asset-1/contract", headers=auth_headers("dq:rules:read"))

    response = client.post(
        "/rulebuilder/v1/data-assets/asset-1/contract/review",
        headers=auth_headers("dq:rules:edit", "dq:rules:write"),
        json={"review_status": "approved", "review_comments": "Ready for publication"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["notification_status"] == "queued"
    assert payload["contract_version"]["review_status"] == "approved"
    assert payload["contract_version"]["review_comments"] == "Ready for publication"

    stored_contract = data_asset_repository.get_latest_data_asset_contract_version("asset-1")
    assert stored_contract is not None
    assert stored_contract.review_status == "approved"

    audit_rows = approvals_repository.list_approval_audit()
    assert audit_rows
    assert any(row.details.get("workspace_id") == "ws-1" for row in audit_rows)

    notifications_response = client.get(
        "/rulebuilder/v1/notifications?notification_type=contract_change",
        headers=auth_headers("dq:notifications:read"),
    )
    assert notifications_response.status_code == 200
    notifications = notifications_response.json()
    assert notifications
    assert notifications[0]["message"].startswith("Contract approved for Data Asset 'asset-1'")


def test_generate_test_data_for_data_asset_uses_asset_version_and_generator_stub(
    client: TestClient,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def _generate(*, command, services):
        captured["asset_id"] = command.asset_id
        captured["sample_count"] = command.sample_count
        result = {
            "version_id": "asset-1-v1",
            "version_name": 1,
            "data_object_id": "asset-1",
            "data_object_name": "Customer health",
            "sample_count": 2,
            "samples": [{"customer_id": "c-1"}],
            "attributes": [{"name": "customer_id", "type": "string", "nullable": False, "format": "", "is_primary_key": False}],
            "generated_at": "2026-05-21T12:00:00Z",
        }
        return result

    monkeypatch.setattr(data_assets_module, "generate_test_data_for_data_asset_use_case", _generate)

    response = client.post(
        "/rulebuilder/v1/data-assets/asset-1/generate-test-data",
        headers=auth_headers("dq:rules:test"),
        json={"sample_count": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured["asset_id"] == "asset-1"
    assert captured["sample_count"] == 2
    assert payload["version_id"] == "asset-1-v1"
    assert payload["sample_count"] == 2
    assert payload["samples"][0]["customer_id"] == "c-1"


def test_schema_only_upload_populates_contract_and_generation_from_preview_columns(
    client: TestClient,
    auth_headers,
    data_asset_repository: InMemoryDataAssetRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_response = client.post(
        "/rulebuilder/v1/data-assets",
        headers=auth_headers("dq:rules:write"),
        json={
            "id": "asset-schema-only",
            "name": "Schema only asset",
            "workspace_id": "ws-1",
        },
    )

    assert create_response.status_code == 200

    version_response = client.post(
        "/rulebuilder/v1/data-assets/asset-schema-only/versions",
        headers=auth_headers("dq:rules:write"),
        json={
            "id": "asset-schema-only-v1",
            "version": 1,
            "upload_preview": {
                "file_name": "schema-only.csv",
                "file_format": "csv",
                "columns": [
                    {"name": "customer_id", "data_type": "string", "nullable": False},
                    {"name": "loyalty_score", "data_type": "number", "nullable": True},
                ],
            },
        },
    )

    assert version_response.status_code == 200
    version_payload = version_response.json()
    assert version_payload["upload_preview"]["columns"][0]["name"] == "customer_id"
    assert version_payload["upload_preview"]["columns"][1]["name"] == "loyalty_score"

    contract_response = client.get(
        "/rulebuilder/v1/data-assets/asset-schema-only/contract",
        headers=auth_headers("dq:rules:read"),
    )

    assert contract_response.status_code == 200
    assert "Schema preview column" in contract_response.text
    assert "customer_id" in contract_response.text
    assert "loyalty_score" in contract_response.text

    stored_contract = data_asset_repository.get_latest_data_asset_contract_version("asset-schema-only")
    assert stored_contract is not None
    assert stored_contract.version == 1
    assert stored_contract.generated_where == "/rulebuilder/v1/data-assets/asset-schema-only/contract"

    captured: dict[str, object] = {}

    async def _generate(*, command, services):
        captured["asset_id"] = command.asset_id
        captured["sample_count"] = command.sample_count
        return {
            "version_id": "asset-schema-only-v1",
            "version_name": 1,
            "data_object_id": "asset-schema-only",
            "data_object_name": "Schema only asset",
            "sample_count": 3,
            "samples": [{"customer_id": "c-1", "loyalty_score": 42}],
            "attributes": [
                {"name": "customer_id", "type": "string", "nullable": False, "format": "", "is_primary_key": False},
                {"name": "loyalty_score", "type": "number", "nullable": True, "format": "", "is_primary_key": False},
            ],
            "generated_at": "2026-05-21T12:00:00Z",
        }

    monkeypatch.setattr(data_assets_module, "generate_test_data_for_data_asset_use_case", _generate)

    generation_response = client.post(
        "/rulebuilder/v1/data-assets/asset-schema-only/generate-test-data",
        headers=auth_headers("dq:rules:test"),
        json={"sample_count": 3},
    )

    assert generation_response.status_code == 200
    generation_payload = generation_response.json()
    assert captured == {"asset_id": "asset-schema-only", "sample_count": 3}
    assert generation_payload["version_id"] == "asset-schema-only-v1"
    assert generation_payload["sample_count"] == 3
    assert generation_payload["samples"][0]["loyalty_score"] == 42


def test_validate_and_delete_data_asset(client: TestClient, auth_headers) -> None:
    validate_response = client.post(
        "/rulebuilder/v1/data-assets/asset-1/validate",
        headers=auth_headers("dq:rules:write"),
    )
    assert validate_response.status_code == 200
    validate_payload = validate_response.json()
    assert validate_payload["ok"] is True
    assert validate_payload["asset"]["id"] == "asset-1"
    assert validate_payload["version"]["id"] == "asset-1-v1"

    delete_response = client.delete(
        "/rulebuilder/v1/data-assets/asset-1",
        headers=auth_headers("dq:rules:write"),
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True
