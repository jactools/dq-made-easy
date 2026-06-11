from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def sso_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('SSO_ENABLED', 'true')
    monkeypatch.setenv('SSO_PUBLIC_ISSUER_URL', 'http://keycloak.local:8080/realms/jaccloud')
    monkeypatch.setenv('SSO_INTERNAL_ISSUER_URL', 'http://keycloak.local:8080/realms/jaccloud')
    monkeypatch.setenv('SSO_CLIENT_ID', 'dq-rules-ui')
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def auth_headers():
    def _auth_headers(*scopes: str) -> dict[str, str]:
        header = {'alg': 'none', 'typ': 'JWT'}
        payload = {
            'sub': 'user-123',
            'preferred_username': 'admin',
            'iss': 'http://keycloak.local:8080/realms/jaccloud',
            'aud': ['dq-rules-ui'],
            'scope': ' '.join(scopes),
        }

        def encode(value: dict) -> str:
            return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')

        token = f"{encode(header)}.{encode(payload)}.signature"
        return {
            'Authorization': f'Bearer {token}',
            'X-Kong-Request-Id': 'test-request-id',
        }

    return _auth_headers


def test_validate_check_type_draft_accepts_valid_quantile_threshold(client: TestClient, auth_headers) -> None:
    response = client.post(
        '/api/rulebuilder/v1/rules/validate/check-type',
        json={
            'check_type': 'THRESHOLD',
            'check_type_params': {
                'checkType': 'THRESHOLD',
                'attribute': 'fee_amount',
                'metric': 'quantile',
                'operator': 'gte',
                'threshold': 0.5,
                'quantile': 0.95,
            },
        },
        headers=auth_headers('dq:rules:write'),
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload['valid'] is True
    assert payload['message'] is None
    assert payload['field_errors'] == {}
    assert payload['normalized_check_type_params']['check_type'] == 'THRESHOLD'
    assert payload['normalized_check_type_params']['metric'] == 'quantile'


def test_validate_check_type_draft_rejects_invalid_quantile_operator(client: TestClient, auth_headers) -> None:
    response = client.post(
        '/api/rulebuilder/v1/rules/validate/check-type',
        json={
            'check_type': 'THRESHOLD',
            'check_type_params': {
                'checkType': 'THRESHOLD',
                'attribute': 'fee_amount',
                'metric': 'quantile',
                'operator': 'gt',
                'threshold': 0.5,
                'quantile': 0.95,
            },
        },
        headers=auth_headers('dq:rules:write'),
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload['valid'] is False
    assert 'only supports operators gte and lte' in payload['message']
    assert payload['field_errors']['operator'] == 'Use greater than or equal (>=) or less than or equal (<=).'
