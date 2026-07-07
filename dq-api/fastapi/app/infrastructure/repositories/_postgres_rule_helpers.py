from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.domain.entities import RuleEntity, RuleTagEntity
from app.domain.entities import rule_policy
from app.domain.status_governance import canonicalize_status
from app.domain.status_governance import is_transition_defined
from app.domain.user_names import compose_user_display_name
from app.infrastructure.orm.models import RuleRow
from app.infrastructure.orm.models import RuleReusableFilterRow
from app.infrastructure.orm.models import RuleStatusHistoryRow
from app.infrastructure.orm.models import RuleVersionRow
from app.infrastructure.orm.models import UserRow
from app.infrastructure.orm.session import session_scope


class RuleHelpersMixin:

    @staticmethod
    def _taxonomy_text(taxonomy: dict | None, *keys: str) -> str | None:
        if not isinstance(taxonomy, dict):
            return None
        for key in keys:
            value = taxonomy.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    @staticmethod
    def _merge_row_taxonomy(row: Any, taxonomy: dict | None) -> dict[str, Any]:
        merged: dict[str, Any] = dict(taxonomy or {})
        for key in ("data_steward", "domain_owner", "technical_owner"):
            value = getattr(row, key, None)
            if value is None:
                continue
            text = str(value).strip()
            if text and key not in merged:
                merged[key] = text
        return merged

    @staticmethod
    def _get_rule_row(session, rule_id: str) -> RuleRow | None:
        return session.execute(
            select(RuleRow)
            .where(RuleRow.id == rule_id)
            .where(RuleRow.deleted_on.is_(None))
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def _load_creator_names(session, user_ids: list[str]) -> dict[str, str]:
        normalized = sorted({user_id for user_id in user_ids if user_id})
        if not normalized:
            return {}

        rows = session.execute(select(UserRow).where(UserRow.id.in_(normalized))).scalars().all()
        return {
            str(row.id): compose_user_display_name(row.first_name, row.last_name, fallback=row.email or row.id or "system")
            for row in rows
        }

    @staticmethod
    def _load_version_numbers(session, version_ids: set[str]) -> dict[str, int]:
        normalized = sorted({version_id for version_id in version_ids if version_id})
        if not normalized:
            return {}

        rows = session.execute(
            select(RuleVersionRow).where(RuleVersionRow.id.in_(normalized))
        ).scalars().all()
        return {str(row.id): int(row.version_number) for row in rows}

    @staticmethod
    def _display_name_for_tag(tag_id: str) -> str:
        parts = [part for part in tag_id.replace("_", "-").split("-") if part and part != "tag"]
        if not parts:
            return tag_id
        display_parts = []
        for part in parts:
            if len(part) <= 3:
                display_parts.append(part.upper())
            else:
                display_parts.append(part.capitalize())
        return " ".join(display_parts)

    @staticmethod
    def _username_for_user(row: UserRow) -> str:
        email = str(row.email or "").strip()
        if email and "@" in email:
            return email.split("@", 1)[0]
        name = compose_user_display_name(row.first_name, row.last_name).strip().lower().replace(" ", "-")
        if name:
            return name
        return str(row.id or "user")

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

    @classmethod
    def _derive_rule_status_from_row(cls, row: RuleRow) -> str:
        if row.deleted_on is not None:
            return "removed"
        if bool(row.active):
            return "activated"

        normalized_status = cls._normalize_rule_status(row.last_approval_status)
        return normalized_status or "draft"

    def _append_rule_status_history_row(
        self,
        session,
        *,
        rule_id: str,
        action: str,
        from_status: str | None,
        to_status: str,
        changed_by: str | None,
        reason: str | None,
        details: dict[str, Any] | None = None,
        allow_same_status: bool = False,
    ) -> RuleStatusHistoryRow | None:
        normalized_from = self._normalize_rule_status(from_status)
        normalized_to = self._normalize_rule_status(to_status)
        normalized_action = self._normalize_rule_audit_action(action)
        if not normalized_to:
            return None
        if normalized_from and normalized_from == normalized_to and not allow_same_status:
            return None

        row = RuleStatusHistoryRow(
            id=f"rsh_{uuid4().hex}",
            rule_id=rule_id,
            action=normalized_action,
            from_status=normalized_from or None,
            to_status=normalized_to,
            changed_by=str(changed_by or "").strip() or None,
            changed_at=datetime.now(UTC),
            reason=reason,
            details=json.dumps(details) if details is not None else None,
        )
        session.add(row)
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

    @staticmethod
    def _parse_json_text(value: str | None) -> dict[str, Any] | None:
        if value is None:
            return None
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def _get_rule_reusable_filter_ids(self, *, rule_id: str) -> list[str]:
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(RuleReusableFilterRow.reusable_filter_id)
                .where(RuleReusableFilterRow.rule_id == rule_id)
                .order_by(RuleReusableFilterRow.reusable_filter_id.asc())
            ).all()

        reusable_filter_ids: list[str] = []
        for row in rows:
            reusable_filter_id = row[0] if isinstance(row, tuple) else row
            reusable_filter_id = str(reusable_filter_id or "").strip()
            if reusable_filter_id and reusable_filter_id not in reusable_filter_ids:
                reusable_filter_ids.append(reusable_filter_id)
        return reusable_filter_ids

    def _to_rule_entity(self, row: RuleRow, *, reusable_filter_ids: list[str] | None = None) -> RuleEntity:
        created_by_user_id = str(row.created_by or "").strip() or "user-admin"
        row_comments = getattr(row, "comments", None)
        check_type_params: dict | None = None
        if row.check_type_params:
            try:
                check_type_params = json.loads(str(row.check_type_params))
            except (TypeError, ValueError):
                check_type_params = None
        dsl: dict | None = None
        row_dsl = getattr(row, "dsl", None)
        if row_dsl:
            try:
                dsl = json.loads(str(row_dsl))
            except (TypeError, ValueError):
                dsl = None
        taxonomy: dict | None = None
        row_taxonomy = getattr(row, "taxonomy", None)
        if row_taxonomy:
            try:
                taxonomy = json.loads(str(row_taxonomy))
            except (TypeError, ValueError):
                taxonomy = None
        taxonomy = self._merge_row_taxonomy(row, taxonomy)

        return RuleEntity(
            id=str(row.id or ""),
            name=str(row.name or ""),
            description=str(row.description) if row.description is not None else None,
            comments=str(row_comments) if row_comments is not None else None,
            expression=str(row.expression or ""),
            dimension=str(row.dimension or ""),
            active=bool(row.active),
            lifecycle_status=str(row.lifecycle_status or "").strip() or rule_policy.derive_rule_lifecycle_status_from_row(row),
            workspace=str(row.workspace or "").strip() or None,
            createdByUserId=created_by_user_id,
            tagIds=[],
            manual_override_by=str(row.manual_override_by or "").strip() or None,
            manual_override_at=self._to_text(row.manual_override_at),
            checkType=str(row.check_type or "").strip() or None,
            checkTypeParams=check_type_params,
            reusableJoinId=str(row.reusable_join_id or "").strip() or None,
            reusableFilterIds=list(reusable_filter_ids or []),
            dsl=dsl,
            taxonomy=taxonomy,
        )

    def _serialize_rule_row(self, row: RuleRow) -> dict[str, Any]:
        removed_at = self._to_text(row.deleted_on)
        removed_by = row.deleted_by
        removed = bool(row.deleted_on)
        row_comments = getattr(row, "comments", None)
        dsl: dict | None = None
        row_dsl = getattr(row, "dsl", None)
        if row_dsl:
            try:
                dsl = json.loads(str(row_dsl))
            except (TypeError, ValueError):
                dsl = None
        taxonomy: dict | None = None
        row_taxonomy = getattr(row, "taxonomy", None)
        if row_taxonomy:
            try:
                taxonomy = json.loads(str(row_taxonomy))
            except (TypeError, ValueError):
                taxonomy = None
        taxonomy = self._merge_row_taxonomy(row, taxonomy)
        return {
            "id": str(row.id or ""),
            "name": str(row.name or ""),
            "description": str(row.description) if row.description is not None else None,
            "comments": str(row_comments) if row_comments is not None else None,
            "expression": str(row.expression or ""),
            "dimension": str(row.dimension or ""),
            "active": bool(row.active),
            "generated": bool(row.generated),
            "is_template": bool(row.is_template),
            "template_id": row.template_id,
            "workspace": row.workspace,
            "created_by": row.created_by,
            "last_approval_by": row.last_approval_by,
            "last_approval_status": row.last_approval_status,
            "lifecycle_status": str(row.lifecycle_status or "").strip() or rule_policy.derive_rule_lifecycle_status_from_row(row),
            "last_approval_at": self._to_text(row.last_approval_at),
            "removed": removed,
            "removed_at": removed_at,
            "removed_by": removed_by,
            "deleted_on": self._to_text(row.deleted_on),
            "deleted_by": row.deleted_by,
            "suggestion_id": row.suggestion_id,
            "dsl": dsl,
            "taxonomy": taxonomy,
            "join_conditions": row.join_conditions,
            "alias_mappings": row.alias_mappings,
            "reusable_join_id": row.reusable_join_id,
            "manual_override_by": row.manual_override_by,
            "manual_override_at": self._to_text(row.manual_override_at),
            "check_type": row.check_type,
            "check_type_params": row.check_type_params,
            "validation_status": row.validation_status,
            "validated_at": self._to_text(row.validated_at),
            "current_version_id": row.current_version_id,
            "total_versions": row.total_versions,
            "versioning_enabled": row.versioning_enabled,
            "version_created_at": self._to_text(row.version_created_at),
            "version_updated_at": self._to_text(row.version_updated_at),
            "tagIds": [],
            "reusableFilterIds": [],
            "reusableFilters": [],
        }

    def _serialize_version_row(
        self,
        row: RuleVersionRow,
        *,
        created_by_name: str,
        validated_by_name: str,
        current_version_id: str,
    ) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "ruleId": str(row.rule_id),
            "versionNumber": int(row.version_number),
            "createdAt": self._to_text(row.created_at),
            "createdBy": created_by_name,
            "changeType": str(row.change_type or "modified"),
            "changeDescription": row.change_description,
            "markedForRollback": bool(row.marked_for_rollback),
            "tags": list(row.tags or []),
            "isCurrentVersion": str(row.id) == current_version_id,
            "validationStatus": row.validation_status,
            "validatedAt": self._to_text(row.validated_at),
            "validatedBy": validated_by_name,
            "validatedByUserId": row.validated_by,
        }

    def _serialize_version_detail(
        self,
        row: RuleVersionRow,
        *,
        created_by_name: str,
        validated_by_name: str,
    ) -> dict[str, Any]:
        check_type_params: dict[str, Any] | None = None
        if row.check_type_params:
            try:
                check_type_params = json.loads(str(row.check_type_params))
            except (TypeError, ValueError):
                check_type_params = None
        dsl: dict[str, Any] | None = None
        row_dsl = getattr(row, "dsl", None)
        if row_dsl:
            try:
                dsl = json.loads(str(row_dsl))
            except (TypeError, ValueError):
                dsl = None
        taxonomy: dict[str, Any] | None = None
        row_taxonomy = getattr(row, "taxonomy", None)
        if row_taxonomy:
            try:
                taxonomy = json.loads(str(row_taxonomy))
            except (TypeError, ValueError):
                taxonomy = None
        taxonomy = self._merge_row_taxonomy(row, taxonomy)

        return {
            "id": str(row.id),
            "ruleId": str(row.rule_id),
            "versionNumber": int(row.version_number),
            "createdAt": self._to_text(row.created_at),
            "createdBy": created_by_name,
            "changeType": str(row.change_type or "modified"),
            "changeDescription": row.change_description,
            "name": str(row.name),
            "description": row.description,
            "expression": str(row.expression),
            "dimension": row.dimension,
            "active": bool(row.active),
            "isTemplate": bool(row.is_template),
            "templateId": row.template_id,
            "dsl": dsl,
            "taxonomy": taxonomy,
            "checkType": row.check_type,
            "checkTypeParams": check_type_params,
            "tags": list(row.tags or []),
            "markedForRollback": bool(row.marked_for_rollback),
            "validationStatus": row.validation_status,
            "validatedAt": self._to_text(row.validated_at),
            "validatedBy": validated_by_name,
            "validatedByUserId": row.validated_by,
        }

    def _serialize_rollback_row(
        self,
        row,
        *,
        rolled_back_by: str,
        version_numbers: dict[str, int],
    ) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "ruleId": str(row.rule_id),
            "fromVersionId": str(row.from_version_id),
            "toVersionId": str(row.to_version_id),
            "rolledBackBy": rolled_back_by,
            "rolledBackAt": self._to_text(row.rolled_back_at),
            "reason": row.reason,
            "newVersionCreatedId": str(row.new_version_created_id or ""),
            "fromVersionNumber": int(version_numbers.get(str(row.from_version_id), 0)),
            "toVersionNumber": int(version_numbers.get(str(row.to_version_id), 0)),
            "newVersionNumber": int(version_numbers.get(str(row.new_version_created_id), 0)),
        }

    def _serialize_rule_status_history_row(self, row: RuleStatusHistoryRow) -> dict[str, Any]:
        return {
            "ruleId": str(row.rule_id),
            "action": str(getattr(row, "action", None) or "transition"),
            "fromStatus": str(row.from_status) if row.from_status is not None else None,
            "toStatus": str(row.to_status),
            "changedBy": str(row.changed_by) if row.changed_by is not None else None,
            "changedAt": self._to_text(row.changed_at),
            "reason": row.reason,
            "details": self._parse_json_text(getattr(row, "details", None)),
        }

    def _serialize_compiler_artifact_row(self, row) -> dict[str, Any]:
        diagnostics_obj = row.diagnostics_payload if isinstance(row.diagnostics_payload, dict) else {}
        diagnostics_items = diagnostics_obj.get("items") if isinstance(diagnostics_obj, dict) else []
        return {
            "id": str(row.id),
            "ruleVersionId": str(row.rule_version_id),
            "compilerVersion": str(row.compiler_version),
            "compilerRevision": int(row.compiler_revision),
            "artifactKey": str(row.artifact_key),
            "artifactPayload": row.artifact_payload or {},
            "diagnosticsPayload": diagnostics_items if isinstance(diagnostics_items, list) else [],
            "compileStatus": str(row.compile_status),
            "sourceFingerprint": str(row.source_fingerprint),
            "isActive": bool(row.is_active),
            "createdAt": self._to_text(row.created_at),
        }

    def _serialize_reusable_filter_row(self, row) -> dict[str, Any]:
        expression = str(row.filter_expression or "")
        return {
            "id": str(row.id),
            "name": str(row.name),
            "description": row.description,
            "filter_expression": expression,
            "expression": expression,
            "workspace": row.workspace,
            "created_by": row.created_by,
            "active": bool(row.active),
            "created_at": self._to_text(row.created_at),
            "updated_at": self._to_text(row.updated_at),
        }

    def _serialize_reusable_join_row(self, row) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "name": str(row.name),
            "description": row.description,
            "join_definition": str(row.join_definition or ""),
            "workspace": row.workspace,
            "created_by": row.created_by,
            "active": bool(row.active),
            "created_at": self._to_text(row.created_at),
            "updated_at": self._to_text(row.updated_at),
        }

    @staticmethod
    def _to_text(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat().replace("+00:00", "Z")

    async def get_user_by_id(self, user_id: str):
        from app.domain.entities import RuleCreatorEntity
        with session_scope(self.database_url) as session:
            row = session.get(UserRow, user_id)

        if row is None:
            return None

        display_name = compose_user_display_name(row.first_name, row.last_name, fallback=row.email or row.id or user_id)
        username = self._username_for_user(row)
        return RuleCreatorEntity(id=str(row.id or user_id), username=username, display_name=display_name)

    async def get_tags_by_ids(self, tag_ids: list[str]) -> list[RuleTagEntity]:
        result: list[RuleTagEntity] = []
        for tag_id in tag_ids:
            normalized = str(tag_id).strip()
            if not normalized:
                continue
            result.append(
                RuleTagEntity(
                    id=normalized,
                    name=self._display_name_for_tag(normalized),
                )
            )
        return result
