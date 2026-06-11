from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.domain.entities.gx_execution_run import build_gx_execution_run_create_entity
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_gx_execution_run_repository
from app.core.dependencies import get_rules_repository
from app.infrastructure.repositories.in_memory_gx_execution_run_repository import InMemoryGxExecutionRunRepository
from app.main import app


class _StubRulesRepository:
    def __init__(self) -> None:
        self._rules = {
            'rule-1': SimpleNamespace(id='rule-1', name='Customer Order Completeness'),
            'rule-2': SimpleNamespace(id='rule-2', name='Invoice Totals'),
        }

    async def get_rule_by_id(self, rule_id: str):
        return self._rules.get(rule_id)


class _StubDataCatalogRepository:
    def list_data_objects_catalog(self, data_set_id: str | None = None):
        return [
            SimpleNamespace(id='object-orders', name='Orders'),
            SimpleNamespace(id='object-customers', name='Customer Orders'),
            SimpleNamespace(id='object-invoices', name='Invoices'),
        ]

    def list_data_object_versions(self, object_id: str | None = None):
        versions = [
            SimpleNamespace(id='dov-777', data_object_id='object-orders', version=7),
            SimpleNamespace(id='dov-778', data_object_id='object-customers', version=8),
            SimpleNamespace(id='dov-900', data_object_id='object-invoices', version=9),
        ]
        if object_id is None:
            return versions
        return [version for version in versions if version.data_object_id == object_id]


@pytest.fixture(autouse=True)
def isolated_gx_recent_runs_dependencies() -> InMemoryGxExecutionRunRepository:
    run_repository = InMemoryGxExecutionRunRepository()
    rules_repository = _StubRulesRepository()
    data_catalog_repository = _StubDataCatalogRepository()

    app.dependency_overrides[get_gx_execution_run_repository] = lambda: run_repository
    app.dependency_overrides[get_rules_repository] = lambda: rules_repository
    app.dependency_overrides[get_data_catalog_repository] = lambda: data_catalog_repository

    yield run_repository

    app.dependency_overrides.pop(get_gx_execution_run_repository, None)
    app.dependency_overrides.pop(get_rules_repository, None)
    app.dependency_overrides.pop(get_data_catalog_repository, None)


@pytest.mark.anyio
async def test_recent_runs_endpoint_filters_by_rule_and_data_object_name(client, auth_headers, isolated_gx_recent_runs_dependencies) -> None:
    run_repository = isolated_gx_recent_runs_dependencies
    recent_submitted_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    stale_submitted_at = (datetime.now(UTC) - timedelta(days=14)).isoformat()

    await run_repository.create_run(
        build_gx_execution_run_create_entity(
            {
                'run_id': 'run-123',
                'suite_id': 'gx_suite_8f40b9ea',
                'suite_version': 3,
                'rule_id': 'rule-1',
                'rule_version_id': 'rule-version-9',
                'correlation_id': 'corr-123',
                'requested_by': 'user-admin',
                'engine_target': 'pyspark',
                'execution_shape': 'join_pair',
                'status': 'running',
                'submitted_at': recent_submitted_at,
                'execution_contract': {
                    'engineTarget': 'pyspark',
                    'executionShape': 'join_pair',
                    'traceability': {
                        'ruleId': 'rule-1',
                        'ruleVersionId': 'rule-version-9',
                        'gxSuiteId': 'gx_suite_8f40b9ea',
                        'gxSuiteVersion': 3,
                        'dataObjectVersionId': 'dov-777',
                    },
                    'sourceMaterialization': {
                        'landingZoneArtifactId': 'lz-artifact-1',
                        'landingZoneVersionId': 'lz-version-1',
                        'outputLocation': 's3://landing-zone/gx/run-123',
                        'joinType': 'inner',
                        'joinKeys': ['order_id'],
                        'leftSource': {
                            'dataObjectId': 'object-orders',
                            'dataObjectVersionId': 'dov-777',
                            'datasetId': 'dataset-a',
                            'dataProductId': None,
                        },
                        'rightSource': {
                            'dataObjectId': 'object-customers',
                            'dataObjectVersionId': 'dov-778',
                            'datasetId': 'dataset-b',
                            'dataProductId': None,
                        },
                    },
                },
                'handoff_payload': {'queue_key': 'dq-gx:execution-dispatch'},
            }
        )
    )

    await run_repository.create_run(
        build_gx_execution_run_create_entity(
            {
                'run_id': 'run-999',
                'suite_id': 'gx_suite_other',
                'suite_version': 1,
                'rule_id': 'rule-2',
                'rule_version_id': 'rule-version-2',
                'correlation_id': 'corr-999',
                'requested_by': 'user-other',
                'engine_target': 'pyspark',
                'execution_shape': 'single_object',
                'status': 'pending',
                'submitted_at': stale_submitted_at,
                'execution_contract': {
                    'engineTarget': 'pyspark',
                    'executionShape': 'single_object',
                    'traceability': {
                        'ruleId': 'rule-2',
                        'ruleVersionId': 'rule-version-2',
                        'gxSuiteId': 'gx_suite_other',
                        'gxSuiteVersion': 1,
                        'dataObjectVersionId': 'dov-900',
                    },
                },
            }
        )
    )

    response = client.get(
        '/api/rulebuilder/v1/gx/runs?lookbackAmount=7&lookbackUnit=days&ruleName=Customer%20Order&dataObjectName=Orders&search=corr-123',
        headers=auth_headers('dq:rules:read'),
    )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 1

    row = payload[0]
    assert row['id'] == 'run-123'
    assert row['rule_name'] == 'Customer Order Completeness'
    assert row['data_object_names'] == ['Orders', 'Customer Orders']
    assert row['status'] == 'running'