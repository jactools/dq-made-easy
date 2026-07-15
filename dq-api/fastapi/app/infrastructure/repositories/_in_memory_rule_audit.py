from __future__ import annotations

from copy import deepcopy
from typing import Any


class InMemoryRuleAuditMixin:

    async def list_rule_status_history(self, rule_id: str, limit: int = 100, offset: int = 0) -> list[dict] | None:
        if rule_id not in self._rules:
            return None

        # Return newest-first to match the API contract and other repositories.
        rows = list(reversed(self._status_history.get(rule_id, [])))
        safe_limit = max(1, min(100, limit))
        safe_offset = max(0, offset)
        window = rows[safe_offset : safe_offset + safe_limit]
        return [deepcopy(row) for row in window]

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
        if rule_id not in self._rules:
            return None

        row = self._record_status_transition(
            rule_id=rule_id,
            action=action,
            from_status=from_status,
            to_status=to_status or self._current_rule_status(rule_id),
            changed_by=changed_by,
            reason=reason,
            details=details,
            allow_same_status=True,
        )
        return deepcopy(row) if row is not None else None

    async def record_rule_status_transition(
        self,
        rule_id: str,
        from_status: str | None,
        to_status: str,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> dict | None:
        if rule_id not in self._rules:
            return None

        self._ensure_rule_transition_allowed(from_status=from_status, to_status=to_status)

        normalized_to = self._normalize_rule_status(to_status)
        if normalized_to:
            details = self._rule_details.setdefault(rule_id, {})
            details["last_approval_status"] = normalized_to
            details["last_approval_by"] = str(changed_by or "").strip() or None

        row = self._record_status_transition(
            rule_id=rule_id,
            action=self._infer_rule_transition_action(normalized_to),
            from_status=from_status,
            to_status=to_status,
            changed_by=changed_by,
            reason=reason,
        )
        return deepcopy(row) if row is not None else None
