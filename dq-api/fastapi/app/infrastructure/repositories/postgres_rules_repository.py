from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import update

from app.domain.entities import build_rule_record_entity, RuleCreatorEntity, RuleEntity, RuleRecordEntity, RuleTagEntity
from app.domain.entities import rule_policy
from app.domain.status_governance import canonicalize_status
from app.domain.status_governance import is_transition_defined
from app.domain.interfaces.v1.rules_repository import RulesRepository
from app.domain.user_names import compose_user_display_name
from app.infrastructure.orm.models import RuleRow
from app.infrastructure.orm.models import RuleRollbackRow
from app.infrastructure.orm.models import RuleCurrentVersionRow
from app.infrastructure.orm.models import RuleStatusHistoryRow
from app.infrastructure.orm.models import RuleReusableFilterRow
from app.infrastructure.orm.models import RuleVersionCompilerArtifactRow
from app.infrastructure.orm.models import RuleVersionRow
from app.infrastructure.orm.models import ReusableFilterRow
from app.infrastructure.orm.models import ReusableJoinRow
from app.infrastructure.orm.models import UserRow
from app.infrastructure.orm.session import session_scope


class PostgresRulesRepository(RulesRepository):
    """Postgres-backed rules repository."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

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

    async def list_rule_records(
        self,
        workspace: str | None = None,
        include_deleted: bool = False,
        is_template: bool | None = None,
        query: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[RuleRecordEntity]:
        return [
            record
            for record in (
                build_rule_record_entity(payload)
                for payload in await self._list_rule_payloads(
                    workspace=workspace,
                    include_deleted=include_deleted,
                    is_template=is_template,
                    query=query,
                    limit=limit,
                    offset=offset,
                )
            )
            if record is not None
        ]

    async def _list_rule_payloads(
        self,
        workspace: str | None = None,
        include_deleted: bool = False,
        is_template: bool | None = None,
        query: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        del limit, offset

        with session_scope(self.database_url) as session:
            stmt = select(RuleRow)
            filters = [RuleRow.generated.is_not(True)]
            if not include_deleted:
                filters.append(RuleRow.deleted_on.is_(None))
            if workspace:
                filters.append(RuleRow.workspace == workspace)
            if is_template is True:
                filters.append(RuleRow.is_template.is_(True))
            normalized_query = str(query or "").strip()
            if normalized_query:
                pattern = f"%{normalized_query}%"
                filters.append(
                    or_(
                        RuleRow.id.ilike(pattern),
                        RuleRow.name.ilike(pattern),
                        RuleRow.description.ilike(pattern),
                        RuleRow.expression.ilike(pattern),
                    )
                )
            if filters:
                stmt = stmt.where(and_(*filters))
            # Keep rules with version history first, then most recently changed
            # rows. This avoids selecting null-version rows as page head.
            stmt = stmt.order_by(
                RuleRow.current_version_id.is_(None),
                RuleRow.version_updated_at.desc().nullslast(),
                RuleRow.id.desc(),
            )
            rows = session.execute(stmt).scalars().all()

        return [self._serialize_rule_row(row) for row in rows]

    async def get_rule_by_id(self, rule_id: str) -> RuleEntity | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(RuleRow)
                .where(RuleRow.id == rule_id)
                .where(RuleRow.deleted_on.is_(None))
                .limit(1)
            ).scalar_one_or_none()

        if row is None:
            return None
        reusable_filter_ids = self._get_rule_reusable_filter_ids(rule_id=rule_id)
        return self._to_rule_entity(row, reusable_filter_ids=reusable_filter_ids)

    async def _create_rule_payload(
        self,
        *,
        name: str,
        description: str | None,
        comments: str | None = None,
        expression: str,
        dimension: str,
        active: bool,
        workspace: str,
        created_by: str,
        generated: bool,
        is_template: bool,
        template_id: str | None,
        suggestion_id: str | None,
        dsl: dict | None,
        join_conditions: list[dict],
        alias_mappings: dict,
        reusable_join_id: str | None,
        reusable_filter_ids: list[str],
        manual_override_by: str | None,
        manual_override_at: datetime | None,
        check_type: str | None,
        check_type_params: dict | None,
        taxonomy: dict | None,
    ) -> dict:
        rule_id = f"rule-{uuid4().hex}"
        initial_version_id = f"rv_{uuid4()}"
        now = datetime.now(UTC)

        with session_scope(self.database_url) as session:
            row = RuleRow(
                id=rule_id,
                name=name,
                description=description,
                comments=comments,
                expression=expression,
                dimension=dimension,
                active=bool(active),
                generated=bool(generated),
                is_template=bool(is_template),
                template_id=template_id,
                workspace=workspace,
                created_by=created_by,
                suggestion_id=suggestion_id,
                lifecycle_status="active",
                dsl=json.dumps(dsl) if dsl is not None else None,
                taxonomy=json.dumps(taxonomy) if taxonomy is not None else None,
                data_steward=self._taxonomy_text(taxonomy, "data_steward", "owner") or created_by,
                domain_owner=self._taxonomy_text(taxonomy, "domain_owner"),
                technical_owner=self._taxonomy_text(taxonomy, "technical_owner"),
                join_conditions=json.dumps(join_conditions),
                alias_mappings=json.dumps(alias_mappings),
                reusable_join_id=reusable_join_id,
                manual_override_by=manual_override_by,
                manual_override_at=manual_override_at,
                check_type=check_type,
                check_type_params=json.dumps(check_type_params) if check_type_params is not None else None,
                total_versions=1,
                version_created_at=now,
                version_updated_at=now,
            )
            session.add(row)
            session.add(
                RuleVersionRow(
                    id=initial_version_id,
                    rule_id=rule_id,
                    version_number=1,
                    created_at=now,
                    created_by=created_by,
                    change_type="created",
                    change_description="Rule created",
                    name=name,
                    description=description,
                    expression=expression,
                    dimension=dimension,
                    active=bool(active),
                    is_template=bool(is_template),
                    template_id=template_id,
                    dsl=json.dumps(dsl) if dsl is not None else None,
                    taxonomy=json.dumps(taxonomy) if taxonomy is not None else None,
                    data_steward=self._taxonomy_text(taxonomy, "data_steward", "owner") or str(row.created_by or "").strip() or None,
                    domain_owner=self._taxonomy_text(taxonomy, "domain_owner"),
                    technical_owner=self._taxonomy_text(taxonomy, "technical_owner"),
                    lifecycle_status="active",
                    check_type=check_type,
                    check_type_params=json.dumps(check_type_params) if check_type_params is not None else None,
                    tags=[],
                    marked_for_rollback=False,
                    validation_status=None,
                    validated_at=None,
                    validated_by=None,
                )
            )
            session.flush()
            session.add(RuleCurrentVersionRow(rule_id=rule_id, version_id=initial_version_id))
            self._append_rule_status_history_row(
                session,
                rule_id=rule_id,
                action="create",
                from_status=None,
                to_status="activated" if bool(active) else "draft",
                changed_by=created_by,
                reason="Rule created",
                allow_same_status=True,
            )

            for reusable_filter_id in sorted({value for value in reusable_filter_ids if value}):
                session.add(
                    RuleReusableFilterRow(
                        rule_id=rule_id,
                        reusable_filter_id=reusable_filter_id,
                    )
                )

            session.commit()
            session.refresh(row)
            payload = self._serialize_rule_row(row)

        payload["joinConditions"] = join_conditions
        payload["aliasMappings"] = alias_mappings
        payload["reusableFilterIds"] = list(reusable_filter_ids)
        payload["reusableFilters"] = []
        payload["current_version_id"] = initial_version_id
        return payload

    async def create_rule_record(
        self,
        *,
        name: str,
        description: str | None,
        comments: str | None = None,
        expression: str,
        dimension: str,
        active: bool,
        workspace: str,
        created_by: str,
        generated: bool,
        is_template: bool,
        template_id: str | None,
        suggestion_id: str | None,
        dsl: dict | None,
        join_conditions: list[dict],
        alias_mappings: dict,
        reusable_join_id: str | None,
        reusable_filter_ids: list[str],
        manual_override_by: str | None,
        manual_override_at: datetime | None,
        check_type: str | None,
        check_type_params: dict | None,
        taxonomy: dict | None,
    ) -> RuleRecordEntity:
        payload = await self._create_rule_payload(
            name=name,
            description=description,
            comments=comments,
            expression=expression,
            dimension=dimension,
            active=active,
            workspace=workspace,
            created_by=created_by,
            generated=generated,
            is_template=is_template,
            template_id=template_id,
            suggestion_id=suggestion_id,
            dsl=dsl,
            join_conditions=join_conditions,
            alias_mappings=alias_mappings,
            reusable_join_id=reusable_join_id,
            reusable_filter_ids=reusable_filter_ids,
            manual_override_by=manual_override_by,
            manual_override_at=manual_override_at,
            check_type=check_type,
            check_type_params=check_type_params,
            taxonomy=taxonomy,
        )
        record = build_rule_record_entity(payload)
        if record is None:
            raise ValueError("Created rule payload is invalid")
        return record

    async def _update_rule_payload(
        self,
        *,
        rule_id: str,
        name: str,
        description: str | None,
        comments: str | None = None,
        expression: str,
        dimension: str,
        active: bool,
        dsl: dict | None,
        join_conditions: list[dict],
        alias_mappings: dict,
        reusable_join_id: str | None,
        reusable_filter_ids: list[str],
        manual_override_by: str | None,
        manual_override_at: datetime | None,
        check_type: str | None,
        check_type_params: dict | None,
        taxonomy: dict | None,
    ) -> dict | None:
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
            desired_status = from_status
            if from_status == "deactivated":
                desired_status = "draft"
            if bool(active) and not bool(row.active):
                desired_status = "activated"
            elif not bool(active) and bool(row.active):
                desired_status = "deactivated"

            self._ensure_rule_transition_allowed(from_status=from_status, to_status=desired_status)

            now = datetime.now(UTC)
            new_version_number = int(row.total_versions or 0) + 1
            new_version_id = f"rv_{uuid4()}"

            row.name = name
            row.description = description
            row.comments = comments
            row.expression = expression
            row.dimension = dimension
            row.active = bool(active)
            row.dsl = json.dumps(dsl) if dsl is not None else None
            row.taxonomy = json.dumps(taxonomy) if taxonomy is not None else None
            row.data_steward = self._taxonomy_text(taxonomy, "data_steward", "owner") or created_by
            row.domain_owner = self._taxonomy_text(taxonomy, "domain_owner")
            row.technical_owner = self._taxonomy_text(taxonomy, "technical_owner")
            row.join_conditions = json.dumps(join_conditions)
            row.alias_mappings = json.dumps(alias_mappings)
            row.reusable_join_id = reusable_join_id
            row.manual_override_by = manual_override_by
            row.manual_override_at = manual_override_at
            row.check_type = check_type
            row.check_type_params = json.dumps(check_type_params) if check_type_params is not None else None
            if from_status == "deactivated":
                row.last_approval_status = "draft"
            row.validation_status = None
            row.validated_at = None
            row.total_versions = new_version_number
            row.version_created_at = now
            row.version_updated_at = now

            new_version_row = RuleVersionRow(
                id=new_version_id,
                rule_id=rule_id,
                version_number=new_version_number,
                created_at=now,
                created_by=str(row.created_by or "system"),
                change_type="modified",
                change_description="Rule updated",
                name=name,
                description=description,
                expression=expression,
                dimension=dimension,
                active=bool(active),
                is_template=bool(row.is_template),
                template_id=row.template_id,
                dsl=json.dumps(dsl) if dsl is not None else None,
                taxonomy=json.dumps(taxonomy) if taxonomy is not None else None,
                data_steward=self._taxonomy_text(taxonomy, "data_steward", "owner") or str(row.created_by or "").strip() or None,
                domain_owner=self._taxonomy_text(taxonomy, "domain_owner"),
                technical_owner=self._taxonomy_text(taxonomy, "technical_owner"),
                lifecycle_status=str(row.lifecycle_status or "").strip() or rule_policy.derive_rule_lifecycle_status_from_row(row),
                check_type=check_type,
                check_type_params=json.dumps(check_type_params) if check_type_params is not None else None,
                marked_for_rollback=False,
                validation_status=None,
                validated_at=None,
                validated_by=None,
            )
            session.add(new_version_row)
            session.flush()

            current_pointer = session.get(RuleCurrentVersionRow, rule_id)
            if current_pointer is None:
                session.add(RuleCurrentVersionRow(rule_id=rule_id, version_id=new_version_id))
            else:
                current_pointer.version_id = new_version_id

            current_links = session.execute(
                select(RuleReusableFilterRow).where(RuleReusableFilterRow.rule_id == rule_id)
            ).scalars().all()
            for link in current_links:
                session.delete(link)
            for reusable_filter_id in sorted({value for value in reusable_filter_ids if value}):
                session.add(
                    RuleReusableFilterRow(
                        rule_id=rule_id,
                        reusable_filter_id=reusable_filter_id,
                    )
                )

            to_status = self._derive_rule_status_from_row(row)
            self._append_rule_status_history_row(
                session,
                rule_id=rule_id,
                action="edit",
                from_status=from_status,
                to_status=to_status,
                changed_by=row.last_approval_by or row.created_by,
                reason="Rule updated",
                allow_same_status=True,
            )

            session.commit()

            payload = self._serialize_rule_row(row)
            payload["current_version_id"] = new_version_id
            payload["validation_status"] = None
            payload["validated_at"] = None
        payload["joinConditions"] = join_conditions
        payload["aliasMappings"] = alias_mappings
        payload["reusableFilterIds"] = list(reusable_filter_ids)
        payload["reusableFilters"] = []
        return payload

    async def update_rule_record(
        self,
        *,
        rule_id: str,
        name: str,
        description: str | None,
        comments: str | None = None,
        expression: str,
        dimension: str,
        active: bool,
        dsl: dict | None,
        join_conditions: list[dict],
        alias_mappings: dict,
        reusable_join_id: str | None,
        reusable_filter_ids: list[str],
        manual_override_by: str | None,
        manual_override_at: datetime | None,
        check_type: str | None,
        check_type_params: dict | None,
        taxonomy: dict | None,
    ) -> RuleRecordEntity | None:
        payload = await self._update_rule_payload(
            rule_id=rule_id,
            name=name,
            description=description,
            comments=comments,
            expression=expression,
            dimension=dimension,
            active=active,
            dsl=dsl,
            join_conditions=join_conditions,
            alias_mappings=alias_mappings,
            reusable_join_id=reusable_join_id,
            reusable_filter_ids=reusable_filter_ids,
            manual_override_by=manual_override_by,
            manual_override_at=manual_override_at,
            check_type=check_type,
            check_type_params=check_type_params,
            taxonomy=taxonomy,
        )
        return build_rule_record_entity(payload)

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

    async def upsert_active_compiler_artifact(
        self,
        *,
        rule_version_id: str,
        compiler_version: str,
        artifact_key: str,
        artifact_payload: dict,
        diagnostics_payload: list[dict],
        compile_status: str,
        source_fingerprint: str,
    ) -> dict:
        now = datetime.now(UTC)
        artifact_id = f"rca-{uuid4().hex}"

        with session_scope(self.database_url) as session:
            version_row = session.execute(
                select(RuleVersionRow)
                .where(RuleVersionRow.id == rule_version_id)
                .limit(1)
            ).scalar_one_or_none()
            if version_row is None:
                raise LookupError(f"Rule version '{rule_version_id}' not found")

            existing_rows = session.execute(
                select(RuleVersionCompilerArtifactRow)
                .where(RuleVersionCompilerArtifactRow.rule_version_id == rule_version_id)
                .order_by(RuleVersionCompilerArtifactRow.compiler_revision.desc())
            ).scalars().all()

            for row in existing_rows:
                row.is_active = False

            next_revision = (max((int(row.compiler_revision or 0) for row in existing_rows), default=0)) + 1

            new_row = RuleVersionCompilerArtifactRow(
                id=artifact_id,
                rule_version_id=rule_version_id,
                compiler_version=compiler_version,
                compiler_revision=next_revision,
                artifact_key=artifact_key,
                artifact_payload=artifact_payload,
                diagnostics_payload={"items": diagnostics_payload},
                compile_status=compile_status,
                source_fingerprint=source_fingerprint,
                is_active=True,
                created_at=now,
            )
            session.add(new_row)
            session.commit()

        return self._serialize_compiler_artifact_row(new_row)

    async def get_active_compiler_artifact(self, rule_version_id: str) -> dict | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(RuleVersionCompilerArtifactRow)
                .where(RuleVersionCompilerArtifactRow.rule_version_id == rule_version_id)
                .where(RuleVersionCompilerArtifactRow.is_active.is_(True))
                .order_by(RuleVersionCompilerArtifactRow.compiler_revision.desc())
                .limit(1)
            ).scalar_one_or_none()

        if row is None:
            return None
        return self._serialize_compiler_artifact_row(row)

    async def list_compiler_artifacts(self, rule_version_id: str) -> list[dict]:
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(RuleVersionCompilerArtifactRow)
                .where(RuleVersionCompilerArtifactRow.rule_version_id == rule_version_id)
                .order_by(RuleVersionCompilerArtifactRow.compiler_revision.desc())
            ).scalars().all()

        return [self._serialize_compiler_artifact_row(row) for row in rows]

    async def list_reusable_filters(self, workspace: str | None = None, query: str | None = None) -> list[dict]:
        with session_scope(self.database_url) as session:
            stmt = select(ReusableFilterRow)
            if workspace:
                stmt = stmt.where(ReusableFilterRow.workspace == workspace)
            normalized_query = str(query or "").strip()
            if normalized_query:
                pattern = f"%{normalized_query}%"
                stmt = stmt.where(or_(
                    ReusableFilterRow.name.ilike(pattern),
                    ReusableFilterRow.description.ilike(pattern),
                    ReusableFilterRow.filter_expression.ilike(pattern),
                ))
            stmt = stmt.order_by(ReusableFilterRow.name.asc())
            rows = session.execute(stmt).scalars().all()

        return [self._serialize_reusable_filter_row(row) for row in rows]

    async def create_reusable_filter(
        self,
        *,
        name: str,
        expression: str,
        description: str | None,
        workspace: str,
        created_by: str,
        active: bool,
    ) -> dict:
        filter_id = f"rf_{uuid4().hex}"
        now = datetime.now(UTC)

        with session_scope(self.database_url) as session:
            row = ReusableFilterRow(
                id=filter_id,
                name=name,
                description=description,
                filter_expression=expression,
                workspace=workspace,
                created_by=created_by,
                active=bool(active),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()

        return self._serialize_reusable_filter_row(row)

    async def delete_reusable_filter(self, filter_id: str) -> bool:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ReusableFilterRow)
                .where(ReusableFilterRow.id == filter_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return False

            in_use = session.execute(
                select(RuleReusableFilterRow)
                .join(RuleRow, RuleReusableFilterRow.rule_id == RuleRow.id)
                .where(RuleReusableFilterRow.reusable_filter_id == filter_id)
                .where(RuleRow.deleted_on.is_(None))
                .limit(1)
            ).first()

            if in_use is not None:
                raise ValueError("Cannot delete reusable filter that is assigned to one or more rules")

            session.delete(row)
            session.commit()
            return True

    async def get_reusable_filter(self, filter_id: str) -> dict | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ReusableFilterRow)
                .where(ReusableFilterRow.id == filter_id)
                .limit(1)
            ).scalar_one_or_none()

        if row is None:
            return None
        return self._serialize_reusable_filter_row(row)

    async def update_reusable_filter(
        self,
        *,
        filter_id: str,
        name: str,
        expression: str,
        description: str | None,
        active: bool,
    ) -> dict | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ReusableFilterRow)
                .where(ReusableFilterRow.id == filter_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None

            row.name = name
            row.description = description
            row.filter_expression = expression
            row.active = bool(active)
            row.updated_at = datetime.now(UTC)
            session.commit()

        return self._serialize_reusable_filter_row(row)

    async def list_reusable_joins(self, workspace: str | None = None) -> list[dict]:
        with session_scope(self.database_url) as session:
            stmt = select(ReusableJoinRow)
            if workspace:
                stmt = stmt.where(ReusableJoinRow.workspace == workspace)
            stmt = stmt.order_by(ReusableJoinRow.name.asc())
            rows = session.execute(stmt).scalars().all()

        return [self._serialize_reusable_join_row(row) for row in rows]

    async def create_reusable_join(
        self,
        *,
        name: str,
        join_definition: str,
        description: str | None,
        workspace: str,
        created_by: str,
        active: bool,
    ) -> dict:
        join_id = f"rj_{uuid4().hex}"
        now = datetime.now(UTC)

        with session_scope(self.database_url) as session:
            row = ReusableJoinRow(
                id=join_id,
                name=name,
                description=description,
                join_definition=join_definition,
                workspace=workspace,
                created_by=created_by,
                active=bool(active),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()

        return self._serialize_reusable_join_row(row)

    async def delete_reusable_join(self, join_id: str) -> bool:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ReusableJoinRow)
                .where(ReusableJoinRow.id == join_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return False

            in_use = session.execute(
                select(RuleRow)
                .where(RuleRow.reusable_join_id == join_id)
                .where(RuleRow.deleted_on.is_(None))
                .limit(1)
            ).first()

            if in_use is not None:
                raise ValueError("Cannot delete reusable join that is assigned to one or more rules")

            session.delete(row)
            session.commit()
            return True

    async def get_reusable_join(self, join_id: str) -> dict | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ReusableJoinRow)
                .where(ReusableJoinRow.id == join_id)
                .limit(1)
            ).scalar_one_or_none()

        if row is None:
            return None
        return self._serialize_reusable_join_row(row)

    async def update_reusable_join(
        self,
        *,
        join_id: str,
        name: str,
        join_definition: str,
        description: str | None,
        active: bool,
    ) -> dict | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(ReusableJoinRow)
                .where(ReusableJoinRow.id == join_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None

            row.name = name
            row.description = description
            row.join_definition = join_definition
            row.active = bool(active)
            row.updated_at = datetime.now(UTC)
            session.commit()

        return self._serialize_reusable_join_row(row)

    async def get_user_by_id(self, user_id: str) -> RuleCreatorEntity | None:
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
        row: RuleRollbackRow,
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

    def _serialize_compiler_artifact_row(self, row: RuleVersionCompilerArtifactRow) -> dict[str, Any]:
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

    def _serialize_reusable_filter_row(self, row: ReusableFilterRow) -> dict[str, Any]:
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

    def _serialize_reusable_join_row(self, row: ReusableJoinRow) -> dict[str, Any]:
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
        return value.isoformat()