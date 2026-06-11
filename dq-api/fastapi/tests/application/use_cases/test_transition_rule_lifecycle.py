from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.application.use_cases.transition_rule_lifecycle import transition_rule_lifecycle
from app.application.use_cases.transition_rule_lifecycle import TransitionRuleLifecycleCommand
from app.domain.entities import build_rule_record_entity


pytestmark = pytest.mark.usefixtures("clone_payload")


def _run(coro):
    return asyncio.run(coro)


class _Repository:
    def __init__(self) -> None:
        self.row = build_rule_record_entity(
            {
                "id": "rule-1",
                "name": "Rule 1",
                "expression": "value > 0",
                "dimension": "validity",
                "active": False,
                "lifecycle_status": "active",
            }
        )
        self.transitions: list[dict[str, str | None]] = []

    async def list_rule_records(self, **kwargs):
        del kwargs
        return [self.row]

    async def set_rule_lifecycle_status(self, rule_id: str, *, lifecycle_status: str, changed_by: str | None, reason: str | None = None):
        assert rule_id == "rule-1"
        self.transitions.append(
            {
                "lifecycle_status": lifecycle_status,
                "changed_by": changed_by,
                "reason": reason,
            }
        )
        self.row = self.row.model_copy(update={"lifecycle_status": lifecycle_status})
        return self.row


def test_transition_rule_lifecycle_updates_rule_state() -> None:
    repository = _Repository()

    payload = _run(
        transition_rule_lifecycle(
            TransitionRuleLifecycleCommand(
                rule_id="rule-1",
                lifecycle_status="deprecated",
                granted_scopes=["dq:rules:write"],
                changed_by="user-admin",
                reason="Use the successor rule instead",
            ),
            repository,
            is_transition_allowed=lambda **kwargs: kwargs["to_status"] == "deprecated",
        )
    )

    assert payload["lifecycle_status"] == "deprecated"
    assert repository.transitions == [
        {
            "lifecycle_status": "deprecated",
            "changed_by": "user-admin",
            "reason": "Use the successor rule instead",
        }
    ]


def test_transition_rule_lifecycle_rejects_disallowed_transition() -> None:
    repository = _Repository()

    with pytest.raises(HTTPException, match="not allowed"):
        _run(
            transition_rule_lifecycle(
                TransitionRuleLifecycleCommand(
                    rule_id="rule-1",
                    lifecycle_status="retired",
                    granted_scopes=["dq:rules:read"],
                ),
                repository,
                is_transition_allowed=lambda **kwargs: False,
            )
        )