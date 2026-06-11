from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

from app.domain.interfaces import RulesRepository


@dataclass(slots=True)
class ValidateRuleEnrichedCommand:
    rule_id: str
    rule_version_id: str
    expression: str
    detected_aliases: list[str] = field(default_factory=list)
    unresolved_aliases: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    manual_alias_mappings: dict[str, str] = field(default_factory=dict)


async def validate_rule_enriched(command: ValidateRuleEnrichedCommand, repository: RulesRepository) -> dict[str, Any]:
    entity = await repository.get_rule_by_id(command.rule_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Rule '{command.rule_id}' not found")

    diagnostics: dict[str, dict[str, Any]] = {}
    catalog_sourced_aliases = 0
    manual_sourced_aliases = 0

    for alias in command.detected_aliases:
        if alias in command.manual_alias_mappings:
            manual_sourced_aliases += 1
            diagnostics[alias] = {
                "resolutionStatus": "resolved",
                "source": "manual",
                "resolvedTermName": command.manual_alias_mappings.get(alias),
                "resolvedDataType": None,
                "domain": None,
                "confidence": 1.0,
                "warning": None,
            }
        elif alias in command.unresolved_aliases:
            diagnostics[alias] = {
                "resolutionStatus": "unresolved",
                "source": "unresolved",
                "resolvedTermName": None,
                "resolvedDataType": None,
                "domain": None,
                "confidence": 0.0,
                "warning": "unresolved",
            }
        else:
            catalog_sourced_aliases += 1
            diagnostics[alias] = {
                "resolutionStatus": "resolved",
                "source": "catalog",
                "resolvedTermName": alias,
                "resolvedDataType": None,
                "domain": None,
                "confidence": 0.8,
                "warning": None,
            }

    return {
        "ruleId": command.rule_id,
        "ruleVersionId": command.rule_version_id,
        "isValid": len(command.unresolved_aliases) == 0,
        "unresolvedAliases": command.unresolved_aliases,
        "issues": command.issues,
        "diagnostics": diagnostics,
        "catalogAvailable": True,
        "lastSync": None,
        "stats": {
            "catalogSourcedAliases": catalog_sourced_aliases,
            "manualSourcedAliases": manual_sourced_aliases,
            "unresolvedCount": len(command.unresolved_aliases),
        },
    }