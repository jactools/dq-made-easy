from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities import build_rule_record_entity, RuleEntity, RuleRecordEntity
from app.domain.entities import rule_policy


class InMemoryRuleLifecycleMixin:

    async def _activate_rule_payload(self, rule_id: str) -> dict | None:
        current = self._rules.get(rule_id)
        if current is None:
            return None

        from_status = self._current_rule_status(rule_id)
        self._ensure_rule_transition_allowed(from_status=from_status, to_status="activated")

        details = self._rule_details.setdefault(rule_id, {})
        self._rules[rule_id] = RuleEntity(
            id=rule_id,
            name=current.name,
            description=current.description,
            comments=str(details.get("comments") or "").strip() or None,
            expression=current.expression,
            dimension=current.dimension,
            active=True,
            createdByUserId=current.created_by_user_id,
            tagIds=list(current.tag_ids),
        )

        details["validation_status"] = "valid"
        details["last_approval_status"] = "approved"
        self._record_status_transition(
            rule_id=rule_id,
            action="activate",
            from_status=from_status,
            to_status="activated",
            changed_by=current.created_by_user_id,
            reason="Rule activated",
        )
        rows = await self._list_rule_payloads(workspace=str(details.get("workspace") or "default"))
        updated = next((row for row in rows if row["id"] == rule_id), None)
        return updated if updated is not None else {"id": rule_id, "active": True}

    async def activate_rule_record(self, rule_id: str) -> RuleRecordEntity | None:
        payload = await self._activate_rule_payload(rule_id)
        return build_rule_record_entity(payload)

    async def set_rule_lifecycle_status(
        self,
        rule_id: str,
        *,
        lifecycle_status: str,
        changed_by: str | None,
        reason: str | None = None,
    ) -> RuleRecordEntity | None:
        current = self._rules.get(rule_id)
        if current is None:
            return None

        details = self._rule_details.setdefault(rule_id, {})
        if details.get("removed_at"):
            return None

        current_lifecycle_status = str(details.get("lifecycle_status") or "").strip() or rule_policy.derive_rule_lifecycle_status_from_row(details)
        target_lifecycle_status = self._normalize_rule_lifecycle_status(lifecycle_status)
        if not target_lifecycle_status:
            raise ValueError("Lifecycle status is required")
        if target_lifecycle_status == "retired" and current.active:
            raise ValueError("Active rules must be deactivated before they can be retired")

        self._ensure_rule_lifecycle_transition_allowed(
            from_status=current_lifecycle_status,
            to_status=target_lifecycle_status,
        )

        details["lifecycle_status"] = target_lifecycle_status
        if self._rule_versions.get(rule_id):
            self._rule_versions[rule_id][0].setdefault("rule", {})["lifecycleStatus"] = target_lifecycle_status
        self._record_status_transition(
            rule_id=rule_id,
            action=self._rule_lifecycle_action(target_lifecycle_status),
            from_status=current_lifecycle_status,
            to_status=target_lifecycle_status,
            changed_by=changed_by,
            reason=reason or f"Lifecycle status set to {target_lifecycle_status}",
        )
        rows = await self._list_rule_payloads(workspace=str(details.get("workspace") or "default"))
        updated = next((row for row in rows if row["id"] == rule_id), None)
        return build_rule_record_entity(updated) if updated is not None else None

    async def deactivate_rule(self, rule_id: str) -> dict | None:
        current = self._rules.get(rule_id)
        if current is None:
            return None

        from_status = self._current_rule_status(rule_id)
        self._ensure_rule_transition_allowed(from_status=from_status, to_status="deactivated")

        self._rules[rule_id] = RuleEntity(
            id=rule_id,
            name=current.name,
            description=current.description,
            expression=current.expression,
            dimension=current.dimension,
            active=False,
            createdByUserId=current.created_by_user_id,
            tagIds=list(current.tag_ids),
        )

        details = self._rule_details.setdefault(rule_id, {})
        details["last_approval_status"] = "deactivated"
        self._record_status_transition(
            rule_id=rule_id,
            action="deactivate",
            from_status=from_status,
            to_status="deactivated",
            changed_by=current.created_by_user_id,
            reason="Rule deactivated",
        )
        rows = await self._list_rule_payloads(workspace=str(details.get("workspace") or "default"))
        updated = next((row for row in rows if row["id"] == rule_id), None)
        return updated if updated is not None else {"id": rule_id, "active": False, "last_approval_status": "deactivated"}

    async def _soft_delete_rule_payload(self, rule_id: str, *, removed_by: str) -> dict | None:
        current = self._rules.get(rule_id)
        if current is None:
            return None

        details = self._rule_details.setdefault(rule_id, {})
        if details.get("removed_at"):
            raise ValueError("Rule is already removed")

        if bool(current.active):
            raise ValueError("Rule must be deactivated before it can be removed")

        normalized_status = str(details.get("last_approval_status") or "").strip().lower().replace("_", "-")
        if normalized_status != "deactivated":
            raise ValueError("Rule must be in deactivated status before it can be removed")

        from_status = self._current_rule_status(rule_id)
        self._ensure_rule_transition_allowed(from_status=from_status, to_status="removed")
        now = datetime.now(UTC).isoformat()
        details["removed_at"] = now
        details["removed_by"] = removed_by
        details["last_approval_status"] = "removed"
        self._record_status_transition(
            rule_id=rule_id,
            action="remove",
            from_status=from_status,
            to_status="removed",
            changed_by=removed_by,
            reason="Rule removed",
        )

        rows = await self._list_rule_payloads(
            workspace=str(details.get("workspace") or "default"),
            include_deleted=True,
        )
        updated = next((row for row in rows if row["id"] == rule_id), None)
        if updated is None:
            return {
                "id": rule_id,
                "removed": True,
                "removed_at": now,
                "removed_by": removed_by,
                "last_approval_status": "removed",
                "ok": True,
            }
        updated["ok"] = True
        return updated

    async def soft_delete_rule_record(self, rule_id: str, *, removed_by: str) -> RuleRecordEntity | None:
        payload = await self._soft_delete_rule_payload(rule_id, removed_by=removed_by)
        return build_rule_record_entity(payload)

    async def recover_rule(self, rule_id: str, *, recovered_by: str) -> dict | None:
        current = self._rules.get(rule_id)
        if current is None:
            return None

        details = self._rule_details.setdefault(rule_id, {})
        if not details.get("removed_at"):
            raise ValueError("Rule is not removed")

        from_status = self._current_rule_status(rule_id)
        self._ensure_rule_transition_allowed(from_status=from_status, to_status="recovered")
        details["removed_at"] = None
        details["removed_by"] = None
        details["last_approval_status"] = "recovered"

        self._rules[rule_id] = RuleEntity(
            id=rule_id,
            name=current.name,
            description=current.description,
            expression=current.expression,
            dimension=current.dimension,
            active=False,
            createdByUserId=current.created_by_user_id,
            tagIds=list(current.tag_ids),
        )

        self._record_status_transition(
            rule_id=rule_id,
            action="recover",
            from_status=from_status,
            to_status="recovered",
            changed_by=recovered_by,
            reason="Rule recovered",
        )

        rows = await self._list_rule_payloads(workspace=str(details.get("workspace") or "default"))
        updated = next((row for row in rows if row["id"] == rule_id), None)
        if updated is None:
            return {
                "id": rule_id,
                "active": False,
                "removed": False,
                "last_approval_status": "recovered",
                "ok": True,
            }
        updated["ok"] = True
        return updated

    async def save_rule_as_template(
        self,
        *,
        rule_id: str,
        template_name: str,
        template_description: str | None,
        created_by: str,
    ) -> dict | None:
        source = self._rules.get(rule_id)
        if source is None:
            return None

        creator_id = created_by if created_by in self._users else "user-admin"
        template_id = f"tmpl-{uuid4().hex[:10]}"
        self._rules[template_id] = RuleEntity(
            id=template_id,
            name=template_name,
            description=template_description,
            expression=source.expression,
            dimension=source.dimension,
            active=False,
            createdByUserId=creator_id,
            tagIds=list(source.tag_ids),
        )
        source_detail = self._rule_details.get(rule_id, {})
        self._rule_details[template_id] = {
            "workspace": source_detail.get("workspace", "default"),
            "generated": False,
            "is_template": True,
            "template_id": rule_id,
            "suggestion_id": None,
            "dsl": deepcopy(source_detail.get("dsl")) if isinstance(source_detail.get("dsl"), dict) else None,
            "taxonomy": deepcopy(source_detail.get("taxonomy")) if isinstance(source_detail.get("taxonomy"), dict) else None,
            "join_conditions": source_detail.get("join_conditions", []),
            "alias_mappings": source_detail.get("alias_mappings", {}),
            "reusable_join_id": source_detail.get("reusable_join_id"),
            "manual_override_by": source_detail.get("manual_override_by"),
            "manual_override_at": source_detail.get("manual_override_at"),
            "reusableFilterIds": list(source_detail.get("reusableFilterIds", [])),
            "reusableFilters": list(source_detail.get("reusableFilters", [])),
        }

        self._record_status_transition(
            rule_id=template_id,
            action="create",
            from_status=None,
            to_status="draft",
            changed_by=creator_id,
            reason="Template created",
            allow_same_status=True,
        )

        rows = await self._list_rule_payloads(workspace=str(source_detail.get("workspace") or "default"))
        created = next((row for row in rows if row["id"] == template_id), None)
        if created is None:
            return {"id": template_id, "ok": True}
        created["ok"] = True
        return created
