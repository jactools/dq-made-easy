from __future__ import annotations

import pytest

from app.core.dependencies import get_gx_execution_run_repository
from app.infrastructure.repositories.in_memory_gx_execution_run_repository import InMemoryGxExecutionRunRepository
from app.main import app


@pytest.fixture(autouse=True)
def isolated_gx_reconciliation_run_dependencies() -> InMemoryGxExecutionRunRepository:
    run_repository = InMemoryGxExecutionRunRepository()
    app.dependency_overrides[get_gx_execution_run_repository] = lambda: run_repository

    yield run_repository

    app.dependency_overrides.pop(get_gx_execution_run_repository, None)


def _create_reconciliation_run_payload() -> dict[str, object]:
    return {
        'workspace_id': 'workspace-1',
        'left_datasource_id': 'left-feed',
        'right_datasource_id': 'right-feed',
        'left_datasource_name': 'Left feed',
        'right_datasource_name': 'Right feed',
        'left_datasource_type': 'postgres',
        'right_datasource_type': 'postgres',
        'reconciliation_params': {
            'check_type': 'RECONCILE',
            'left_data_object_version_id': 'dov-left',
            'right_data_object_version_id': 'dov-right',
            'join_keys': [
                {'left_attribute': 'account_id', 'right_attribute': 'account_id'},
            ],
            'comparisons': [
                {'left_attribute': 'status', 'right_attribute': 'status', 'mode': 'exact'},
            ],
        },
        'preview_left_rows': [
            {'account_id': 'acct-1', 'status': 'active'},
        ],
        'preview_right_rows': [
            {'account_id': 'acct-1', 'status': 'active'},
        ],
    }


@pytest.mark.anyio
async def test_create_and_list_reconciliation_runs_persists_history(client, auth_headers, isolated_gx_reconciliation_run_dependencies) -> None:
    create_response = client.post(
        '/api/rulebuilder/v1/gx/runs/reconciliation',
        json=_create_reconciliation_run_payload(),
        headers=auth_headers('dq:rules:write'),
    )

    assert create_response.status_code == 200
    created_run = create_response.json()
    assert created_run['status'] == 'pending'
    assert created_run['requested_by'] == 'user-admin'
    assert created_run['engine_target'] == 'pyspark'

    execution_contract = created_run['execution_contract']
    assert execution_contract.get('workspace_id') == 'workspace-1' or execution_contract.get('workspaceId') == 'workspace-1'
    assert execution_contract.get('workflow_type') == 'reconciliation' or execution_contract.get('workflowType') == 'reconciliation'

    conflict_response = client.post(
        '/api/rulebuilder/v1/gx/runs/reconciliation',
        json=_create_reconciliation_run_payload(),
        headers=auth_headers('dq:rules:write'),
    )

    assert conflict_response.status_code == 409
    conflict_payload = conflict_response.json()
    assert conflict_payload['detail']['error'] == 'reconciliation_datasource_busy'
    assert conflict_payload['detail']['active_run_id'] == created_run['id']

    list_response = client.get(
        '/api/rulebuilder/v1/gx/runs/reconciliation?workspaceId=workspace-1',
        headers=auth_headers('dq:rules:read'),
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload) == 1
    assert payload[0]['id'] == created_run['id']

    empty_response = client.get(
        '/api/rulebuilder/v1/gx/runs/reconciliation?workspaceId=workspace-2',
        headers=auth_headers('dq:rules:read'),
    )
    assert empty_response.status_code == 200
    assert empty_response.json() == []
