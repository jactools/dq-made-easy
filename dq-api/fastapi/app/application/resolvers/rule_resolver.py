from pydantic_resolve import Resolver

from app.api.v1.schemas.rule_view import RuleView
from app.domain.entities import RuleEntity
from app.domain.interfaces import RulesRepository


async def resolve_rule_view(rule: RuleEntity, repository: RulesRepository) -> RuleView:
    unresolved_view = RuleView.model_validate(
        {
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "comments": rule.comments,
            "expression": rule.expression,
            "dimension": rule.dimension,
            "active": rule.active,
            "lifecycleStatus": rule.lifecycle_status,
            "created_by_user_id": rule.created_by_user_id,
            "tag_ids": rule.tag_ids,
            "manual_override_by": rule.manual_override_by,
            "manual_override_at": rule.manual_override_at,
            "checkType": rule.check_type,
            "checkTypeParams": rule.check_type_params,
            "reusableJoinId": rule.reusable_join_id,
            "reusableFilterIds": list(rule.reusable_filter_ids),
            "dsl": rule.dsl,
            "taxonomy": rule.taxonomy.model_dump(mode="python"),
        }
    )

    return await Resolver(context={"rules_repository": repository}).resolve(unresolved_view)
