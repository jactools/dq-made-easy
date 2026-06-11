from __future__ import annotations

from app.core.dependencies import get_app_config_repository
from app.infrastructure.repositories import InMemoryAppConfigRepository


def test_put_app_config_updates_status_transition_policy(client, auth_headers) -> None:
    repository = InMemoryAppConfigRepository()
    client.app.dependency_overrides[get_app_config_repository] = lambda: repository

    try:
        response = client.put(
            "/api/system/v1/app-config",
            headers=auth_headers("dq:config:manage"),
            json={
                "status_governance": {
                    "rule": {
                        "transitions": [
                            {
                                "from_status": "draft",
                                "to_status": "testing",
                                "label": "Begin QA",
                                "required_any_scopes": ["dq:rules:test"],
                            }
                        ]
                    },
                    "run_plan": {
                        "transitions": [
                            {
                                "from_status": "inactive",
                                "to_status": "activation-requested",
                                "label": "Request Activation",
                                "required_any_scopes": ["dq:rules:write"],
                            }
                        ]
                    },
                    "rule_lifecycle": {
                        "transitions": [
                            {
                                "from_status": "active",
                                "to_status": "deprecated",
                                "label": "Deprecate",
                                "required_any_scopes": ["dq:rules:write"],
                            }
                        ]
                    }
                },
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status_governance"]["rule"]["transitions"][0]["label"] == "Begin QA"

        model_response = client.get(
            "/api/rulebuilder/v1/governance/status-models/rule",
            headers=auth_headers("dq:rules:read"),
        )
        assert model_response.status_code == 200
        model = model_response.json()
        assert any(transition["label"] == "Begin QA" for transition in model["transitions"])

        run_plan_model_response = client.get(
            "/api/rulebuilder/v1/governance/status-models/run_plan",
            headers=auth_headers("dq:rules:read"),
        )
        assert run_plan_model_response.status_code == 200
        run_plan_model = run_plan_model_response.json()
        assert run_plan_model["entity"] == "run_plan"
        assert any(transition["label"] == "Request Activation" for transition in run_plan_model["transitions"])

        lifecycle_model_response = client.get(
            "/api/rulebuilder/v1/governance/status-models/rule_lifecycle",
            headers=auth_headers("dq:rules:read"),
        )
        assert lifecycle_model_response.status_code == 200
        lifecycle_model = lifecycle_model_response.json()
        assert lifecycle_model["entity"] == "rule_lifecycle"
        assert any(transition["label"] == "Deprecate" for transition in lifecycle_model["transitions"])
    finally:
        client.app.dependency_overrides.clear()


def test_put_app_config_rejects_unknown_status_governance_keys(client, auth_headers) -> None:
    repository = InMemoryAppConfigRepository()
    client.app.dependency_overrides[get_app_config_repository] = lambda: repository

    try:
        response = client.put(
            "/api/system/v1/app-config",
            headers=auth_headers("dq:config:manage"),
            json={
                "status_governance": {
                    "unsupported": {
                        "transitions": [],
                    }
                },
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "status_governance.unsupported is not supported"

        config_response = client.get(
            "/api/system/v1/app-config",
            headers=auth_headers("dq:admin:read"),
        )
        assert config_response.status_code == 200
        assert config_response.json()["status_governance"] is None
    finally:
        client.app.dependency_overrides.clear()
