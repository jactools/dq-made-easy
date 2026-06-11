from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy import update

from app.domain.entities.approvals import ApprovalAuditEntity, ApprovalEntity
from app.domain.entities.approvals import build_approval_comment_governance
from app.domain.entities.approvals import build_approval_comment_thread
from app.domain.interfaces.v1.approvals_repository import ApprovalsRepository
from app.infrastructure.orm.models import ApprovalRow
from app.infrastructure.orm.models import AuditRow
from app.infrastructure.orm.session import session_scope


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
    approval: dict[str, Any],
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

    current_request_type = _normalize_request_type(approval.get("request_type"))
    current_status = _normalize_status(approval.get("status"))
    current_requester_id = str(approval.get("requester_id") or "").strip()

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
        approval.get("id"),
        approval.get("business_key"),
        approval.get("rule_id"),
        current_status or "",
        current_request_type,
        current_requester_id,
        approval.get("acted_by"),
        approval.get("effective_status"),
        approval.get("comments"),
    )
    return any(normalized_query in str(value or "").strip().lower() for value in searchable_values)


class PostgresApprovalsRepository(ApprovalsRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

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
        with session_scope(self.database_url) as session:
            stmt = select(ApprovalRow)
            if workspace_id:
                stmt = stmt.where(ApprovalRow.workspace_id == workspace_id)
            if business_key is not None:
                stmt = stmt.where(ApprovalRow.business_key == business_key)
            if requester_id is not None:
                stmt = stmt.where(ApprovalRow.requester_id == requester_id)
            if exclude_requester_id is not None:
                stmt = stmt.where(ApprovalRow.requester_id != exclude_requester_id)
            if status is not None:
                stmt = stmt.where(ApprovalRow.status == status)
            rows = session.execute(stmt).scalars().all()
            approval_ids = [str(row.id or "") for row in rows if str(row.id or "").strip()]
            created_details = self._load_created_details(session, approval_ids)
            comment_threads = self._load_comment_threads(session, approval_ids)
            comment_governance = self._load_comment_governance(session, approval_ids)
            payload_rows = [
                {
                    **self._approval_row_to_dict(
                        row,
                        created_details.get(str(row.id or ""), {}),
                        comment_threads.get(str(row.id or ""), []),
                    ),
                    **comment_governance.get(str(row.id or ""), {}),
                }
                for row in rows
            ]
            filtered_rows = [
                row for row in payload_rows
                if _approval_matches_filters(
                    row,
                    request_type=request_type,
                    status=status,
                    requester_id=requester_id,
                    exclude_requester_id=exclude_requester_id,
                    query=query,
                )
            ]
            return [self._to_approval_entity(row) for row in filtered_rows]

    def list_approval_audit(self) -> list[ApprovalAuditEntity]:
        with session_scope(self.database_url) as session:
            rows = session.execute(select(AuditRow)).scalars().all()
        return [
            ApprovalAuditEntity(
                id=str(item.id or ""),
                approvalId=str(item.approval_id or ""),
                action=str(item.action or ""),
                actorId=str(item.actor_id) if item.actor_id is not None else None,
                timestamp=str(item.timestamp or ""),
                details=self._parse_json_object(item.details),
            )
            for item in rows
        ]

    def create_approval(self, payload: dict, actor_id: str | None = None) -> ApprovalEntity:
        import json
        import random
        import time

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
        timestamp = self._current_timestamp()
        acted_at = self._parse_iso_datetime(timestamp) if status in {"approved", "rejected"} and actor_id else None

        details = json.dumps(
            {
                "requester_id": requester_id,
                "request_type": request_type,
                "effective_status": effective_status,
                "effective_at": effective_at,
                "comments": comments,
                "suite_repair": suite_repair,
                "gx_run_plan_id": gx_run_plan_id,
                "gx_run_plan_version_id": gx_run_plan_version_id,
            }
        )

        with session_scope(self.database_url) as session:
            session.add(
                ApprovalRow(
                    id=approval_id,
                    business_key=approval_id,
                    rule_id=rule_id,
                    effective_status=effective_status,
                    gx_run_plan_id=gx_run_plan_id,
                    gx_run_plan_version_id=gx_run_plan_version_id,
                    status=status,
                    requester_id=requester_id,
                    requested_at=timestamp,
                    acted_by=actor_id if acted_at else None,
                    acted_at=acted_at,
                    workspace_id=workspace_id,
                )
            )
            session.add(
                AuditRow(
                    id=f"{approval_id}-a",
                    approval_id=approval_id,
                    action="created",
                    actor_id=requester_id,
                    timestamp=timestamp,
                    details=details,
                )
            )
            session.commit()

        row = self._fetch_one(approval_id)
        if row is None:
            raise RuntimeError("Failed to create approval")
        return self._to_approval_entity(row)

    def update_approval(self, approval_id: str, payload: dict, actor_id: str | None = None) -> ApprovalEntity | None:
        import json

        _reject_camel_case_approval_keys(payload, "Approval update payload")

        existing = self._fetch_one(approval_id)
        if existing is None:
            return None

        timestamp = self._current_timestamp()
        requester = _payload_text(existing, "requester_id", "requesterid", "requesterId", default="") or ""
        actor = str(actor_id or "").strip()
        if requester and actor and requester == actor:
            raise PermissionError("Requester cannot approve their own request")

        status = _payload_text(payload, "status", default=str(existing.get("status") or "pending")) or "pending"
        comments = _payload_text(payload, "comments", default=str(existing.get("comments") or "").strip() or None)
        request_type = _normalize_request_type(existing.get("request_type"))
        effective_status = _payload_text(existing, "effective_status", "effectivestatus", "effectiveStatus", default=None)
        acted_at = self._parse_iso_datetime(timestamp)

        with session_scope(self.database_url) as session:
            result = session.execute(
                update(ApprovalRow)
                .where(ApprovalRow.id == approval_id)
                .values(status=status, acted_by=actor_id, acted_at=acted_at)
            )
            if not result.rowcount:
                session.rollback()
                return None
            session.add(
                AuditRow(
                    id=f"{approval_id}-u",
                    approval_id=approval_id,
                    action="approved" if status == "approved" else "rejected",
                    actor_id=actor_id,
                    timestamp=timestamp,
                    details=json.dumps(
                        {
                            "status": status,
                            "request_type": request_type,
                            "effective_status": effective_status or _derive_effective_status(request_type),
                            "comments": comments,
                        }
                    ),
                )
            )
            session.commit()

        row = self._fetch_one(approval_id)
        if row is None:
            return None
        return self._to_approval_entity(row)

    def delete_approval(self, approval_id: str, actor_id: str | None = None) -> ApprovalEntity | None:
        existing = self._fetch_one(approval_id)
        if existing is None:
            return None

        timestamp = self._current_timestamp()
        requester = _payload_text(existing, "requester_id", "requesterid", "requesterId", default="") or ""
        actor = str(actor_id or "").strip()
        if requester and actor and requester != actor:
            raise PermissionError("Only requester can cancel")

        with session_scope(self.database_url) as session:
            session.execute(delete(ApprovalRow).where(ApprovalRow.id == approval_id))
            session.add(
                AuditRow(
                    id=f"{approval_id}-d",
                    approval_id=approval_id,
                    action="cancelled",
                    actor_id=actor_id,
                    timestamp=timestamp,
                    details="{}",
                )
            )
            session.commit()

        return self._to_approval_entity(existing)

    def _to_approval_entity(self, row: dict[str, Any]) -> ApprovalEntity:
        return ApprovalEntity(
            id=str(row.get("id") or ""),
            businessKey=_payload_text(row, "business_key", "businesskey", "businessKey", default=None),
            ruleId=str(
                _payload_text(row, "rule_id", "ruleid", "ruleId", default="")
                or ""
            ),
            gxRunPlanId=_payload_text(row, "gx_run_plan_id", "gxrunplanid", "gxRunPlanId", default=None),
            gxRunPlanVersionId=_payload_text(row, "gx_run_plan_version_id", "gxrunplanversionid", "gxRunPlanVersionId", default=None),
            effectiveStatus=_payload_text(row, "effective_status", "effectivestatus", "effectiveStatus", default=None),
            status=str(row.get("status") or "pending"),
            requesterId=(
                _payload_text(row, "requester_id", "requesterid", "requesterId", default=None)
            ),
            workspaceId=str(
                _payload_text(row, "workspace_id", "workspaceid", "workspaceId", default="default")
                or "default"
            ),
            requestType=_normalize_request_type(
                _payload_value(row, "request_type", "requesttype", "requestType", default=None)
            ),
            effectiveAt=_payload_text(row, "effective_at", "effectiveat", "effectiveAt", default=None),
            comments=_payload_text(row, "comments", default=None),
            commentThread=list(row.get("comment_thread") or row.get("commentThread") or []),
            requestedAt=_payload_text(row, "requested_at", "requestedat", "requestedAt", default=None),
            reviewedBy=_payload_text(row, "acted_by", "actedby", "reviewedBy", default=None),
            reviewedAt=_payload_text(row, "acted_at", "actedat", "reviewedAt", default=None),
        )

    def _fetch_one(self, approval_id: str) -> dict[str, Any] | None:
        with session_scope(self.database_url) as session:
            row = session.get(ApprovalRow, approval_id)
            if not row:
                return None
            created_details = self._load_created_details(session, [approval_id]).get(str(approval_id), {})
            return self._approval_row_to_dict(row, created_details)

    @staticmethod
    def _current_timestamp() -> str:
        from datetime import UTC
        from datetime import datetime as dt

        return dt.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _approval_row_to_dict(
        row: ApprovalRow,
        created_details: dict[str, Any] | None = None,
        comment_thread: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        details = created_details or {}
        return {
            "id": row.id,
            "business_key": row.business_key,
            "rule_id": row.rule_id,
            "effective_status": row.effective_status,
            "gx_run_plan_id": row.gx_run_plan_id,
            "gx_run_plan_version_id": row.gx_run_plan_version_id,
            "status": row.status,
            "requester_id": row.requester_id,
            "workspace_id": row.workspace_id,
            "requested_at": row.requested_at,
            "acted_by": row.acted_by,
            "acted_at": row.acted_at.isoformat().replace("+00:00", "Z") if row.acted_at else None,
            "request_type": details.get("request_type"),
            "effective_at": details.get("effective_at"),
            "comments": details.get("comments"),
            "comment_thread": list(comment_thread or []),
        }

    def _load_comment_threads(self, session, approval_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not approval_ids:
            return {}

        rows = session.execute(
            select(AuditRow).where(AuditRow.approval_id.in_(approval_ids))
        ).scalars().all()
        by_approval: dict[str, list[ApprovalAuditEntity]] = {approval_id: [] for approval_id in approval_ids}
        for row in rows:
            approval_id = str(row.approval_id or "").strip()
            if not approval_id:
                continue
            by_approval.setdefault(approval_id, []).append(
                ApprovalAuditEntity(
                    id=str(row.id or ""),
                    approvalId=approval_id,
                    action=str(row.action or ""),
                    actorId=str(row.actor_id) if row.actor_id is not None else None,
                    timestamp=str(row.timestamp or ""),
                    details=self._parse_json_object(row.details),
                )
            )

        return {
            approval_id: build_approval_comment_thread(audit_rows)
            for approval_id, audit_rows in by_approval.items()
            if audit_rows
        }

    def _load_comment_governance(self, session, approval_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not approval_ids:
            return {}

        rows = session.execute(
            select(AuditRow).where(AuditRow.approval_id.in_(approval_ids))
        ).scalars().all()
        by_approval: dict[str, list[ApprovalAuditEntity]] = {approval_id: [] for approval_id in approval_ids}
        for row in rows:
            approval_id = str(row.approval_id or "").strip()
            if not approval_id:
                continue
            by_approval.setdefault(approval_id, []).append(
                ApprovalAuditEntity(
                    id=str(row.id or ""),
                    approvalId=approval_id,
                    action=str(row.action or ""),
                    actorId=str(row.actor_id) if row.actor_id is not None else None,
                    timestamp=str(row.timestamp or ""),
                    details=self._parse_json_object(row.details),
                )
            )

        return {
            approval_id: build_approval_comment_governance(audit_rows)
            for approval_id, audit_rows in by_approval.items()
            if audit_rows
        }

    def _load_created_details(self, session, approval_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not approval_ids:
            return {}

        rows = session.execute(
            select(AuditRow)
            .where(AuditRow.approval_id.in_(approval_ids))
            .where(AuditRow.action == "created")
        ).scalars().all()
        payload: dict[str, dict[str, Any]] = {}
        for row in rows:
            approval_id = str(row.approval_id or "").strip()
            if not approval_id or approval_id in payload:
                continue
            payload[approval_id] = self._parse_json_object(row.details)
        return payload

    @staticmethod
    def _parse_json_object(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if value is None:
            return {}
        import json

        try:
            parsed = json.loads(str(value))
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    def append_audit_event(
        self,
        *,
        approval_id: str,
        action: str,
        actor_id: str | None,
        details: dict,
    ) -> ApprovalAuditEntity:
        import json

        normalized_approval_id = str(approval_id or "").strip()
        if not normalized_approval_id:
            raise ValueError("approval_id is required")

        timestamp = self._current_timestamp()
        row_id = f"{normalized_approval_id}-x-{uuid4().hex}"

        with session_scope(self.database_url) as session:
            session.add(
                AuditRow(
                    id=row_id,
                    approval_id=normalized_approval_id,
                    action=str(action or ""),
                    actor_id=actor_id,
                    timestamp=timestamp,
                    details=json.dumps(details or {}),
                )
            )
            session.commit()

        return ApprovalAuditEntity(
            id=row_id,
            approvalId=normalized_approval_id,
            action=str(action or ""),
            actorId=actor_id,
            timestamp=timestamp,
            details=dict(details or {}),
        )
