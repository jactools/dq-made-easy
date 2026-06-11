from app.application.services.status_governance_policy_loader import set_status_model_policy_from_source
from app.domain.status_governance import canonicalize_status, get_status_model_definition, is_transition_allowed, normalize_status


def test_normalize_and_canonicalize_and_transition():
    assert normalize_status("PENDING") == "pending"
    assert canonicalize_status(entity="rule", status="pending") == "pending-approval"
    assert canonicalize_status(entity="rule", status="declined") == "rejected"

    # Draft -> testing requires dq:rules:test or dq:rules:write
    assert is_transition_allowed(entity="rule", from_status="draft", to_status="testing", granted_scopes=["dq:rules:test"]) is True
    assert is_transition_allowed(entity="rule", from_status="draft", to_status="testing", granted_scopes=[]) is False


def test_set_status_model_policy_from_source_loads_snake_case_transition_payloads():
    set_status_model_policy_from_source(
        {
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
                }
            }
        }
    )

    _, transitions = get_status_model_definition("rule") or ([], [])
    assert len(transitions) == 1
    assert transitions[0].label == "Begin QA"
    assert transitions[0].requiredAnyScopes == ["dq:rules:test"]

    set_status_model_policy_from_source({})
