from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Callable

from fastapi import HTTPException

from app.domain.entities import rule_policy
from app.domain.interfaces import RulesRepository


@dataclass(slots=True)
class RemoveRuleCommand:
    rule_id: str
    granted_scopes: list[str] | None = None
    removed_by: str | None = None


async def remove_rule(
    command: RemoveRuleCommand,
    repository: RulesRepository,
    *,
    read_row_field: Callable[[object, str], Any] = rule_policy.read_row_field,
    derive_rule_status_from_row: Callable[[object], str] = rule_policy.derive_rule_status_from_row,
    is_transition_allowed: Callable[..., bool],
) -> dict[str, Any]:
    rows = await repository.list_rule_records(
        workspace=None,
        include_deleted=True,
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

    current_status = derive_rule_status_from_row(current_row)
    granted_scopes = [str(scope).strip() for scope in command.granted_scopes or [] if str(scope).strip()]
    if not is_transition_allowed(
        entity="rule",
        from_status=current_status,
        to_status="removed",
        granted_scopes=granted_scopes,
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Transition '{current_status}' -> 'removed' is not allowed",
        )

    try:
        payload = await repository.soft_delete_rule_record(command.rule_id, removed_by=command.removed_by or "user-admin")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if payload is None:
        raise HTTPException(status_code=404, detail=f"Rule '{command.rule_id}' not found")
    return payload.to_payload()