from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.domain.status_governance import canonicalize_status
from app.domain.status_governance import is_transition_defined


class InMemoryRuleHelpersMixin:

    def _current_rule_status(self, rule_id: str) -> str:
        current = self._rules.get(rule_id)
        if current is None:
            return "draft"

        details = self._rule_details.get(rule_id, {})
        if details.get("removed_at"):
            return "removed"
        if bool(current.active):
            return "activated"

        normalized_status = self._normalize_rule_status(details.get("last_approval_status"))
        return normalized_status or "draft"

    @staticmethod
    def _normalize_rule_status(value: str | None) -> str:
        normalized = str(value or "").strip().lower().replace("_", "-")
        if normalized == "pending":
            return "pending-approval"
        if normalized == "declined":
            return "rejected"
        return normalized

    def _ensure_rule_transition_allowed(self, *, from_status: str | None, to_status: str) -> None:
        normalized_from = self._normalize_rule_status(from_status)
        normalized_to = self._normalize_rule_status(to_status)
        if not normalized_from or normalized_from == normalized_to:
            return

        if not is_transition_defined(entity="rule", from_status=normalized_from, to_status=normalized_to):
            raise ValueError(f"Transition '{normalized_from}' -> '{normalized_to}' is not allowed")

    @staticmethod
    def _normalize_rule_lifecycle_status(value: str | None) -> str:
        return canonicalize_status(entity="rule_lifecycle", status=value)

    def _ensure_rule_lifecycle_transition_allowed(self, *, from_status: str | None, to_status: str) -> None:
        normalized_from = self._normalize_rule_lifecycle_status(from_status)
        normalized_to = self._normalize_rule_lifecycle_status(to_status)
        if not normalized_from or normalized_from == normalized_to:
            return

        if not is_transition_defined(entity="rule_lifecycle", from_status=normalized_from, to_status=normalized_to):
            raise ValueError(f"Transition '{normalized_from}' -> '{normalized_to}' is not allowed")

    def _record_status_transition(
        self,
        *,
        rule_id: str,
        action: str,
        from_status: str | None,
        to_status: str,
        changed_by: str | None,
        reason: str | None,
        details: dict | None = None,
        allow_same_status: bool = False,
    ) -> dict | None:
        normalized_from = self._normalize_rule_status(from_status)
        normalized_to = self._normalize_rule_status(to_status)
        normalized_action = self._normalize_rule_audit_action(action)
        if not normalized_to:
            return None
        if normalized_from and normalized_from == normalized_to and not allow_same_status:
            return None

        row = {
            "id": f"rsh-{uuid4().hex[:12]}",
            "ruleId": rule_id,
            "action": normalized_action,
            "fromStatus": normalized_from or None,
            "toStatus": normalized_to,
            "changedBy": str(changed_by or "").strip() or None,
            "changedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "reason": reason,
            "details": deepcopy(details) if details is not None else None,
        }
        history = self._status_history.setdefault(rule_id, [])
        history.append(row)
        history.sort(key=lambda item: (str(item.get("changedAt") or ""), str(item.get("id") or "")))

        return row

    @staticmethod
    def _normalize_rule_audit_action(value: str | None) -> str:
        normalized = str(value or "").strip().lower().replace("_", "-")
        return normalized or "transition"

    @staticmethod
    def _infer_rule_transition_action(to_status: str | None) -> str:
        normalized = str(to_status or "").strip().lower().replace("_", "-")
        action_map = {
            "approved": "approve",
            "rejected": "reject",
            "activated": "activate",
            "deactivated": "deactivate",
            "deprecated": "deprecate",
            "superseded": "supersede",
            "retired": "retire",
            "removed": "remove",
            "recovered": "recover",
        }
        return action_map.get(normalized, "transition")

    @staticmethod
    def _rule_lifecycle_action(lifecycle_status: str) -> str:
        normalized = str(lifecycle_status or "").strip().lower().replace("_", "-")
        action_map = {
            "active": "activate",
            "deprecated": "deprecate",
            "superseded": "supersede",
            "retired": "retire",
        }
        return action_map.get(normalized, "transition")
