from app.domain.entities.approvals import ApprovalAuditEntity, ApprovalEntity
from app.domain.comment_governance import coerce_bool
from app.domain.entities.approvals import build_approval_comment_governance
from app.domain.entities.approvals import build_approval_comment_thread
from app.domain.interfaces.v1.approvals_repository import ApprovalsRepository
from app.infrastructure.repositories.in_memory_test_data import approvals_seed_data


def _normalize_request_type(value: object) -> str:
    normalized = str(value or "activation").strip().lower().replace("-", "_")
    return normalized or "activation"


def _payload_value(payload: dict, *keys: str, default: object = None) -> object:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def _payload_text(payload: dict, *keys: str, default: str | None = None) -> str | None:
    value = _payload_value(payload, *keys, default=default)
    if value is None:
        return None
    text = str(value).strip()
    return text or default


def _reject_camel_case_approval_keys(payload: dict, context: str) -> None:
    camel_case_keys = {"ruleId", "effectiveStatus", "gxRunPlanId", "gxRunPlanVersionId", "workspaceId", "requestType", "requesterId", "effectiveAt"}
    unexpected = sorted(key for key in payload if key in camel_case_keys)
    if unexpected:
        raise ValueError(f"{context} must use snake_case keys only: {', '.join(unexpected)}")


def _derive_effective_status(request_type: str) -> str | None:
    if request_type == "activation":
        return "activated"
    if request_type == "deactivation":
        return "deactivated"
    return None


def _normalize_status(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _approval_matches_filters(
    approval: dict[str, object],
    *,
    request_type: str | None,
    status: str | None,
    requester_id: str | None,
    exclude_requester_id: str | None,
    query: str | None,
) -> bool:
    normalized_request_type = _normalize_request_type(request_type) if request_type is not None else None
    normalized_status = _normalize_status(status)
    normalized_requester_id = str(requester_id or "").strip()
    normalized_exclude_requester_id = str(exclude_requester_id or "").strip()
    normalized_query = str(query or "").strip().lower()

    current_request_type = _normalize_request_type(
        _payload_value(approval, "requestType", "request_type", default="activation")
    )
    current_status = _normalize_status(_payload_value(approval, "status", default=None))
    current_requester_id = str(_payload_value(approval, "requesterId", "requester_id", default="") or "").strip()

    if normalized_request_type is not None and current_request_type != normalized_request_type:
        return False
    if normalized_status is not None and current_status != normalized_status:
        return False
    if normalized_requester_id and current_requester_id != normalized_requester_id:
        return False
    if normalized_exclude_requester_id and current_requester_id == normalized_exclude_requester_id:
        return False
    if not normalized_query:
        return True

    searchable_values = (
        _payload_value(approval, "id", default=""),
        _payload_value(approval, "businessKey", "business_key", default=""),
        _payload_value(approval, "ruleId", "rule_id", default=""),
        current_status or "",
        current_request_type,
        current_requester_id,
        _payload_value(approval, "reviewedBy", "reviewed_by", default=""),
        _payload_value(approval, "effectiveStatus", "effective_status", default=""),
        _payload_value(approval, "comments", default=""),
    )
    return any(normalized_query in str(value or "").strip().lower() for value in searchable_values)


class InMemoryApprovalsRepository(ApprovalsRepository):
    def __init__(self) -> None:
        self._approvals, self._audit = approvals_seed_data()

    def list_approvals(
        self,
        workspace_id: str | None = None,
        business_key: str | None = None,
        request_type: str | None = None,
        status: str | None = None,
        requester_id: str | None = None,
        exclude_requester_id: str | None = None,
        query: str | None = None,
    ) -> list[ApprovalEntity]:
        rows = self._approvals
        if workspace_id is not None:
            target = str(workspace_id).strip().lower()
            rows = [item for item in rows if str(item.get("workspaceId") or "").strip().lower() == target]
        if business_key is not None:
            rows = [item for item in rows if str(item.get("businessKey") or "").strip() == business_key]
        rows = [
            item for item in rows
            if _approval_matches_filters(
                item,
                request_type=request_type,
                status=status,
                requester_id=requester_id,
                exclude_requester_id=exclude_requester_id,
                query=query,
            )
        ]
        approval_ids = [str(item.get("id") or "").strip() for item in rows if str(item.get("id") or "").strip()]
        comment_threads = self._load_comment_threads(approval_ids)
        comment_governance = self._load_comment_governance(approval_ids)
        return [
            ApprovalEntity(
                **{
                    **item,
                    "commentThread": comment_threads.get(str(item.get("id") or ""), []),
                    **comment_governance.get(str(item.get("id") or ""), {}),
                }
            )
            for item in rows
        ]

    def create_approval(self, payload: dict, actor_id: str | None = None) -> ApprovalEntity:
        import random
        import time
        from datetime import UTC, datetime

        approval_id = f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
        _reject_camel_case_approval_keys(payload, "Approval creation payload")
        requester_id = str(actor_id or payload.get("requester_id") or "").strip() or None
        workspace_id = str(payload.get("workspace_id") or "default").strip() or "default"
        rule_id = str(payload.get("rule_id") or "").strip()
        gx_run_plan_id = str(payload.get("gx_run_plan_id") or "").strip() or None
        gx_run_plan_version_id = str(payload.get("gx_run_plan_version_id") or "").strip() or None
        if gx_run_plan_id and not gx_run_plan_version_id:
            raise ValueError("gx_run_plan_version_id is required when gx_run_plan_id is provided")
        status = str(payload.get("status") or "pending").strip() or "pending"
        request_type = _normalize_request_type(payload.get("request_type"))
        effective_status = _derive_effective_status(request_type)
        comments = str(payload.get("comments") or "").strip() or None
        effective_at = str(payload.get("effective_at") or "").strip() or None
        suite_repair = payload.get("suite_repair")
        requested_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

        created = {
            "id": approval_id,
            "businessKey": approval_id,
            "ruleId": rule_id,
            "gxRunPlanId": gx_run_plan_id,
            "gxRunPlanVersionId": gx_run_plan_version_id,
            "status": status,
            "requesterId": requester_id,
            "workspaceId": workspace_id,
            "requestType": request_type,
            "effectiveStatus": effective_status,
            "effectiveAt": effective_at,
            "comments": comments,
            "requestedAt": requested_at,
            "reviewedBy": None,
            "reviewedAt": None,
        }
        self._approvals.append(created)
        self._audit.append(
            {
                "id": f"{approval_id}-a",
                "approvalId": approval_id,
                "action": "created",
                "actorId": requester_id,
                "timestamp": requested_at,
                "details": {
                    "requester_id": requester_id,
                    "request_type": request_type,
                    "effective_status": effective_status,
                    "effective_at": effective_at,
                    "comments": comments,
                    "suite_repair": suite_repair,
                    "gx_run_plan_id": gx_run_plan_id,
                    "gx_run_plan_version_id": gx_run_plan_version_id,
                },
            }
        )
        return ApprovalEntity(**created)

    def update_approval(self, approval_id: str, payload: dict, actor_id: str | None = None) -> ApprovalEntity | None:
        from datetime import UTC, datetime

        existing = next((item for item in self._approvals if str(item.get("id") or "") == str(approval_id)), None)
        if existing is None:
            return None

        requester = str(existing.get("requesterId") or "").strip()
        actor = str(actor_id or "").strip()
        if requester and actor and requester == actor:
            raise PermissionError("Requester cannot approve their own request")

        status = str(payload.get("status") or existing.get("status") or "pending").strip() or "pending"
        comments = str(payload.get("comments") or existing.get("comments") or "").strip() or None
        reviewed_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        existing["status"] = status
        existing["comments"] = comments
        existing["reviewedBy"] = actor_id
        existing["reviewedAt"] = reviewed_at

        self._audit.append(
            {
                "id": f"{approval_id}-u-{len(self._audit) + 1}",
                "approvalId": approval_id,
                "action": "approved" if status == "approved" else "rejected",
                "actorId": actor_id,
                "timestamp": reviewed_at,
                "details": {
                    "status": status,
                    "request_type": existing.get("requestType") or "activation",
                    "effective_status": existing.get("effectiveStatus") or _derive_effective_status(_normalize_request_type(existing.get("requestType"))),
                    "comments": comments,
                },
            }
        )
        return ApprovalEntity(**existing)

    def delete_approval(self, approval_id: str, actor_id: str | None = None) -> ApprovalEntity | None:
        for index, item in enumerate(self._approvals):
            if str(item.get("id") or "") != str(approval_id):
                continue

            requester = str(item.get("requesterId") or "").strip()
            actor = str(actor_id or "").strip()
            if requester and actor and requester != actor:
                raise PermissionError("Only requester can cancel")

            removed = dict(item)
            del self._approvals[index]
            self._audit.append(
                {
                    "id": f"{approval_id}-d-{len(self._audit) + 1}",
                    "approvalId": approval_id,
                    "action": "cancelled",
                    "actorId": actor_id,
                    "timestamp": "2026-03-14T00:00:00Z",
                    "details": {},
                }
            )
            return ApprovalEntity(**removed)
        return None

    def list_approval_audit(self) -> list[ApprovalAuditEntity]:
        return [ApprovalAuditEntity(**item) for item in self._audit]

    def _load_comment_threads(self, approval_ids: list[str]) -> dict[str, list[dict[str, object]]]:
        if not approval_ids:
            return {}

        audit_by_approval: dict[str, list[ApprovalAuditEntity]] = {approval_id: [] for approval_id in approval_ids}
        target_ids = {str(approval_id).strip() for approval_id in approval_ids if str(approval_id).strip()}
        for row in self._audit:
            approval_id = str(row.get("approvalId") or row.get("approval_id") or "").strip()
            if approval_id not in target_ids:
                continue
            audit_by_approval.setdefault(approval_id, []).append(ApprovalAuditEntity(**row))

        return {
            approval_id: build_approval_comment_thread(rows)
            for approval_id, rows in audit_by_approval.items()
            if rows
        }

    def _load_comment_governance(self, approval_ids: list[str]) -> dict[str, dict[str, object]]:
        if not approval_ids:
            return {}

        audit_by_approval: dict[str, list[ApprovalAuditEntity]] = {approval_id: [] for approval_id in approval_ids}
        target_ids = {str(approval_id).strip() for approval_id in approval_ids if str(approval_id).strip()}
        for row in self._audit:
            approval_id = str(row.get("approvalId") or row.get("approval_id") or "").strip()
            if approval_id not in target_ids:
                continue
            audit_by_approval.setdefault(approval_id, []).append(ApprovalAuditEntity(**row))

        return {
            approval_id: build_approval_comment_governance(rows)
            for approval_id, rows in audit_by_approval.items()
            if rows
        }

    def append_audit_event(
        self,
        *,
        approval_id: str,
        action: str,
        actor_id: str | None,
        details: dict,
    ) -> ApprovalAuditEntity:
        from datetime import UTC, datetime

        timestamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        item = {
            "id": f"{approval_id}-x-{len(self._audit) + 1}",
            "approvalId": str(approval_id),
            "action": str(action),
            "actorId": actor_id,
            "timestamp": timestamp,
            "details": dict(details or {}),
        }
        self._audit.append(item)
        return ApprovalAuditEntity(**item)