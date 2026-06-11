from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

from app.domain.entities.rule_templates import RuleTemplateEntity
from app.domain.entities.rule_templates import RuleTemplatePackEntity
from app.domain.entities.rule_templates import RuleTemplateResolutionEntity
from app.domain.entities.rule_templates import list_rule_template_packs as list_rule_template_packs_entity
from app.domain.entities.rule_templates import list_rule_templates as list_rule_templates_entity
from app.domain.entities.rule_templates import resolve_rule_template as resolve_rule_template_entity


@dataclass(slots=True)
class ListRuleTemplatesQuery:
    pack_id: str | None = None
    dimension: str | None = None


@dataclass(slots=True)
class ResolveRuleTemplateCommand:
    template_id: str
    overrides: dict[str, Any] = field(default_factory=dict)


async def list_rule_template_packs() -> list[RuleTemplatePackEntity]:
    return list_rule_template_packs_entity()


async def list_rule_templates(query: ListRuleTemplatesQuery) -> list[RuleTemplateEntity]:
    try:
        return list_rule_templates_entity(pack_id=query.pack_id, dimension=query.dimension)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def resolve_rule_template(command: ResolveRuleTemplateCommand) -> RuleTemplateResolutionEntity:
    try:
        return resolve_rule_template_entity(command.template_id, command.overrides)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc