from typing import Any

from pydantic import ConfigDict, Field

from app.api.v1.schemas.common_view import PaginationView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class ApprovalView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    businessKey: str | None = None
    ruleId: str
    effectiveStatus: str | None = None
    gxRunPlanId: str | None = None
    gxRunPlanVersionId: str | None = None
    status: str
    requesterId: str | None = None
    workspaceId: str = "default"
    requestType: str = "activation"
    effectiveAt: str | None = None
    comments: str | None = None
    commentThread: list[dict[str, Any]] = Field(default_factory=list)
    commentsLocked: bool = False
    removedCommentCount: int = 0
    requestedAt: str | None = None
    reviewedBy: str | None = None
    reviewedAt: str | None = None


class ApprovalAuditView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    approvalId: str
    action: str
    actorId: str | None = None
    timestamp: str
    details: dict = Field(default_factory=dict)


class ApprovalsPageView(SnakeModel):
    data: list[ApprovalView]
    pagination: PaginationView
