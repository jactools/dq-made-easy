from collections.abc import Sequence
from typing import Any

from app.api.v1.schemas.approvals_view import ApprovalAuditView, ApprovalsPageView, ApprovalView
from app.domain.entities import ApprovalAuditEntity, ApprovalEntity


def resolve_approvals_page_view(payload: dict[str, Any]) -> ApprovalsPageView:
    return ApprovalsPageView.model_validate(payload)


def resolve_approval_view(entity: ApprovalEntity) -> ApprovalView:
    return ApprovalView.model_validate(entity)


def resolve_approval_audit_view(rows: Sequence[ApprovalAuditEntity]) -> list[ApprovalAuditView]:
    return [ApprovalAuditView.model_validate(row) for row in rows]
