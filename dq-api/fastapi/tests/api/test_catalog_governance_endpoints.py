from fastapi.testclient import TestClient
import pytest

from app.core.config import get_settings
from app.core.dependencies import get_data_asset_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_exception_reason_analytics_projection_repository
from app.core.dependencies import get_gx_execution_run_repository
from app.core.dependencies import get_rules_repository
from app.domain.entities import ApprovalEntity
from app.domain.entities import build_rule_record_entity
from app.main import app
from app.domain.entities.gx_execution_violation import build_gx_execution_violation_summary_entity

client = TestClient(app)


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
    return {"Authorization": f"Bearer {token}"}


def setup_module() -> None:
    get_settings.cache_clear()


def teardown_module() -> None:
    get_settings.cache_clear()


def test_catalog_health_and_terms_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    health_response = client.get("/api/rulebuilder/v1/catalog/health", headers=_auth_headers("dq:rules:read"))
    terms_response = client.get("/api/rulebuilder/v1/catalog/terms", headers=_auth_headers("dq:rules:read"))

    assert health_response.status_code == 200
    assert terms_response.status_code == 200
    health_payload = health_response.json()
    terms_payload = terms_response.json()
    assert health_payload["status"] in {"healthy", "degraded", "unknown", "error"}
    assert isinstance(terms_payload["terms"], list)


def test_governance_drift_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    rule_response = client.get(
        "/api/rulebuilder/v1/governance/drift/rules/rule-email-format/v1",
        headers=_auth_headers("dq:rules:read"),
    )
    summary_response = client.get(
        "/api/rulebuilder/v1/governance/drift/summary",
        headers=_auth_headers("dq:rules:read"),
    )
    affected_response = client.get(
        "/api/rulebuilder/v1/governance/drift/terms/amount/affected-rules",
        headers=_auth_headers("dq:rules:read"),
    )

    assert rule_response.status_code == 200
    assert summary_response.status_code == 200
    assert affected_response.status_code == 200
    assert "rule_id" in rule_response.json()
    assert "affected_rules" in summary_response.json()
    assert "affected_rules" in affected_response.json()


class _MonitorDefinitionDataAssetRepository:
    def __init__(self) -> None:
        from types import SimpleNamespace

        self.assets = [
            SimpleNamespace(id="asset-1", name="Customer Snapshot", workspace_id="ws-1"),
            SimpleNamespace(id="asset-2", name="Ledger Snapshot", workspace_id="ws-2"),
        ]

    def list_data_assets(self, workspace_id: str | None = None):
        if workspace_id is None:
            return list(self.assets)
        return [asset for asset in self.assets if asset.workspace_id == workspace_id]


class _MonitorDefinitionDataCatalogRepository:
    def __init__(self) -> None:
        from types import SimpleNamespace

        self.data_sets = [
            SimpleNamespace(id="dataset-1", name="Source Feed", workspace_id="ws-1"),
            SimpleNamespace(id="dataset-2", name="Archive Feed", workspace_id="ws-2"),
        ]

    def list_data_sets(self, product_id: str | None = None, workspace: str | None = None):
        rows = list(self.data_sets)
        if workspace is not None:
            rows = [data_set for data_set in rows if data_set.workspace_id == workspace]
        return rows


def test_governance_monitor_definition_catalog(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    data_asset_repository = _MonitorDefinitionDataAssetRepository()
    data_catalog_repository = _MonitorDefinitionDataCatalogRepository()
    app.dependency_overrides[get_data_asset_repository] = lambda: data_asset_repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: data_catalog_repository

    try:
        response = client.get(
            "/api/rulebuilder/v1/governance/monitor-definitions",
            headers=_auth_headers("dq:rules:read"),
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["total_monitor_definitions"] == 4
        assert payload["summary"]["data_asset_monitor_count"] == 2
        assert payload["summary"]["source_dataset_monitor_count"] == 2
        assert payload["summary"]["workspace_count"] == 2

        filtered_response = client.get(
            "/api/rulebuilder/v1/governance/monitor-definitions?workspace_id=ws-1",
            headers=_auth_headers("dq:rules:read"),
        )
        assert filtered_response.status_code == 200
        filtered_payload = filtered_response.json()
        assert filtered_payload["summary"]["total_monitor_definitions"] == 2
        assert filtered_payload["summary"]["workspace_count"] == 1
        assert {item["scope_kind"] for item in filtered_payload["monitor_definitions"]} == {"data_asset", "source_dataset"}
        assert all(item["workspace_id"] == "ws-1" for item in filtered_payload["monitor_definitions"])
        assert filtered_payload["monitor_definitions"][0]["schedule_definition"]["timezone"] == "UTC"
    finally:
        app.dependency_overrides.pop(get_data_asset_repository, None)
        app.dependency_overrides.pop(get_data_catalog_repository, None)


def test_governance_monitor_anomaly_catalog(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    data_asset_repository = _MonitorDefinitionDataAssetRepository()
    data_catalog_repository = _MonitorDefinitionDataCatalogRepository()
    app.dependency_overrides[get_data_asset_repository] = lambda: data_asset_repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: data_catalog_repository

    try:
        response = client.get(
            "/api/rulebuilder/v1/governance/monitor-anomalies",
            headers=_auth_headers("dq:rules:read"),
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["total_monitor_anomalies"] == 16
        assert payload["summary"]["data_asset_anomaly_count"] == 8
        assert payload["summary"]["source_dataset_anomaly_count"] == 8
        assert payload["summary"]["workspace_count"] == 2
        assert payload["summary"]["signal_counts"] == {
            "distribution": 4,
            "freshness": 4,
            "null_rate": 4,
            "volume": 4,
        }

        filtered_response = client.get(
            "/api/rulebuilder/v1/governance/monitor-anomalies?workspace_id=ws-1",
            headers=_auth_headers("dq:rules:read"),
        )
        assert filtered_response.status_code == 200
        filtered_payload = filtered_response.json()
        assert filtered_payload["summary"]["total_monitor_anomalies"] == 8
        assert filtered_payload["summary"]["workspace_count"] == 1
        assert all(item["workspace_id"] == "ws-1" for item in filtered_payload["monitor_anomalies"])
        assert filtered_payload["monitor_anomalies"][0]["threshold_unit"] in {"percent", "points", "hours"}
    finally:
        app.dependency_overrides.pop(get_data_asset_repository, None)
        app.dependency_overrides.pop(get_data_catalog_repository, None)


def test_governance_monitor_drift_catalog(client, auth_headers) -> None:
    data_asset_repository = _MonitorDefinitionDataAssetRepository()
    data_catalog_repository = _MonitorDefinitionDataCatalogRepository()
    app.dependency_overrides[get_data_asset_repository] = lambda: data_asset_repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: data_catalog_repository

    try:
        response = client.get(
            "/api/rulebuilder/v1/governance/monitor-drifts",
            headers=auth_headers("dq:rules:read"),
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["total_monitor_drifts"] == 12
        assert payload["summary"]["data_asset_drift_count"] == 6
        assert payload["summary"]["source_dataset_drift_count"] == 6
        assert payload["summary"]["workspace_count"] == 2
        assert payload["summary"]["drift_counts"] == {
            "behavioral": 4,
            "field_level": 4,
            "schema": 4,
        }

        filtered_response = client.get(
            "/api/rulebuilder/v1/governance/monitor-drifts?workspace_id=ws-1",
            headers=auth_headers("dq:rules:read"),
        )
        assert filtered_response.status_code == 200
        filtered_payload = filtered_response.json()
        assert filtered_payload["summary"]["total_monitor_drifts"] == 6
        assert filtered_payload["summary"]["workspace_count"] == 1
        assert all(item["workspace_id"] == "ws-1" for item in filtered_payload["monitor_drifts"])
        assert filtered_payload["monitor_drifts"][0]["drift_kind"] in {"schema", "field_level", "behavioral"}
    finally:
        app.dependency_overrides.pop(get_data_asset_repository, None)
        app.dependency_overrides.pop(get_data_catalog_repository, None)


@pytest.fixture
def governance_inbox_client() -> TestClient:
    return TestClient(app)


class _GovernanceInboxRulesRepository:
    def __init__(self) -> None:
        self._rows = [
            build_rule_record_entity(
                {
                    "id": "rule-owned",
                    "name": "Owned rule",
                    "expression": "email IS NOT NULL",
                    "dimension": "Validity",
                    "workspace": "retail-banking",
                    "created_by": "alice@example.com",
                    "active": True,
                    "taxonomy": {
                        "owner": "alice@example.com",
                        "data_steward": "alice@example.com",
                        "domain_owner": "domain-owner@example.com",
                        "technical_owner": "tech-owner@example.com",
                    },
                }
            ),
            build_rule_record_entity(
                {
                    "id": "rule-reassign",
                    "name": "Needs reassignment",
                    "expression": "amount > 0",
                    "dimension": "Completeness",
                    "workspace": "retail-banking",
                    "created_by": "alice@example.com",
                    "active": True,
                    "taxonomy": {
                        "owner": "alice@example.com",
                        "data_steward": "alice@example.com",
                    },
                }
            ),
            build_rule_record_entity(
                {
                    "id": "rule-deprecated",
                    "name": "Deprecated rule",
                    "expression": "status = 'deprecated'",
                    "dimension": "Validity",
                    "workspace": "retail-banking",
                    "created_by": "alice@example.com",
                    "active": False,
                    "lifecycle_status": "deprecated",
                    "taxonomy": {
                        "owner": "alice@example.com",
                        "data_steward": "alice@example.com",
                        "domain_owner": "domain-owner@example.com",
                        "technical_owner": "tech-owner@example.com",
                    },
                }
            ),
        ]

    async def list_rule_records(self, **kwargs):
        workspace = kwargs.get("workspace")
        include_deleted = bool(kwargs.get("include_deleted", False))
        limit = int(kwargs.get("limit", 200))
        offset = int(kwargs.get("offset", 0))
        rows = list(self._rows)
        if workspace is not None:
            rows = [row for row in rows if str(row.workspace or "") == str(workspace)]
        if not include_deleted:
            rows = [row for row in rows if not bool(getattr(row, "removed", False))]
        return rows[offset : offset + limit]


class _GovernanceInboxApprovalsRepository:
    def __init__(self) -> None:
        self._rows = [
            ApprovalEntity(
                id="approval-pending",
                businessKey="approval-pending",
                ruleId="rule-reassign",
                status="pending",
                requesterId="reviewer-1",
                workspaceId="retail-banking",
                requestType="activation",
                requestedAt="2026-05-30T12:00:00Z",
            ),
            ApprovalEntity(
                id="approval-approved",
                businessKey="approval-approved",
                ruleId="rule-owned",
                status="approved",
                requesterId="reviewer-2",
                workspaceId="retail-banking",
                requestType="activation",
                requestedAt="2026-05-30T12:05:00Z",
                reviewedBy="reviewer-1",
                reviewedAt="2026-05-30T12:10:00Z",
            ),
        ]

    def list_approvals(self, workspace_id=None, business_key=None, request_type=None, status=None, requester_id=None, exclude_requester_id=None, query=None):
        del business_key, request_type, requester_id, exclude_requester_id, query
        rows = list(self._rows)
        if workspace_id is not None:
            rows = [row for row in rows if row.workspaceId == workspace_id]
        if status is not None:
            rows = [row for row in rows if row.status == status]
        return rows


def test_governance_inboxes_roll_up_approval_reassignment_and_deprecation_queues(governance_inbox_client, auth_headers) -> None:
    app.dependency_overrides[get_rules_repository] = lambda: _GovernanceInboxRulesRepository()
    app.dependency_overrides[get_approvals_repository] = lambda: _GovernanceInboxApprovalsRepository()

    try:
        response = governance_inbox_client.get(
            "/api/rulebuilder/v1/governance/inboxes?workspace_id=retail-banking&page=1&limit=20",
            headers=auth_headers("dq:rules:read"),
        )

        assert response.status_code == 200, response.text
        payload = response.json()

        assert payload["approval_inbox"]["pagination"]["total"] == 1
        assert [item["id"] for item in payload["approval_inbox"]["data"]] == ["approval-pending"]

        assert payload["reassignment_inbox"]["pagination"]["total"] == 1
        assert [item["id"] for item in payload["reassignment_inbox"]["data"]] == ["rule-reassign"]

        assert payload["deprecation_review_inbox"]["pagination"]["total"] == 1
        assert [item["id"] for item in payload["deprecation_review_inbox"]["data"]] == ["rule-deprecated"]
    finally:
        app.dependency_overrides.pop(get_rules_repository, None)
        app.dependency_overrides.pop(get_approvals_repository, None)


class _RootCauseGxExecutionRunRepository:
    def __init__(self) -> None:
        from types import SimpleNamespace

        self.runs = [
            SimpleNamespace(
                id="run-1",
                suiteId="suite-1",
                suiteVersion=1,
                ruleId="rule-1",
                ruleVersionId="rv-1",
                correlationId="corr-1",
                requestedBy="analyst",
                engineType="spark",
                engineTarget="pyspark",
                executionShape="single_object",
                status="failed",
                submittedAt="2026-05-20T12:00:00+00:00",
                startedAt="2026-05-20T12:01:00+00:00",
                completedAt="2026-05-20T12:02:00+00:00",
                createdAt="2026-05-20T12:00:00+00:00",
                updatedAt="2026-05-20T12:02:00+00:00",
                executionContract={
                    "traceability": {
                        "gx_suite_id": "suite-1",
                        "data_object_version_id": "version-1",
                        "rule_version_id": "rv-1",
                    },
                    "resolved_data_delivery_id": "delivery-1",
                },
                handoffPayload={"run_plan_id": "plan-1"},
                resultSummary={},
                diagnostics=[],
                failureCode=None,
                failureMessage=None,
            )
        ]

    async def list_runs(self, query):
        return list(self.runs)


class _RootCauseRulesRepository:
    def __init__(self) -> None:
        from types import SimpleNamespace

        self.rules = {
            "rule-1": SimpleNamespace(id="rule-1", name="Schema check"),
            "rule-2": SimpleNamespace(id="rule-2", name="Freshness check"),
        }

    async def get_rule_by_id(self, rule_id: str):
        return self.rules.get(rule_id)


class _RootCauseDataCatalogRepository:
    def __init__(self) -> None:
        from types import SimpleNamespace

        self.data_objects = [
            SimpleNamespace(id="data-object-1", name="Customer Snapshot"),
            SimpleNamespace(id="data-object-2", name="Ledger Snapshot"),
        ]
        self.data_object_versions = [
            SimpleNamespace(id="version-1", data_object_id="data-object-1"),
            SimpleNamespace(id="version-2", data_object_id="data-object-2"),
        ]

    def list_data_objects_catalog(self, data_set_id: str | None = None):
        return list(self.data_objects)

    def list_data_object_versions(self, object_id: str | None = None):
        return list(self.data_object_versions)


class _RootCauseProjectionRepository:
    def __init__(self) -> None:
        self.summary = build_gx_execution_violation_summary_entity(
            {
                "total_failed_records": 21,
                "runs_with_failures": 1,
                "trend_totals": [
                    {"bucket_start": "2026-05-20T12:00:00+00:00", "total": 10},
                    {"bucket_start": "2026-05-20T13:00:00+00:00", "total": 11},
                ],
                "rule_totals": [
                    {"rule_id": "rule-1", "total": 12},
                    {"rule_id": "rule-2", "total": 9},
                ],
                "data_object_totals": [
                    {"data_object_version_id": "version-1", "total": 21},
                ],
                "reason_totals": [
                    {"reason_code": "schema_change", "reason_text": "Schema changed", "total": 12},
                    {"reason_code": "freshness_lag", "reason_text": "Upstream lag", "total": 9},
                ],
                "reason_trend_totals": [
                    {
                        "bucket_start": "2026-05-20T12:00:00+00:00",
                        "reason_code": "schema_change",
                        "reason_text": "Schema changed",
                        "total": 4,
                    },
                    {
                        "bucket_start": "2026-05-20T13:00:00+00:00",
                        "reason_code": "schema_change",
                        "reason_text": "Schema changed",
                        "total": 8,
                    },
                    {
                        "bucket_start": "2026-05-20T12:00:00+00:00",
                        "reason_code": "freshness_lag",
                        "reason_text": "Upstream lag",
                        "total": 6,
                    },
                    {
                        "bucket_start": "2026-05-20T13:00:00+00:00",
                        "reason_code": "freshness_lag",
                        "reason_text": "Upstream lag",
                        "total": 3,
                    },
                ],
            }
        )

    async def summarize_reason_analytics(self, **kwargs):
        return self.summary


def test_governance_monitor_root_cause_catalog(client, auth_headers) -> None:
    run_repository = _RootCauseGxExecutionRunRepository()
    rules_repository = _RootCauseRulesRepository()
    data_catalog_repository = _RootCauseDataCatalogRepository()
    projection_repository = _RootCauseProjectionRepository()

    app.dependency_overrides[get_gx_execution_run_repository] = lambda: run_repository
    app.dependency_overrides[get_rules_repository] = lambda: rules_repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: data_catalog_repository
    app.dependency_overrides[get_exception_reason_analytics_projection_repository] = lambda: projection_repository

    try:
        response = client.get(
            "/api/rulebuilder/v1/governance/monitor-root-cause?data_object_version_id=version-1&delivery_id=delivery-1&execution_plan_id=plan-1&suite_id=suite-1&rule_version_id=rv-1",
            headers=auth_headers("dq:rules:read"),
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["total_failed_records"] == 21
        assert payload["summary"]["runs_with_failures"] == 1
        assert payload["summary"]["affected_rule_count"] == 2
        assert payload["summary"]["affected_data_object_version_count"] == 1
        assert payload["summary"]["cause_group_count"] == 2
        assert payload["likely_causes"][0]["cause_group"] == "source_change"
        assert payload["likely_causes"][0]["confidence_band"] == "high"
        assert payload["correlated_changes"][0]["trend_direction"] == "up"
        assert payload["correlated_changes"][1]["trend_direction"] == "down"
        assert all("reason_text" not in item for item in payload["likely_causes"])
        assert all("reason_text" not in item for item in payload["correlated_changes"])
    finally:
        app.dependency_overrides.pop(get_gx_execution_run_repository, None)
        app.dependency_overrides.pop(get_rules_repository, None)
        app.dependency_overrides.pop(get_data_catalog_repository, None)
        app.dependency_overrides.pop(get_exception_reason_analytics_projection_repository, None)


def test_governance_revalidation_job_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    create_response = client.post(
        "/api/rulebuilder/v1/governance/revalidation/jobs",
        headers={**_auth_headers("dq:rules:write"), "Content-Type": "application/json"},
        json={
            "ruleVersionIds": ["v1", "v2"],
            "triggeredByTermId": "amount",
            "triggeredByTermName": "Amount",
        },
    )
    assert create_response.status_code == 201
    job_id = create_response.json()["job_id"]

    status_response = client.get(
        f"/api/rulebuilder/v1/governance/revalidation/jobs/{job_id}",
        headers=_auth_headers("dq:rules:read"),
    )
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["job_id"] == job_id


class _DriftReviewRepository:
    def __init__(self) -> None:
        self.audit: list[dict[str, object]] = []

    def list_approval_audit(self):
        from types import SimpleNamespace

        return [SimpleNamespace(**item) for item in self.audit]

    def append_audit_event(self, *, approval_id: str, action: str, actor_id: str | None, details: dict):
        from types import SimpleNamespace

        item = {
            "id": f"{approval_id}-x-{len(self.audit) + 1}",
            "approvalId": approval_id,
            "action": action,
            "actorId": actor_id,
            "timestamp": "2026-05-02T12:34:56Z",
            "details": dict(details or {}),
        }
        self.audit.append(item)
        return SimpleNamespace(**item)


def test_governance_drift_review_records_audit_entry(monkeypatch) -> None:
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()

    approvals_repository = _DriftReviewRepository()
    app.dependency_overrides[get_approvals_repository] = lambda: approvals_repository

    try:
        review_response = client.post(
            "/api/rulebuilder/v1/governance/drift/reviews",
            headers={**_auth_headers("dq:rules:write"), "Content-Type": "application/json"},
            json={
                "affectedRules": [
                    {
                        "ruleId": "rule-1",
                        "ruleName": "Check Amount",
                        "ruleVersionId": "rv-1",
                        "versionNumber": 5,
                        "affectedAliases": ["amount"],
                        "totalDrifts": 2,
                        "needsRevalidation": True,
                    }
                ],
                "triggeredByTermId": "amount",
                "triggeredByTermName": "Amount",
            },
        )

        assert review_response.status_code == 201
        assert review_response.json()["reviewed_count"] == 1

        audit_response = client.get(
            "/api/rulebuilder/v1/approvals/audit",
            headers=_auth_headers("dq:rules:read"),
        )
        assert audit_response.status_code == 200
        audit_payload = audit_response.json()
        assert len(audit_payload) == 1
        assert audit_payload[0]["action"] == "drift-reviewed"
        assert audit_payload[0]["details"]["rule_id"] == "rule-1"
        assert audit_payload[0]["details"]["reviewed_by"] == "admin"
    finally:
        app.dependency_overrides.pop(get_approvals_repository, None)