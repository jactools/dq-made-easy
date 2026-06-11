from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.domain.interfaces import RulesRepository


@dataclass(slots=True)
class SaveRuleTemplateCommand:
    rule_id: str
    template_name: str
    template_description: str | None = None
    created_by: str | None = None


@dataclass(slots=True)
class RollbackRuleCommand:
    rule_id: str
    to_version_id: str
    reason: str
    requested_by_user_id: str
    skip_approval: bool = False
    tags: list[str] | None = None


@dataclass(slots=True)
class UpdateRuleVersionTagsCommand:
    rule_id: str
    version_id: str
    tags: list[str]
    updated_by_user_id: str


@dataclass(slots=True)
class MarkRuleVersionForRollbackCommand:
    rule_id: str
    version_id: str
    marked: bool


async def save_rule_as_template(command: SaveRuleTemplateCommand, repository: RulesRepository) -> dict[str, Any]:
    payload = await repository.save_rule_as_template(
        rule_id=command.rule_id,
        template_name=command.template_name,
        template_description=command.template_description,
        created_by=command.created_by,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Rule '{command.rule_id}' not found")
    return payload


async def rollback_rule(command: RollbackRuleCommand, repository: RulesRepository) -> dict[str, Any]:
    to_version_id = command.to_version_id.strip()
    reason = command.reason.strip()
    if not to_version_id or not reason:
        raise HTTPException(status_code=400, detail="toVersionId and reason are required")

    try:
        payload = await repository.execute_rule_rollback(
            rule_id=command.rule_id,
            to_version_id=to_version_id,
            reason=reason,
            requested_by_user_id=command.requested_by_user_id,
            skip_approval=command.skip_approval,
            tags=command.tags,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload is None:
        raise HTTPException(status_code=404, detail=f"Rule '{command.rule_id}' not found")
    return payload


async def update_rule_version_tags(command: UpdateRuleVersionTagsCommand, repository: RulesRepository) -> dict[str, Any]:
    payload = await repository.update_rule_version_tags(
        rule_id=command.rule_id,
        version_id=command.version_id,
        tags=command.tags,
        updated_by_user_id=command.updated_by_user_id,
    )
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version '{command.version_id}' not found for rule '{command.rule_id}'",
        )
    return payload


async def mark_rule_version_for_rollback(
    command: MarkRuleVersionForRollbackCommand,
    repository: RulesRepository,
) -> dict[str, Any]:
    payload = await repository.mark_rule_version_for_rollback(
        rule_id=command.rule_id,
        version_id=command.version_id,
        marked=command.marked,
    )
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version '{command.version_id}' not found for rule '{command.rule_id}'",
        )
    return payload