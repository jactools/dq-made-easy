from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.dependencies import get_admin_repository


class StubMonitorNotificationAdminRepository:
    def __init__(self) -> None:
        self.current_user = SimpleNamespace(
            id='user-1',
            name='Admin User',
            email='admin@example.com',
            roles=['admin'],
            granted_scopes=['dq:rules:read'],
            workspaces=['workspace-alpha'],
            workspace_roles=[
                SimpleNamespace(workspace_id='workspace-alpha', role='editor'),
                SimpleNamespace(workspace_id='workspace-beta', role='viewer'),
            ],
            preferences={
                'monitor_notification_preferences': [
                    {
                        'workspace_id': 'workspace-alpha',
                        'enabled': True,
                        'categories': ['drift'],
                        'channels': ['email'],
                    },
                    {
                        'workspace_id': 'workspace-restricted',
                        'enabled': True,
                        'categories': ['anomaly'],
                        'channels': ['in_app'],
                    },
                ],
                'notifications': {'emailOnApproval': True},
            },
            external_id=None,
        )

    def get_current_user(self, user_id, claims=None):
        return self.current_user

    def update_current_user(self, user_id, claims, payload):
        preferences = payload.get('preferences') if isinstance(payload, dict) else None
        self.current_user.preferences = dict(preferences or {})
        return self.current_user


@pytest.fixture()
def monitor_notification_repository():
    return StubMonitorNotificationAdminRepository()


@pytest.fixture(autouse=True)
def _override_admin_repository(monitor_notification_repository):
    from app.main import app

    app.dependency_overrides[get_admin_repository] = lambda: monitor_notification_repository
    yield
    app.dependency_overrides.pop(get_admin_repository, None)


def test_monitor_notification_preferences_round_trip(client, auth_headers, monitor_notification_repository):
    response = client.get(
        '/api/rulebuilder/v1/governance/monitor-notification-preferences',
        headers=auth_headers('dq:rules:read', sub='user-1', preferred_username='admin-user'),
    )

    assert response.status_code == 200
    body = response.json()
    assert body['accessible_workspace_ids'] == ['workspace-alpha', 'workspace-beta']
    assert body['available_categories'] == ['anomaly', 'drift', 'root_cause']
    assert body['available_channels'] == ['email', 'in_app', 'teams']
    assert body['summary']['workspace_count'] == 2
    assert body['summary']['workspace_preference_count'] == 2
    assert body['monitor_notification_preferences'] == [
        {
            'workspace_id': 'workspace-alpha',
            'enabled': True,
            'categories': ['drift'],
            'channels': ['email'],
        },
        {
            'workspace_id': 'workspace-beta',
            'enabled': False,
            'categories': [],
            'channels': [],
        },
    ]

    update_response = client.put(
        '/api/rulebuilder/v1/governance/monitor-notification-preferences',
        headers=auth_headers('dq:rules:write', sub='user-1', preferred_username='admin-user'),
        json={
            'monitor_notification_preferences': [
                {
                    'workspace_id': 'workspace-beta',
                    'enabled': True,
                    'categories': ['anomaly', 'drift', 'root_cause'],
                    'channels': ['email', 'in_app'],
                }
            ]
        },
    )

    assert update_response.status_code == 200
    update_body = update_response.json()
    assert update_body['monitor_notification_preferences'] == [
        {
            'workspace_id': 'workspace-alpha',
            'enabled': True,
            'categories': ['drift'],
            'channels': ['email'],
        },
        {
            'workspace_id': 'workspace-beta',
            'enabled': True,
            'categories': ['anomaly', 'drift', 'root_cause'],
            'channels': ['email', 'in_app'],
        },
    ]
    assert monitor_notification_repository.current_user.preferences['monitor_notification_preferences'] == [
        {
            'workspace_id': 'workspace-alpha',
            'enabled': True,
            'categories': ['drift'],
            'channels': ['email'],
        },
        {
            'workspace_id': 'workspace-beta',
            'enabled': True,
            'categories': ['anomaly', 'drift', 'root_cause'],
            'channels': ['email', 'in_app'],
        },
    ]


def test_monitor_notification_preferences_rejects_inaccessible_workspace(client, auth_headers):
    response = client.put(
        '/api/rulebuilder/v1/governance/monitor-notification-preferences',
        headers=auth_headers('dq:rules:write', sub='user-1', preferred_username='admin-user'),
        json={
            'monitor_notification_preferences': [
                {
                    'workspace_id': 'workspace-restricted',
                    'enabled': True,
                    'categories': ['anomaly'],
                    'channels': ['email'],
                }
            ]
        },
    )

    assert response.status_code == 403
    assert response.json()['detail']['error'] == 'workspace_access_denied'
    assert response.json()['detail']['workspace_ids'] == ['workspace-restricted']
