
from pydantic import ConfigDict, Field
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class RuleUserView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    username: str
    display_name: str


class RuleTagView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    name: str


class RuleTaxonomyView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    type: str | None = None
    severity: str | None = None
    domain: str | None = None
    owner: str | None = None
    dataSteward: str | None = None
    domainOwner: str | None = None
    technicalOwner: str | None = None
    sla_scope: str | None = None
    execution_target: str | None = None


class RuleView(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_snake_alias, from_attributes=True)

    id: str
    name: str
    description: str | None = None
    comments: str | None = None
    expression: str
    dimension: str
    active: bool
    lifecycleStatus: str = "active"
    created_by_user_id: str
    tag_ids: list[str]
    manual_override_by: str | None = None
    manual_override_at: str | None = None
    checkType: str | None = None
    checkTypeParams: dict | None = None
    reusableJoinId: str | None = None
    reusableFilterIds: list[str] = Field(default_factory=list)
    dsl: dict | None = None
    taxonomy: RuleTaxonomyView = Field(default_factory=RuleTaxonomyView)
    pendingDeactivationRequested: bool = False

    created_by: RuleUserView | None = None
    tags: list[RuleTagView] = Field(default_factory=list)

    async def resolve_created_by(self, context):
        repository = context["rules_repository"]
        user = await repository.get_user_by_id(self.created_by_user_id)
        if user is None:
            return None
        return RuleUserView.model_validate(user)

    async def resolve_tags(self, context):
        repository = context["rules_repository"]
        tags = await repository.get_tags_by_ids(self.tag_ids)
        return [RuleTagView.model_validate(tag) for tag in tags]


class RuleStatusHistoryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ruleId: str
    action: str
    fromStatus: str | None = None
    toStatus: str
    changedBy: str | None = None
    changedAt: str
    reason: str | None = None
    details: dict | None = None
