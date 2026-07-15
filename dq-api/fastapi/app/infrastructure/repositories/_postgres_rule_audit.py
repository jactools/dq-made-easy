from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.infrastructure.orm.models import RuleRow
from app.infrastructure.orm.models import RuleStatusHistoryRow
from app.infrastructure.orm.session import session_scope


class RuleAuditMixin:

    async def list_rule_status_history(
        self,
        rule_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict] | None:
        with session_scope(self.database_url) as session:
            rule = session.execute(
                select(RuleRow)
                .where(RuleRow.id == rule_id)
                .limit(1)
            ).scalar_one_or_none()
            if rule is None:
                return None

            rows = session.execute(
                select(RuleStatusHistoryRow)
                .where(RuleStatusHistoryRow.rule_id == rule_id)
                .order_by(RuleStatusHistoryRow.changed_at.desc(), RuleStatusHistoryRow.id.desc())
            ).scalars().all()

        safe_limit = max(1, min(100, limit))
        safe_offset = max(0, offset)
        window = rows[safe_offset : safe_offset + safe_limit]
        return [self._serialize_rule_status_history_row(row) for row in window]

    async def record_rule_audit_event(
        self,
        rule_id: str,
        *,
        action: str,
        from_status: str | None = None,
        to_status: str | None = None,
        changed_by: str | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict | None:
        with session_scope(self.database_url) as session:
            rule = session.execute(
                select(RuleRow)
                .where(RuleRow.id == rule_id)
                .limit(1)
            ).scalar_one_or_none()
            if rule is None:
                return None

            history_row = self._append_rule_status_history_row(
                session,
                rule_id=rule_id,
                action=action,
                from_status=from_status,
                to_status=to_status if to_status is not None else self._derive_rule_status_from_row(rule),
                changed_by=changed_by,
                reason=reason,
                details=details,
                allow_same_status=True,
            )
            session.commit()

        if history_row is None:
            return None
        return self._serialize_rule_status_history_row(history_row)

    async def record_rule_status_transition(
        self,
        rule_id: str,
        from_status: str | None,
        to_status: str,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> dict | None:
        with session_scope(self.database_url) as session:
            rule = session.execute(
                select(RuleRow)
                .where(RuleRow.id == rule_id)
                .limit(1)
            ).scalar_one_or_none()
            if rule is None:
                return None

            normalized_to = self._normalize_rule_status(to_status)
            self._ensure_rule_transition_allowed(from_status=from_status, to_status=to_status)

            if normalized_to:
                rule.last_approval_status = normalized_to
                rule.last_approval_by = str(changed_by or "").strip() or None
                rule.last_approval_at = datetime.now(UTC)

            history_row = self._append_rule_status_history_row(
                session,
                rule_id=rule_id,
                action=self._infer_rule_transition_action(normalized_to),
                from_status=from_status,
                to_status=to_status,
                changed_by=changed_by,
                reason=reason,
            )
            session.commit()

        if history_row is None:
            return None
        return self._serialize_rule_status_history_row(history_row)
