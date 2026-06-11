from typing import Protocol

from app.domain.entities.approvals import ApprovalAuditEntity, ApprovalEntity


class ApprovalsRepository(Protocol):
    def list_approvals(
        self,
        workspace_id: str | None = None,
        business_key: str | None = None,
        request_type: str | None = None,
        status: str | None = None,
        requester_id: str | None = None,
        exclude_requester_id: str | None = None,
        query: str | None = None,
    ) -> list[ApprovalEntity]: ...

    def create_approval(self, payload: dict, actor_id: str | None = None) -> ApprovalEntity: ...

    def update_approval(self, approval_id: str, payload: dict, actor_id: str | None = None) -> ApprovalEntity | None: ...

    def delete_approval(self, approval_id: str, actor_id: str | None = None) -> ApprovalEntity | None: ...

    def list_approval_audit(self) -> list[ApprovalAuditEntity]: ...

    def append_audit_event(
        self,
        *,
        approval_id: str,
        action: str,
        actor_id: str | None,
        details: dict,
    ) -> ApprovalAuditEntity:
        ...