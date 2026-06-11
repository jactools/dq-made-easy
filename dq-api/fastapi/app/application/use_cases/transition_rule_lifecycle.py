from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Callable

from fastapi import HTTPException

from app.domain.entities import rule_policy
from app.domain.interfaces import RulesRepository
from app.domain.status_governance import canonicalize_status
from app.domain.status_governance import get_status_model_definition


@dataclass(slots=True)
class TransitionRuleLifecycleCommand:
    rule_id: str
    lifecycle_status: str
    granted_scopes: list[str] | None = None
    changed_by: str | None = None
    reason: str | None = None


async def transition_rule_lifecycle(
    command: TransitionRuleLifecycleCommand,
    repository: RulesRepository,
    *,
    read_row_field: Callable[[object, str], Any] = rule_policy.read_row_field,
    derive_rule_lifecycle_status_from_row: Callable[[object], str] = rule_policy.derive_rule_lifecycle_status_from_row,
    is_transition_allowed: Callable[..., bool],
) -> dict[str, Any]:
    target_status = canonicalize_status(entity="rule_lifecycle", status=command.lifecycle_status)
    lifecycle_definition = get_status_model_definition("rule_lifecycle")
    supported_statuses = {item.value for item in lifecycle_definition[0]} if lifecycle_definition is not None else set()
    if target_status not in supported_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported lifecycle_status '{command.lifecycle_status}'",
        )

    rows = await repository.list_rule_records(
        workspace=None,
        include_deleted=False,
        is_template=False,
        limit=500,
        offset=0,
    )
    current_row = next(
        (row for row in rows if str(read_row_field(row, "id") or "") == str(command.rule_id)),
        None,
    )
    if current_row is None:
        raise HTTPException(status_code=404, detail=f"Rule '{command.rule_id}' not found")

    current_status = derive_rule_lifecycle_status_from_row(current_row)
    if current_status != target_status:
        granted_scopes = [str(scope).strip() for scope in command.granted_scopes or [] if str(scope).strip()]
        if not is_transition_allowed(
            entity="rule_lifecycle",
            from_status=current_status,
            to_status=target_status,
            granted_scopes=granted_scopes,
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Transition '{current_status}' -> '{target_status}' is not allowed",
            )

    try:
        payload = await repository.set_rule_lifecycle_status(
            command.rule_id,
            lifecycle_status=target_status,
            changed_by=command.changed_by,
            reason=command.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if payload is None:
        raise HTTPException(status_code=404, detail=f"Rule '{command.rule_id}' not found")
    return payload.to_payload()