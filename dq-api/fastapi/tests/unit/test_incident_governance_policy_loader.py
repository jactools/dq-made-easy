from app.application.services.incident_governance_policy_loader import (
    load_incident_governance_policy,
    resolve_incident_governance_resolution,
)


def test_load_incident_governance_policy_and_resolve_assignment() -> None:
    policy = load_incident_governance_policy(
        {
            "incident_governance": {
                "default_assigned_to": "dq-made-easy-support@jaccloud.nl",
                "default_escalation_label": "dq-made-easy-support",
                "rules": [
                    {
                        "incident_kinds": ["technical_run_error"],
                        "severities": ["high"],
                        "assigned_to": "engine-on-call",
                        "escalation_label": "engine-on-call",
                        "escalate_after_minutes": 15,
                    },
                    {
                        "incidentKinds": ["functional_violation"],
                        "workspaceIds": ["ws-2"],
                        "assignedTo": "data-governance",
                        "escalationLabel": "governance-triage",
                        "escalateAfterMinutes": 60,
                    },
                ],
            }
        }
    )

    assert policy is not None
    assert policy.defaultAssignedTo == "dq-made-easy-support@jaccloud.nl"
    assert len(policy.rules) == 2

    technical = resolve_incident_governance_resolution(
        {"incidentGovernance": policy.model_dump(by_alias=True)},
        incident_kind="technical_run_error",
        severity="high",
        workspace_id="ws-1",
        scope_kind="data_asset",
    )
    assert technical.assignedTo == "engine-on-call"
    assert technical.escalationLabel == "engine-on-call"
    assert technical.escalateAfterMinutes == 15

    functional = resolve_incident_governance_resolution(
        {"incidentGovernance": policy.model_dump(by_alias=True)},
        incident_kind="functional_violation",
        severity="medium",
        workspace_id="ws-2",
        scope_kind="data_asset",
    )
    assert functional.assignedTo == "data-governance"
    assert functional.escalationLabel == "governance-triage"
    assert functional.escalateAfterMinutes == 60
