from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field

from app.api.v1.schemas.approvals_view import ApprovalsPageView
from app.api.v1.schemas.common_view import PaginationView
from app.api.v1.schemas.rule_view import RuleTaxonomyView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class GovernanceInboxRuleView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    name: str
    description: str | None = None
    comments: str | None = None
    expression: str
    dimension: str
    active: bool
    status: str
    lifecycleStatus: str
    workspace: str | None = None
    createdBy: str | None = None
    dataSteward: str | None = None
    domainOwner: str | None = None
    technicalOwner: str | None = None
    generated: bool = False
    isTemplate: bool = False
    templateId: str | None = None
    suggestionId: str | None = None
    checkType: str | None = None
    checkTypeParams: dict[str, Any] | None = None
    reusableJoinId: str | None = None
    reusableFilterIds: list[str] = Field(default_factory=list)
    tagIds: list[str] = Field(default_factory=list)
    joinConditions: list[dict[str, Any]] = Field(default_factory=list)
    aliasMappings: dict[str, Any] = Field(default_factory=dict)
    currentVersionId: str | None = None
    totalVersions: int | None = None
    versioningEnabled: bool | None = None
    versionCreatedAt: str | None = None
    versionUpdatedAt: str | None = None
    pendingDeactivationRequested: bool = False
    taxonomy: RuleTaxonomyView = Field(default_factory=RuleTaxonomyView)


class GovernanceInboxRulePageView(SnakeModel):
    data: list[GovernanceInboxRuleView]
    pagination: PaginationView


class GovernanceInboxView(SnakeModel):
    approvalInbox: ApprovalsPageView
    reassignmentInbox: GovernanceInboxRulePageView
    deprecationReviewInbox: GovernanceInboxRulePageView