from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domain.entities.data_asset import DataAssetBusinessContextEntity
from app.domain.entities.data_asset import DataAssetEntity
from app.domain.entities.data_asset import DataAssetLineageSnapshotEntity
from app.domain.entities.rule import RuleEntity
from app.domain.entities.sla_slo import SlaSloDefinitionEntity
from app.core.dependencies import get_agent_request_audit_repository
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_data_asset_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_sla_slo_repository
from app.core.dependencies import get_validation_run_repository
from app.main import app


@pytest.fixture
def _agent_dependency_overrides() -> None:
    class _AuditRepository:
        def __init__(self) -> None:
            self.events = []

        async def record_event(self, event):
            self.events.append(event)
            return event

        async def list_events(self, *, limit: int = 100, offset: int = 0):
            return self.events[offset : offset + limit]

    class _ConfigRepository:
        def __init__(self, allowed_agents=None):
            if allowed_agents is None:
                self._allowed_agents = [{"agent_type": "mcp", "agent_source": "pytest-agent"}]
            else:
                self._allowed_agents = list(allowed_agents)

        def get_app_config(self):
            return SimpleNamespace(
                agentPlatformAllowlist=["mistral_ai", "microsoft_copilot"],
                agentAccessPolicy={
                    "defaultAction": "deny",
                    "allowedAgents": self._allowed_agents,
                }
            )

    audit_repository = _AuditRepository()
    config_repository = _ConfigRepository()
    app.dependency_overrides[get_rules_repository] = lambda: object()
    app.dependency_overrides[get_data_asset_repository] = lambda: object()
    app.dependency_overrides[get_data_catalog_repository] = lambda: object()
    app.dependency_overrides[get_sla_slo_repository] = lambda: object()
    app.dependency_overrides[get_app_config_repository] = lambda: config_repository
    app.dependency_overrides[get_validation_run_repository] = lambda: object()
    app.dependency_overrides[get_agent_request_audit_repository] = lambda: audit_repository
    try:
        yield {
            "audit_repository": audit_repository,
            "config_repository": config_repository,
            "config_repository_cls": _ConfigRepository,
        }
    finally:
        app.dependency_overrides.pop(get_rules_repository, None)
        app.dependency_overrides.pop(get_data_asset_repository, None)
        app.dependency_overrides.pop(get_data_catalog_repository, None)
        app.dependency_overrides.pop(get_sla_slo_repository, None)
        app.dependency_overrides.pop(get_app_config_repository, None)
        app.dependency_overrides.pop(get_validation_run_repository, None)
        app.dependency_overrides.pop(get_agent_request_audit_repository, None)


def _agent_headers(auth_headers, *scopes: str) -> dict[str, str]:
    return {
        **auth_headers(*scopes),
        "X-Request-Id": "req-agent-1",
        "X-Agent-Type": "mcp",
        "X-Agent-Source": "pytest-agent",
        "X-Agent-Instance-Id": "pytest-instance-1",
        "X-Forwarded-For": "10.0.0.1",
    }


def test_agent_execute_batch_uses_snake_case_contract(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
    _agent_dependency_overrides,
) -> None:
    from app.api.v1.endpoints import agent as agent_endpoints

    async def _fake_validate_rules_batch(**kwargs):
        return {
            "run_id": "run-agent-001",
            "results": [],
            "conflicts": [],
            "summary": {
                "total": 1,
                "valid": 1,
                "invalid": 0,
                "errors": 0,
                "warnings": 0,
            },
        }

    monkeypatch.setattr(agent_endpoints.rules_endpoints, "validate_rules_batch", _fake_validate_rules_batch)

    response = client.post(
        "/agent/v1/rules/execute-batch",
        headers=_agent_headers(auth_headers, "dq:rules:write"),
        json={"rule_ids": ["rule-001"], "workspace": "workspace-a"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-agent-001"
    assert payload["summary"]["total"] == 1
    audit_events = _agent_dependency_overrides["audit_repository"].events
    assert len(audit_events) == 1
    event = audit_events[0]
    assert event.response_type == "batch_validation_response"
    assert event.status_code == 200
    assert event.agent_type == "mcp"
    assert event.agent_source == "pytest-agent"
    assert event.agent_instance_id == "pytest-instance-1"
    assert event.request_origin == "10.0.0.1"


def test_agent_metadata_data_objects_lookup_filters_search(client, auth_headers, _agent_dependency_overrides) -> None:
    class _CatalogRepository:
        def list_data_objects(self):
            return [
                SimpleNamespace(id="obj-1", name="Customer", description="Customer profile", status="active"),
                SimpleNamespace(id="obj-2", name="Payment", description="Payment facts", status="active"),
            ]

    app.dependency_overrides[get_data_catalog_repository] = lambda: _CatalogRepository()
    try:
        response = client.get(
            "/agent/v1/metadata/data-objects?search=customer&limit=10",
            headers=_agent_headers(auth_headers, "dq:rules:read"),
        )
    finally:
        app.dependency_overrides.pop(get_data_catalog_repository, None)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["data_objects"]) == 1
    assert payload["data_objects"][0]["name"] == "Customer"
    audit_events = _agent_dependency_overrides["audit_repository"].events
    assert len(audit_events) == 1
    event = audit_events[0]
    assert event.response_type == "metadata_lookup_response"
    assert event.status_code == 200


def test_agent_openapi_publishes_agent_paths(client, auth_headers, _agent_dependency_overrides) -> None:
    response = client.get(
        "/agent/v1/openapi",
        headers=_agent_headers(auth_headers, "dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["openapi"]
    assert "/agent/v1/rules/execute-batch" in payload["paths"]
    assert "/agent/v1/metadata/data-objects" in payload["paths"]
    audit_events = _agent_dependency_overrides["audit_repository"].events
    assert len(audit_events) == 1
    assert audit_events[0].response_type == "openapi_spec_response"


def test_agent_audit_records_validation_error_response_type(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
    _agent_dependency_overrides,
) -> None:
    from app.api.v1.endpoints import agent as agent_endpoints

    async def _raise_http_exception(**kwargs):
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail={"error": "validation_failed"})

    monkeypatch.setattr(agent_endpoints.rules_endpoints, "validate_rules_batch", _raise_http_exception)

    response = client.post(
        "/agent/v1/rules/execute-batch",
        headers=_agent_headers(auth_headers, "dq:rules:write"),
        json={"rule_ids": ["rule-001"], "workspace": "workspace-a"},
    )

    assert response.status_code == 422
    audit_events = _agent_dependency_overrides["audit_repository"].events
    assert len(audit_events) == 1
    event = audit_events[0]
    assert event.response_type == "validation_error_response"
    assert event.status_code == 422


def test_agent_endpoints_deny_by_default_and_still_audit(client, auth_headers, _agent_dependency_overrides) -> None:
    deny_config_repository = _agent_dependency_overrides["config_repository_cls"](allowed_agents=[])
    app.dependency_overrides[get_app_config_repository] = lambda: deny_config_repository
    try:
        response = client.get(
            "/agent/v1/openapi",
            headers=_agent_headers(auth_headers, "dq:rules:read"),
        )
    finally:
        app.dependency_overrides[get_app_config_repository] = lambda: _agent_dependency_overrides["config_repository"]

    assert response.status_code == 403
    payload = response.json()
    assert payload["detail"]["error"] == "agent_not_allowed"
    audit_events = _agent_dependency_overrides["audit_repository"].events
    assert len(audit_events) == 1
    assert audit_events[0].response_type == "agent_denied_response"


def test_agent_audit_events_endpoint_lists_events(client, auth_headers, _agent_dependency_overrides) -> None:
    response = client.get(
        "/agent/v1/openapi",
        headers=_agent_headers(auth_headers, "dq:rules:read"),
    )
    assert response.status_code == 200

    list_response = client.get(
        "/agent/v1/audit/events?limit=10&offset=0",
        headers=auth_headers("dq:admin:read", "dq:rules:read"),
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload["events"]) >= 1
    assert payload["events"][0]["action"]


def test_agent_audit_events_endpoint_records_event(client, auth_headers, _agent_dependency_overrides) -> None:
    response = client.post(
        "/agent/v1/audit/events",
        headers=auth_headers("dq:rules:write"),
        json={
            "action": "run_agent",
            "endpoint": "/api/llm/v1/agent/run",
            "method": "POST",
            "actor_id": "alice",
            "correlation_id": "session-123",
            "agent_type": "general",
            "agent_source": "dq-llm",
            "agent_instance_id": "session-123",
            "request_origin": "dq-llm",
            "user_agent": "pytest",
            "response_type": "agent_response",
            "status_code": 200,
            "success": True,
            "details": {
                "session_id": "session-123",
                "prompt": "hello",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "run_agent"
    assert payload["endpoint"] == "/api/llm/v1/agent/run"
    assert payload["governance_context_ref"]["lineage_context_available"] is False

    list_response = client.get(
        "/agent/v1/audit/events?limit=10&offset=0",
        headers=auth_headers("dq:admin:read", "dq:rules:read"),
    )

    assert list_response.status_code == 200
    audit_events = list_response.json()["events"]
    assert any(event["action"] == "run_agent" for event in audit_events)


def test_agent_integration_contracts_list_includes_initial_allowlist(
    client,
    auth_headers,
    _agent_dependency_overrides,
) -> None:
    response = client.get(
        "/agent/v1/integrations/contracts",
        headers=_agent_headers(auth_headers, "dq:rules:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["allowlisted_platforms"] == ["mistral_ai", "microsoft_copilot"]
    platforms = {item["platform"] for item in payload["contracts"]}
    assert {"mistral_ai", "microsoft_copilot"}.issubset(platforms)
    assert all(item["allowlisted"] is True for item in payload["contracts"] if item["platform"] in {"mistral_ai", "microsoft_copilot"})


def test_agent_integration_dispatch_accepts_mistral_webhook_payload(
    client,
    auth_headers,
    _agent_dependency_overrides,
) -> None:
    response = client.post(
        "/agent/v1/integrations/dispatches",
        headers=_agent_headers(auth_headers, "dq:rules:write"),
        json={
            "platform": "mistral_ai",
            "dispatch_mode": "webhook",
            "event_type": "dq.alert.created",
            "webhook_url": "https://example.invalid/hooks/dq",
            "webhook_headers": {"x-test": "1"},
            "payload": {"delivery_id": "delivery-001"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "mistral_ai"
    assert payload["dispatch_mode"] == "webhook"
    assert payload["status"] == "accepted"
    assert payload["target"]["webhook_url"] == "https://example.invalid/hooks/dq"


def test_agent_integration_dispatch_rejects_unallowlisted_platform(
    client,
    auth_headers,
    _agent_dependency_overrides,
) -> None:
    response = client.post(
        "/agent/v1/integrations/dispatches",
        headers=_agent_headers(auth_headers, "dq:rules:write"),
        json={
            "platform": "slack",
            "dispatch_mode": "job",
            "event_type": "dq.alert.created",
            "job_name": "dq-alert-dispatch",
            "payload": {"delivery_id": "delivery-001"},
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "agent_platform_not_allowed"


def test_agent_decision_context_includes_governance_lineage_sla_and_remediation_trail(
    client,
    auth_headers,
    _agent_dependency_overrides,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RulesRepository:
        async def get_rule_by_id(self, rule_id: str):
            assert rule_id == "rule-001"
            return RuleEntity.model_validate(
                {
                    "id": "rule-001",
                    "name": "Customer completeness",
                    "description": "Ensure customer records are complete",
                    "expression": "count(*) > 0",
                    "dimension": "completeness",
                    "workspace": "workspace-a",
                    "createdByUserId": "user-1",
                    "tagIds": ["tag-1"],
                    "taxonomy": {
                        "type": "CHECK",
                        "severity": "high",
                        "domain": "Customer",
                        "owner": "data-steward@example.com",
                        "data_steward": "data-steward@example.com",
                        "domain_owner": "domain-owner@example.com",
                        "technical_owner": "engineer@example.com",
                        "sla_scope": "dataset",
                        "execution_target": "gx",
                    },
                }
            )

        async def list_rule_status_history(self, rule_id: str, limit: int = 100, offset: int = 0):
            assert rule_id == "rule-001"
            return [
                {
                    "from_status": "draft",
                    "to_status": "active",
                    "changed_by": "data-steward@example.com",
                    "reason": "approved for triage",
                    "changed_at": "2026-06-01T00:00:00Z",
                }
            ]

    class _DataAssetRepository:
        def get_data_asset(self, asset_id: str):
            assert asset_id == "asset-001"
            return DataAssetEntity.model_validate(
                {
                    "id": "asset-001",
                    "name": "Customer dataset",
                    "description": "Customer records",
                    "workspace_id": "workspace-a",
                    "status": "active",
                    "business_context": {
                        "dataset_id": "dataset-001",
                        "data_product_id": "product-001",
                        "domain": "Customer",
                        "owner": "data-owner@example.com",
                        "purpose": "customer reporting",
                        "steward": "data-steward@example.com",
                        "criticality": "high",
                        "tags": ["pii", "customer"],
                        "business_definitions": ["Customer", "Customer profile"],
                        "lineage_references": ["lineage-001"],
                        "validation_suites": ["suite-001"],
                        "validation_plans": ["plan-001"],
                        "consumers": ["reporting"]
                    },
                }
            )

        def list_data_asset_lineage_snapshots(self, asset_id: str, limit: int = 20):
            assert asset_id == "asset-001"
            assert limit == 2
            return [
                DataAssetLineageSnapshotEntity.model_validate(
                    {
                        "id": "snapshot-001",
                        "data_asset_id": "asset-001",
                        "captured_at": "2026-06-01T00:00:00Z",
                        "captured_by": "pytest-agent",
                        "snapshot_kind": "lineage",
                        "lineage_json": {"upstream": ["source-1"]},
                        "business_context_overlay": {"domain": "Customer"},
                        "classification_view": {"classification": "internal"},
                        "anomaly_annotations": [{"kind": "volume", "severity": "warning", "summary": "Low volume"}],
                    }
                )
            ]

    class _SlaRepository:
        async def list_sla_slo_definitions(self, *, workspace_id: str | None = None, status: str | None = None, scope_kind: str | None = None, metric_kind: str | None = None):
            assert workspace_id == "workspace-a"
            assert status == "active"
            return [
                SlaSloDefinitionEntity.model_validate(
                    {
                        "id": "sla-001",
                        "workspace_id": "workspace-a",
                        "name": "Customer completeness target",
                        "description": "Keep completeness above target",
                        "scope_kind": "dataset",
                        "scope_id": "asset-001",
                        "metric_kind": "quality_score",
                        "threshold_value": 95,
                        "threshold_operator": "gte",
                        "lookback_amount": 30,
                        "lookback_unit": "day",
                        "lifecycle_status": "active",
                        "approval_status": "approved",
                    }
                )
            ]

    app.dependency_overrides[get_rules_repository] = lambda: _RulesRepository()
    app.dependency_overrides[get_data_asset_repository] = lambda: _DataAssetRepository()
    app.dependency_overrides[get_sla_slo_repository] = lambda: _SlaRepository()
    try:
        dispatch_response = client.post(
            "/agent/v1/integrations/dispatches",
            headers=_agent_headers(auth_headers, "dq:rules:write"),
            json={
                "platform": "mistral_ai",
                "dispatch_mode": "webhook",
                "event_type": "dq.alert.created",
                "webhook_url": "https://example.invalid/hooks/dq",
                "payload": {"delivery_id": "delivery-001"},
            },
        )
        assert dispatch_response.status_code == 200

        response = client.get(
            "/agent/v1/context/decisions/rule-001?data_asset_id=asset-001&recent_event_limit=5&lineage_snapshot_limit=2",
            headers=_agent_headers(auth_headers, "dq:rules:read"),
        )
    finally:
        app.dependency_overrides.pop(get_rules_repository, None)
        app.dependency_overrides.pop(get_data_asset_repository, None)
        app.dependency_overrides.pop(get_sla_slo_repository, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["rule_context"]["id"] == "rule-001"
    assert payload["governance_context"]["workspace_id"] == "workspace-a"
    assert payload["lineage_context"]["snapshot_count"] == 1
    assert payload["business_context"]["domain"] == "Customer"
    assert payload["sla_thresholds"][0]["threshold_value"] == 95
    assert payload["explanation_payload"]["evidence_counts"]["sla_threshold_count"] == 1
    assert payload["remediation_audit_trail"]["recent_events"]


def test_agent_audit_events_include_governance_metadata_and_context_refs(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
    _agent_dependency_overrides,
) -> None:
    """WS10-AC05: audit list is governance-aware with per-event explainability refs."""
    from app.api.v1.endpoints import agent as agent_endpoints

    async def _fake_validate_rules_batch(**kwargs):
        return {
            "run_id": "run-ac05-001",
            "results": [],
            "conflicts": [],
            "summary": {"total": 1, "valid": 1, "invalid": 0, "errors": 0, "warnings": 0},
        }

    monkeypatch.setattr(agent_endpoints.rules_endpoints, "validate_rules_batch", _fake_validate_rules_batch)

    # Fire an agent action that records rule_ids in details
    client.post(
        "/agent/v1/rules/execute-batch",
        headers=_agent_headers(auth_headers, "dq:rules:write"),
        json={"rule_ids": ["rule-ac05-001", "rule-ac05-002"], "workspace": "workspace-ac05"},
    )

    list_response = client.get(
        "/agent/v1/audit/events?limit=10&offset=0",
        headers=auth_headers("dq:admin:read", "dq:rules:read"),
    )

    assert list_response.status_code == 200
    payload = list_response.json()

    # governance_metadata must be present and carry policy + explainability refs
    gm = payload["governance_metadata"]
    assert gm["access_policy_default_action"] == "deny"
    assert "mistral_ai" in gm["allowed_platforms"]
    assert gm["governance_aware"] is True
    assert "{rule_id}" in gm["explainability_endpoint_template"]

    # each event must carry governance_context_ref
    assert len(payload["events"]) >= 1
    event = payload["events"][0]
    assert "governance_context_ref" in event
