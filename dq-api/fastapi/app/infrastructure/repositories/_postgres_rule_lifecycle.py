from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.domain.entities import build_rule_record_entity, RuleRecordEntity
from app.domain.entities import rule_policy
from app.infrastructure.orm.models import RuleRow
from app.infrastructure.orm.models import RuleVersionRow
from app.infrastructure.orm.session import session_scope


class RuleLifecycleMixin:

    async def _activate_rule_payload(self, rule_id: str) -> dict | None:
        payload: dict[str, Any] | None = None
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(RuleRow)
                .where(RuleRow.id == rule_id)
                .where(RuleRow.deleted_on.is_(None))
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None

            from_status = self._derive_rule_status_from_row(row)
            self._ensure_rule_transition_allowed(from_status=from_status, to_status="activated")
            row.active = True
            row.last_approval_status = "approved"
            row.validation_status = row.validation_status or "valid"
            row.validated_at = row.validated_at or datetime.now(UTC)
            row.version_updated_at = datetime.now(UTC)
            self._append_rule_status_history_row(
                session,
                rule_id=rule_id,
                action="activate",
                from_status=from_status,
                to_status="activated",
                changed_by=row.last_approval_by or row.created_by,
                reason="Rule activated",
            )
            session.commit()

            payload = self._serialize_rule_row(row)

        if payload is None:
            return None
        payload["ok"] = True
        return payload

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
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(RuleRow)
                .where(RuleRow.id == rule_id)
                .where(RuleRow.deleted_on.is_(None))
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None

            current_lifecycle_status = rule_policy.derive_rule_lifecycle_status_from_row(row)
            target_lifecycle_status = self._normalize_rule_lifecycle_status(lifecycle_status)
            if not target_lifecycle_status:
                raise ValueError("Lifecycle status is required")
            if target_lifecycle_status == "retired" and self._derive_rule_status_from_row(row) == "activated":
                raise ValueError("Active rules must be deactivated before they can be retired")

            self._ensure_rule_lifecycle_transition_allowed(
                from_status=current_lifecycle_status,
                to_status=target_lifecycle_status,
            )

            row.lifecycle_status = target_lifecycle_status
            if row.current_version_id:
                version_row = session.execute(
                    select(RuleVersionRow)
                    .where(RuleVersionRow.id == row.current_version_id)
                    .limit(1)
                ).scalar_one_or_none()
                if version_row is not None:
                    version_row.lifecycle_status = target_lifecycle_status
            self._append_rule_status_history_row(
                session,
                rule_id=rule_id,
                action=self._rule_lifecycle_action(target_lifecycle_status),
                from_status=current_lifecycle_status,
                to_status=target_lifecycle_status,
                changed_by=changed_by,
                reason=reason or f"Lifecycle status set to {target_lifecycle_status}",
            )
            session.commit()
            session.refresh(row)
            payload = self._serialize_rule_row(row)

        return build_rule_record_entity(payload)

    async def deactivate_rule(self, rule_id: str) -> dict | None:
        payload: dict[str, Any] | None = None
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(RuleRow)
                .where(RuleRow.id == rule_id)
                .where(RuleRow.deleted_on.is_(None))
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None

            from_status = self._derive_rule_status_from_row(row)
            self._ensure_rule_transition_allowed(from_status=from_status, to_status="deactivated")
            row.active = False
            row.last_approval_status = "deactivated"
            row.version_updated_at = datetime.now(UTC)
            self._append_rule_status_history_row(
                session,
                rule_id=rule_id,
                action="deactivate",
                from_status=from_status,
                to_status="deactivated",
                changed_by=row.last_approval_by or row.created_by,
                reason="Rule deactivated",
            )
            session.commit()

            payload = self._serialize_rule_row(row)

        if payload is None:
            return None
        payload["ok"] = True
        return payload

    async def _soft_delete_rule_payload(self, rule_id: str, *, removed_by: str) -> dict | None:
        payload: dict[str, Any] | None = None
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(RuleRow)
                .where(RuleRow.id == rule_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None

            if row.deleted_on is not None:
                raise ValueError("Rule is already removed")

            if bool(row.active):
                raise ValueError("Rule must be deactivated before it can be removed")

            from_status = self._derive_rule_status_from_row(row)
            normalized_status = str(row.last_approval_status or "").strip().lower().replace("_", "-")
            if normalized_status != "deactivated":
                raise ValueError("Rule must be in deactivated status before it can be removed")

            now = datetime.now(UTC)
            row.deleted_on = now
            row.deleted_by = removed_by
            row.last_approval_status = "removed"
            row.version_updated_at = now
            self._ensure_rule_transition_allowed(from_status=from_status, to_status="removed")
            self._append_rule_status_history_row(
                session,
                rule_id=rule_id,
                action="remove",
                from_status=from_status,
                to_status="removed",
                changed_by=removed_by,
                reason="Rule removed",
            )
            session.commit()

            payload = self._serialize_rule_row(row)

        if payload is None:
            return None
        payload["ok"] = True
        return payload

    async def soft_delete_rule_record(self, rule_id: str, *, removed_by: str) -> RuleRecordEntity | None:
        payload = await self._soft_delete_rule_payload(rule_id, removed_by=removed_by)
        return build_rule_record_entity(payload)

    async def recover_rule(self, rule_id: str, *, recovered_by: str) -> dict | None:
        payload: dict[str, Any] | None = None
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(RuleRow)
                .where(RuleRow.id == rule_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None

            if row.deleted_on is None:
                raise ValueError("Rule is not removed")

            now = datetime.now(UTC)
            from_status = self._derive_rule_status_from_row(row)
            self._ensure_rule_transition_allowed(from_status=from_status, to_status="recovered")
            row.deleted_on = None
            row.deleted_by = None
            row.active = False
            row.last_approval_by = recovered_by
            row.last_approval_at = now
            row.last_approval_status = "recovered"
            row.version_updated_at = now
            self._append_rule_status_history_row(
                session,
                rule_id=rule_id,
                action="recover",
                from_status=from_status,
                to_status="recovered",
                changed_by=recovered_by,
                reason="Rule recovered",
            )
            session.commit()

            payload = self._serialize_rule_row(row)

        if payload is None:
            return None
        payload["ok"] = True
        return payload

    async def save_rule_as_template(
        self,
        *,
        rule_id: str,
        template_name: str,
        template_description: str | None,
        created_by: str,
    ) -> dict | None:
        payload: dict[str, Any] | None = None
        with session_scope(self.database_url) as session:
            source = session.execute(
                select(RuleRow)
                .where(RuleRow.id == rule_id)
                .where(RuleRow.deleted_on.is_(None))
                .limit(1)
            ).scalar_one_or_none()
            if source is None:
                return None

            template_rule_id = f"tmpl-{uuid4().hex}"
            now = datetime.now(UTC)
            row = RuleRow(
                id=template_rule_id,
                name=template_name,
                description=template_description,
                expression=source.expression,
                dimension=source.dimension,
                active=False,
                generated=False,
                is_template=True,
                template_id=rule_id,
                workspace=source.workspace,
                created_by=created_by,
                suggestion_id=None,
                dsl=getattr(source, "dsl", None),
                taxonomy=getattr(source, "taxonomy", None),
                join_conditions=source.join_conditions,
                alias_mappings=source.alias_mappings,
                reusable_join_id=source.reusable_join_id,
                check_type=source.check_type,
                check_type_params=source.check_type_params,
                version_created_at=now,
                version_updated_at=now,
            )
            session.add(row)
            self._append_rule_status_history_row(
                session,
                rule_id=template_rule_id,
                action="create",
                from_status=None,
                to_status="draft",
                changed_by=created_by,
                reason="Template created",
                allow_same_status=True,
            )
            session.commit()

            payload = self._serialize_rule_row(row)

        if payload is None:
            return None
        payload["ok"] = True
        return payload
