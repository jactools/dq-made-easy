from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy import update

from app.infrastructure.orm.models import RuleRow
from app.infrastructure.orm.models import RuleRollbackRow
from app.infrastructure.orm.models import RuleCurrentVersionRow
from app.infrastructure.orm.models import RuleVersionRow
from app.infrastructure.orm.session import session_scope


class RuleVersionsMixin:

    async def list_rule_versions(self, rule_id: str, limit: int = 20, offset: int = 0) -> dict | None:
        with session_scope(self.database_url) as session:
            rule = self._get_rule_row(session, rule_id)
            if rule is None:
                return None

            rows = session.execute(
                select(RuleVersionRow)
                .where(RuleVersionRow.rule_id == rule_id)
                .order_by(RuleVersionRow.version_number.desc(), RuleVersionRow.created_at.desc())
            ).scalars().all()

            creators = self._load_creator_names(
                session,
                [str(row.created_by) for row in rows if row.created_by],
            )
            validators = self._load_creator_names(
                session,
                [str(row.validated_by) for row in rows if row.validated_by],
            )

        safe_limit = max(1, min(100, limit))
        safe_offset = max(0, offset)
        window = rows[safe_offset : safe_offset + safe_limit]
        current_version_number = next(
            (
                row.version_number
                for row in rows
                if str(row.id or "") == str(rule.current_version_id or "")
            ),
            0,
        )

        return {
            "ruleId": rule_id,
            "ruleName": str(rule.name or rule_id),
            "versioning": {
                "enabled": bool(rule.versioning_enabled),
                "currentVersion": int(current_version_number or 0),
                "totalVersions": len(rows),
            },
            "pagination": {
                "limit": safe_limit,
                "offset": safe_offset,
                "total": len(rows),
                "hasMore": safe_offset + safe_limit < len(rows),
            },
            "versions": [
                self._serialize_version_row(
                    row,
                    created_by_name=creators.get(str(row.created_by or ""), str(row.created_by or "system")),
                    validated_by_name=validators.get(str(row.validated_by or ""), str(row.validated_by or "")),
                    current_version_id=str(rule.current_version_id or ""),
                )
                for row in window
            ],
        }

    async def get_rule_version(self, rule_id: str, version_id: str) -> dict | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(RuleVersionRow)
                .where(RuleVersionRow.rule_id == rule_id)
                .where(RuleVersionRow.id == version_id)
                .limit(1)
            ).scalar_one_or_none()

            if row is None:
                return None

            user_names = self._load_creator_names(
                session,
                [
                    str(row.created_by),
                    str(row.validated_by or ""),
                ],
            )

            created_by_name = user_names.get(
                str(row.created_by),
                str(row.created_by or "system"),
            )
            validated_by_name = user_names.get(
                str(row.validated_by or ""),
                str(row.validated_by or ""),
            )

        return self._serialize_version_detail(
            row,
            created_by_name=created_by_name,
            validated_by_name=validated_by_name,
        )

    async def get_rule_rollback_history(
        self,
        rule_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> dict | None:
        with session_scope(self.database_url) as session:
            rule = self._get_rule_row(session, rule_id)
            if rule is None:
                return None

            rows = session.execute(
                select(RuleRollbackRow)
                .where(RuleRollbackRow.rule_id == rule_id)
                .order_by(RuleRollbackRow.rolled_back_at.desc())
            ).scalars().all()

            version_ids = {
                str(version_id)
                for row in rows
                for version_id in (row.from_version_id, row.to_version_id, row.new_version_created_id)
                if version_id
            }
            version_numbers = self._load_version_numbers(session, version_ids)
            creators = self._load_creator_names(
                session,
                [str(row.rolled_back_by) for row in rows if row.rolled_back_by],
            )

        safe_limit = max(1, min(100, limit))
        safe_offset = max(0, offset)
        window = rows[safe_offset : safe_offset + safe_limit]

        return {
            "ruleId": rule_id,
            "rollbacks": [
                self._serialize_rollback_row(
                    row,
                    rolled_back_by=creators.get(str(row.rolled_back_by or ""), str(row.rolled_back_by or "system")),
                    version_numbers=version_numbers,
                )
                for row in window
            ],
            "pagination": {
                "limit": safe_limit,
                "offset": safe_offset,
                "total": len(rows),
                "hasMore": safe_offset + safe_limit < len(rows),
            },
        }

    async def compare_rule_versions(
        self,
        rule_id: str,
        version_1: str,
        version_2: str,
    ) -> dict | None:
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(RuleVersionRow)
                .where(RuleVersionRow.rule_id == rule_id)
                .where(RuleVersionRow.id.in_([version_1, version_2]))
            ).scalars().all()

            versions = {str(row.id): row for row in rows}
            first = versions.get(version_1)
            second = versions.get(version_2)
            if first is None or second is None:
                return None

            creators = self._load_creator_names(
                session,
                [str(first.created_by), str(second.created_by)],
            )

        details: list[dict[str, Any]] = []
        for field_name in ("name", "description", "expression", "dimension", "active"):
            old_value = getattr(first, field_name)
            new_value = getattr(second, field_name)
            if old_value != new_value:
                details.append(
                    {
                        "field": field_name,
                        "oldValue": old_value,
                        "newValue": new_value,
                        "changeType": "modified",
                    }
                )

        first_tags = sorted(first.tags or [])
        second_tags = sorted(second.tags or [])
        if first_tags != second_tags:
            details.append(
                {
                    "field": "tags",
                    "oldValue": first_tags,
                    "newValue": second_tags,
                    "changeType": "modified",
                }
            )

        return {
            "fromVersion": {
                "id": str(first.id),
                "versionNumber": int(first.version_number),
                "createdAt": self._to_text(first.created_at),
                "createdBy": creators.get(str(first.created_by), str(first.created_by or "system")),
            },
            "toVersion": {
                "id": str(second.id),
                "versionNumber": int(second.version_number),
                "createdAt": self._to_text(second.created_at),
                "createdBy": creators.get(str(second.created_by), str(second.created_by or "system")),
            },
            "changes": {
                "summary": {
                    "fieldsChanged": len(details),
                    "totalChanges": len(details),
                },
                "details": details,
            },
        }

    async def get_rule_version_statistics(self, rule_id: str) -> dict | None:
        with session_scope(self.database_url) as session:
            rule = self._get_rule_row(session, rule_id)
            if rule is None:
                return None

            version_rows = session.execute(
                select(RuleVersionRow)
                .where(RuleVersionRow.rule_id == rule_id)
                .order_by(RuleVersionRow.version_number.desc())
            ).scalars().all()
            rollback_rows = session.execute(
                select(RuleRollbackRow)
                .where(RuleRollbackRow.rule_id == rule_id)
                .order_by(RuleRollbackRow.rolled_back_at.desc())
            ).scalars().all()

        change_types: dict[str, int] = {}
        active_count = 0
        marked_for_rollback = 0
        testing_rows: list[dict[str, Any]] = []
        rollback_targets: dict[str, int] = {}

        for row in version_rows:
            change_type = str(row.change_type or "unknown")
            change_types[change_type] = change_types.get(change_type, 0) + 1
            if bool(row.active):
                active_count += 1
            if bool(row.marked_for_rollback):
                marked_for_rollback += 1
            testing_rows.append(
                {
                    "versionId": str(row.id),
                    "versionNumber": int(row.version_number),
                    "testCount": 0,
                    "passedTests": 0,
                    "avgCoverage": None,
                }
            )

        for row in rollback_rows:
            key = str(row.to_version_id or "")
            if key:
                rollback_targets[key] = rollback_targets.get(key, 0) + 1

        return {
            "versions": {
                "total": len(version_rows),
                "active": active_count,
                "markedForRollback": marked_for_rollback,
                "changeTypes": change_types,
            },
            "testing": testing_rows,
            "rollbacks": {
                "total": len(rollback_rows),
                "rollbackTargets": rollback_targets,
            },
        }

    async def execute_rule_rollback(
        self,
        rule_id: str,
        to_version_id: str,
        reason: str,
        requested_by_user_id: str | None = None,
        skip_approval: bool = False,
        tags: list[str] | None = None,
    ) -> dict | None:
        actor_id = str(requested_by_user_id or "").strip() or "user-admin"

        with session_scope(self.database_url) as session:
            rule = self._get_rule_row(session, rule_id)
            if rule is None:
                return None

            if str(rule.current_version_id or "") == to_version_id:
                raise ValueError("Cannot rollback to the current version")

            if not rule.current_version_id:
                raise ValueError("Rule has no current version to rollback from")

            target = session.execute(
                select(RuleVersionRow)
                .where(RuleVersionRow.rule_id == rule_id)
                .where(RuleVersionRow.id == to_version_id)
                .limit(1)
            ).scalar_one_or_none()
            if target is None:
                raise LookupError(f"Version '{to_version_id}' not found for rule '{rule_id}'")

            current_version_id = str(rule.current_version_id)
            completed_at_dt = datetime.now(UTC)
            new_version_number = int(rule.total_versions or 1) + 1
            new_version_id = f"rv_{uuid4()}"
            rollback_id = f"rb_{uuid4()}"

            new_version = RuleVersionRow(
                id=new_version_id,
                rule_id=rule_id,
                version_number=new_version_number,
                created_at=completed_at_dt,
                created_by=actor_id,
                change_type="rollback",
                change_description=f"Rollback from version {int(target.version_number)}",
                name=str(target.name),
                description=target.description,
                expression=str(target.expression),
                dimension=target.dimension,
                active=bool(target.active),
                is_template=bool(target.is_template),
                template_id=target.template_id,
                dsl=getattr(target, "dsl", None),
                taxonomy=getattr(target, "taxonomy", None),
                check_type=target.check_type,
                check_type_params=target.check_type_params,
                tags=list(tags) if tags is not None else None,
            )
            session.add(new_version)
            session.flush()

            rollback_row = RuleRollbackRow(
                id=rollback_id,
                rule_id=rule_id,
                from_version_id=current_version_id,
                to_version_id=to_version_id,
                rolled_back_by=actor_id,
                rolled_back_at=completed_at_dt,
                reason=reason,
                new_version_created_id=new_version_id,
            )
            session.add(rollback_row)

            current_pointer = session.get(RuleCurrentVersionRow, rule_id)
            if current_pointer is None:
                session.add(RuleCurrentVersionRow(rule_id=rule_id, version_id=new_version_id))
            else:
                current_pointer.version_id = new_version_id
            rule.name = str(target.name)
            rule.description = target.description
            rule.expression = str(target.expression)
            rule.dimension = target.dimension
            rule.active = bool(target.active)
            rule.dsl = getattr(target, "dsl", None)
            rule.taxonomy = getattr(target, "taxonomy", None)
            rule.check_type = target.check_type
            rule.check_type_params = target.check_type_params
            rule.total_versions = new_version_number
            rule.version_updated_at = completed_at_dt

            session.commit()

            actor_name = self._load_creator_names(session, [actor_id]).get(actor_id, actor_id)
            current_version_number = self._load_version_numbers(
                session,
                {current_version_id},
            ).get(current_version_id, 0)

        completed_at = self._to_text(completed_at_dt)
        if completed_at is None:
            completed_at = datetime.now(UTC).isoformat()

        return {
            "id": rollback_id,
            "status": "processing",
            "fromVersion": {
                "id": current_version_id,
                "versionNumber": int(current_version_number or 0),
            },
            "toVersion": {
                "id": str(target.id),
                "versionNumber": int(target.version_number),
            },
            "newVersionCreated": {
                "id": new_version_id,
                "versionNumber": int(new_version_number),
                "status": "activated" if skip_approval else "pending_approval",
            },
            "rolledBackBy": {
                "name": actor_name,
            },
            "rolledBackAt": completed_at,
            "estimatedCompletionTime": completed_at,
            "links": {
                "checkStatus": f"/rulebuilder/v1/rules/{rule_id}/rollbacks/{rollback_id}",
                "viewNewVersion": f"/rulebuilder/v1/rules/{rule_id}/versions/{new_version_id}",
            },
        }

    async def update_rule_version_tags(
        self,
        rule_id: str,
        version_id: str,
        tags: list[str],
        updated_by_user_id: str | None = None,
    ) -> dict | None:
        actor_id = str(updated_by_user_id or "").strip() or "user-admin"

        with session_scope(self.database_url) as session:
            row = session.execute(
                select(RuleVersionRow)
                .where(RuleVersionRow.rule_id == rule_id)
                .where(RuleVersionRow.id == version_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None

            session.execute(
                update(RuleVersionRow)
                .where(RuleVersionRow.id == version_id)
                .values(tags=list(tags))
            )
            session.commit()

            actor_name = self._load_creator_names(session, [actor_id]).get(actor_id, actor_id)

        updated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return {
            "id": version_id,
            "versionNumber": int(row.version_number),
            "tags": list(tags),
            "updatedAt": updated_at,
            "updatedBy": {
                "id": actor_id,
                "name": actor_name,
            },
        }

    async def mark_rule_version_for_rollback(
        self,
        rule_id: str,
        version_id: str,
        marked: bool,
    ) -> dict | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(RuleVersionRow)
                .where(RuleVersionRow.rule_id == rule_id)
                .where(RuleVersionRow.id == version_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None

            session.execute(
                update(RuleVersionRow)
                .where(RuleVersionRow.id == version_id)
                .values(marked_for_rollback=bool(marked))
            )
            session.commit()

        return {
            "id": version_id,
            "marked": bool(marked),
        }

    async def set_current_rule_version_validation(
        self,
        *,
        rule_id: str,
        validation_status: str,
        validated_by: str | None,
    ) -> dict | None:
        with session_scope(self.database_url) as session:
            rule = self._get_rule_row(session, rule_id)
            if rule is None:
                return None

            current_version_id = str(rule.current_version_id or "").strip()
            if not current_version_id:
                return None

            version_row = session.execute(
                select(RuleVersionRow)
                .where(RuleVersionRow.rule_id == rule_id)
                .where(RuleVersionRow.id == current_version_id)
                .limit(1)
            ).scalar_one_or_none()
            if version_row is None:
                return None

            now = datetime.now(UTC)
            version_row.validation_status = str(validation_status or "").strip() or None
            version_row.validated_at = now
            version_row.validated_by = str(validated_by or "").strip() or None

            # Keep legacy rule-level fields in sync for existing consumers.
            rule.validation_status = version_row.validation_status
            rule.validated_at = now

            validator_id = str(version_row.validated_by or "")
            validator_name = ""
            if validator_id:
                validator_name = self._load_creator_names(session, [validator_id]).get(validator_id, validator_id)

            session.commit()

        return {
            "ruleId": rule_id,
            "versionId": current_version_id,
            "validationStatus": version_row.validation_status,
            "validatedAt": self._to_text(version_row.validated_at),
            "validatedBy": validator_name,
            "validatedByUserId": version_row.validated_by,
        }
