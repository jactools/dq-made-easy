from __future__ import annotations

import asyncio

import pytest

from app.api.v1.schemas.ontology_view import OntologyGraphProjectionRequestView
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_dq_result_event_repository
from app.core.dependencies import get_incident_repository
from app.core.dependencies import get_ontology_graph_repository
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_validation_run_plan_repository
from app.domain.entities import AttributeCatalogEntity
from app.domain.entities import DataObjectCatalogEntity
from app.domain.entities import DataObjectVersionEntity
from app.domain.entities import DataProductEntity
from app.domain.entities import DataSetEntity
from app.domain.entities import DqResultCorrelationEntity
from app.domain.entities import DqResultDatasetEntity
from app.domain.entities import DqResultEventEntity
from app.domain.entities import DqResultRuleEntity
from app.domain.entities import DqResultRunOutcomeEntity
from app.domain.entities import IncidentEntity
from app.domain.entities import OntologyGraphSnapshotEntity
from app.domain.entities import RuleRecordEntity
from app.domain.entities import RuleTaxonomyEntity
from app.domain.entities import ValidationRunPlanEntity
from app.domain.entities import ValidationRunPlanScopeSelectorEntity
from app.infrastructure.repositories.in_memory_ontology_graph_repository import InMemoryOntologyGraphRepository
from app.main import app


class _FakeDataCatalogRepository:
    def __init__(self) -> None:
        self.data_product = DataProductEntity(
            id="prod-1",
            name="Retail Banking Product",
            workspace_id="retail-banking",
            business_key="retail-banking-product",
            tags=["priority"],
        )
        self.data_set = DataSetEntity(
            id="set-1",
            product_id="prod-1",
            name="Customer Dataset",
            workspace_id="retail-banking",
            business_key="customer-dataset",
            tags=["priority"],
        )
        self.data_object = DataObjectCatalogEntity(
            id="obj-1",
            dataset_id="set-1",
            name="Customer Object",
            latest_version_id="ver-1",
            business_key="customer-object",
            tags=["priority"],
        )
        self.data_object_version = DataObjectVersionEntity(
            id="ver-1",
            data_object_id="obj-1",
            version=1,
            schema_hash="schema-hash-1",
            attribute_count=1,
            tags=["priority"],
        )
        self.attribute = AttributeCatalogEntity(
            id="attr-1",
            name="customer_id",
            type="string",
            data_object_id="obj-1",
            version_id="ver-1",
            workspace_id="retail-banking",
            source_name="Customer Object",
            source_version_label="v1",
            definition_id="def.customer_id",
            tags=["priority"],
        )

    def list_data_products(self, workspace: str | None = None):
        if workspace and workspace != self.data_product.workspace_id:
            return []
        return [self.data_product]

    def list_data_sets(self, product_id: str | None = None, workspace: str | None = None):
        if product_id and product_id != self.data_set.product_id:
            return []
        if workspace and workspace != self.data_set.workspace_id:
            return []
        return [self.data_set]

    def list_data_objects_catalog(self, data_set_id: str | None = None):
        if data_set_id and data_set_id != self.data_object.dataset_id:
            return []
        return [self.data_object]

    def list_data_object_versions(self, object_id: str | None = None):
        if object_id and object_id != self.data_object_version.data_object_id:
            return []
        return [self.data_object_version]

    def list_attributes_catalog(self, version_id: str | None = None):
        if version_id and version_id != self.attribute.version_id:
            return []
        return [self.attribute]


class _FakeRulesRepository:
    def __init__(self) -> None:
        self.rule = RuleRecordEntity(
            id="rule-1",
            name="Customer ID present",
            expression="customer_id IS NOT NULL",
            dimension="completeness",
            workspace="retail-banking",
            created_by="data.steward@example.com",
            tagIds=["priority"],
            taxonomy=RuleTaxonomyEntity(domain="prod-1", owner="data.steward@example.com"),
        )

    async def list_rule_records(self, workspace: str | None = None, include_deleted: bool = False, is_template: bool | None = None, query: str | None = None, limit: int = 200, offset: int = 0):
        if workspace and workspace != self.rule.workspace:
            return []
        return [self.rule]


class _FakeValidationRunPlanRepository:
    def __init__(self) -> None:
        self.plan = ValidationRunPlanEntity(
            runPlanId="plan-1",
            businessKey="customer-plan",
            workspaceId="retail-banking",
            scopeSelector=ValidationRunPlanScopeSelectorEntity(
                workspaceId="retail-banking",
                dataProductId="prod-1",
                tagIds=["priority"],
            ),
            planningMode="manual",
            status="draft",
            createdAt="2026-05-30T10:00:00Z",
            updatedAt="2026-05-30T10:00:00Z",
        )

    async def list_plans(self, *, workspace_id: str | None = None, business_key: str | None = None, status: str | None = None, artifact_id: str | None = None):
        if workspace_id and workspace_id != self.plan.workspaceId:
            return []
        return [self.plan]


class _FakeDqResultEventRepository:
    def __init__(self) -> None:
        self.event = DqResultEventEntity(
            emittedAt="2026-05-30T10:01:00Z",
            severity="high",
            dataset=DqResultDatasetEntity(
                id="dataset-1",
                name="Customer Dataset",
                workspaceId="retail-banking",
                dataProductId="prod-1",
                dataObjectId="obj-1",
                dataObjectVersionId="ver-1",
            ),
            rule=DqResultRuleEntity(
                id="rule-1",
                name="Customer ID present",
                workspaceId="retail-banking",
                versionId="rule-version-1",
                versionNumber=1,
            ),
            runOutcome=DqResultRunOutcomeEntity(
                status="failed",
                result="failed",
                passed=False,
                score=0,
                scoreLabel="quality_score",
                observedAt="2026-05-30T10:01:00Z",
                message="customer_id is missing",
            ),
            correlation=DqResultCorrelationEntity(
                correlationId="corr-1",
                runId="run-1",
                requestId="request-1",
                queueMessageId="queue-1",
                traceId="trace-1",
                sourceSystem="gx-worker",
            ),
        )

    async def list_result_events(self, *, rule_id: str | None = None, dataset_id: str | None = None, domain_id: str | None = None, data_product_id: str | None = None, severity: str | None = None, status: str | None = None, emitted_after: str | None = None, emitted_before: str | None = None, limit: int = 100, offset: int = 0):
        return [self.event]


class _FakeIncidentRepository:
    def __init__(self) -> None:
        self.incident = IncidentEntity(
            id="incident-1",
            incident_kind="technical_run_error",
            title="GX worker failed",
            description="The worker stopped after the failed DQ run",
            run_id="run-1",
            workspace_id="retail-banking",
            source_correlation_id="corr-1",
            created_at="2026-05-30T10:02:00Z",
        )

    def list_incidents(self, *, workspace_id: str | None = None, incident_kind: str | None = None, status: str | None = None, run_id: str | None = None, limit: int = 50, offset: int = 0):
        if workspace_id and workspace_id != self.incident.workspace_id:
            return []
        return [self.incident]


@pytest.fixture
def ontology_graph_repository() -> InMemoryOntologyGraphRepository:
    return InMemoryOntologyGraphRepository()


@pytest.fixture
def data_catalog_repository() -> _FakeDataCatalogRepository:
    return _FakeDataCatalogRepository()


@pytest.fixture
def rules_repository() -> _FakeRulesRepository:
    return _FakeRulesRepository()


@pytest.fixture
def validation_run_plan_repository() -> _FakeValidationRunPlanRepository:
    return _FakeValidationRunPlanRepository()


@pytest.fixture
def dq_result_event_repository() -> _FakeDqResultEventRepository:
    return _FakeDqResultEventRepository()


@pytest.fixture
def incident_repository() -> _FakeIncidentRepository:
    return _FakeIncidentRepository()


@pytest.fixture(autouse=True)
def override_ontology_projection_dependencies(
    data_catalog_repository: _FakeDataCatalogRepository,
    rules_repository: _FakeRulesRepository,
    validation_run_plan_repository: _FakeValidationRunPlanRepository,
    dq_result_event_repository: _FakeDqResultEventRepository,
    incident_repository: _FakeIncidentRepository,
    ontology_graph_repository: InMemoryOntologyGraphRepository,
) -> None:
    app.dependency_overrides[get_data_catalog_repository] = lambda: data_catalog_repository
    app.dependency_overrides[get_rules_repository] = lambda: rules_repository
    app.dependency_overrides[get_validation_run_plan_repository] = lambda: validation_run_plan_repository
    app.dependency_overrides[get_dq_result_event_repository] = lambda: dq_result_event_repository
    app.dependency_overrides[get_incident_repository] = lambda: incident_repository
    app.dependency_overrides[get_ontology_graph_repository] = lambda: ontology_graph_repository
    yield
    app.dependency_overrides.pop(get_data_catalog_repository, None)
    app.dependency_overrides.pop(get_rules_repository, None)
    app.dependency_overrides.pop(get_validation_run_plan_repository, None)
    app.dependency_overrides.pop(get_dq_result_event_repository, None)
    app.dependency_overrides.pop(get_incident_repository, None)
    app.dependency_overrides.pop(get_ontology_graph_repository, None)


def test_project_ontology_graph_persists_snapshot(client, auth_headers, ontology_graph_repository) -> None:
    response = client.post(
        "/api/data-catalog/v1/ontology/graph/project",
        json={"workspace_id": "retail-banking", "data_product_id": "prod-1", "captured_by": "data.steward@example.com"},
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["graph_id"] == "dq-made-easy-domain-knowledge-graph"
    assert payload["snapshot"]["workspace_id"] == "retail-banking"
    assert payload["snapshot"]["data_product_id"] == "prod-1"
    assert payload["snapshot"]["node_count"] > 0
    assert payload["snapshot"]["edge_count"] > 0
    assert any(node["node_id"] == "data_product:prod-1" for node in payload["graph"]["nodes"])
    assert any(node["node_id"] == "validation_plan:plan-1" for node in payload["graph"]["nodes"])
    assert any(edge["relation_type"] == "produces_dq_outcome" for edge in payload["graph"]["edges"])
    assert any(edge["relation_type"] == "supports_validation_plan" for edge in payload["graph"]["edges"])

    persisted_snapshot = asyncio.run(ontology_graph_repository.get_latest_ontology_graph_snapshot(
        graph_id="dq-made-easy-domain-knowledge-graph",
        workspace_id="retail-banking",
        data_product_id="prod-1",
    ))
    assert persisted_snapshot is not None
    assert persisted_snapshot.node_count == payload["snapshot"]["node_count"]
    assert persisted_snapshot.edge_count == payload["snapshot"]["edge_count"]
    assert persisted_snapshot.graph_json["graph_id"] == "dq-made-easy-domain-knowledge-graph"


def test_query_ontology_graph_filters_seeded_projection(client, auth_headers) -> None:
    project_response = client.post(
        "/api/data-catalog/v1/ontology/graph/project",
        json={"workspace_id": "retail-banking", "data_product_id": "prod-1", "captured_by": "data.steward@example.com"},
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert project_response.status_code == 200

    query_response = client.post(
        "/api/data-catalog/v1/ontology/graph/query",
        json={
            "workspace_id": "retail-banking",
            "data_product_id": "prod-1",
            "node_types": ["rule"],
            "label_contains": "Customer",
        },
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert query_response.status_code == 200
    payload = query_response.json()
    assert payload["snapshot"]["graph_id"] == "dq-made-easy-domain-knowledge-graph"
    assert payload["matched_node_ids"] == ["rule:rule-1"]
    assert payload["graph"]["node_count"] == 1
    assert payload["graph"]["edge_count"] == 0
    assert payload["query_summary"]["matched_node_count"] == 1


def test_traverse_ontology_graph_discovers_impact_path(client, auth_headers) -> None:
    project_response = client.post(
        "/api/data-catalog/v1/ontology/graph/project",
        json={"workspace_id": "retail-banking", "data_product_id": "prod-1", "captured_by": "data.steward@example.com"},
        headers=auth_headers("dq:data_catalog:read"),
    )
    assert project_response.status_code == 200

    traverse_response = client.post(
        "/api/data-catalog/v1/ontology/graph/traverse",
        json={
            "workspace_id": "retail-banking",
            "data_product_id": "prod-1",
            "start_node_id": "data_product:prod-1",
            "max_depth": 4,
            "direction": "outbound",
        },
        headers=auth_headers("dq:data_catalog:read"),
    )

    assert traverse_response.status_code == 200
    payload = traverse_response.json()
    assert payload["start_node_id"] == "data_product:prod-1"
    assert "incident:incident-1" in payload["visited_node_ids"]
    assert any(edge["relation_type"] == "impacts_incident" for edge in payload["graph"]["edges"])
    assert payload["node_depths"]["incident:incident-1"] >= 2
