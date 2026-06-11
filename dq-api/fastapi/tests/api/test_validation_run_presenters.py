from __future__ import annotations

from app.api.presenters.validation_runs import build_validation_run_item_payload
from app.api.presenters.validation_runs import build_validation_run_payload
from app.domain.entities.validation_run import ValidationRunEntity
from app.domain.entities.validation_run import ValidationRunItemEntity


def test_build_validation_run_payload_serializes_item_and_run_shapes() -> None:
    item = ValidationRunItemEntity(
        id="item-1",
        rule_id="rule-1",
        rule_name="Email Rule",
        rule_version_number=3,
        valid=False,
        errors=2,
        warnings=1,
        diagnostics=[{"code": "invalid_expression"}],
        conflicts=[{"type": "version_mismatch"}],
    )
    run = ValidationRunEntity(
        id="run-1",
        workspace="governance",
        triggered_by="user-1",
        run_at="2026-04-20T12:00:00Z",
        total=1,
        valid_count=0,
        invalid_count=1,
        status="completed",
        validation_items=[item],
    )

    item_payload = build_validation_run_item_payload(item)
    assert item_payload == {
        "id": "item-1",
        "ruleId": "rule-1",
        "ruleName": "Email Rule",
        "ruleVersionNumber": 3,
        "valid": False,
        "errors": 2,
        "warnings": 1,
        "diagnostics": [{"code": "invalid_expression"}],
        "conflicts": [{"type": "version_mismatch"}],
    }

    run_payload = build_validation_run_payload(run)
    assert run_payload == {
        "id": "run-1",
        "workspace": "governance",
        "triggeredBy": "user-1",
        "runAt": "2026-04-20T12:00:00Z",
        "total": 1,
        "validCount": 0,
        "invalidCount": 1,
        "status": "completed",
        "items": [item_payload],
    }
