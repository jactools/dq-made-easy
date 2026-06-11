from fastapi import HTTPException

from app.domain.entities import RuleEntity
from app.domain.interfaces import RulesRepository


async def get_rule_details(rule_id: str, repository: RulesRepository) -> RuleEntity:
    rule = await repository.get_rule_by_id(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    return rule
