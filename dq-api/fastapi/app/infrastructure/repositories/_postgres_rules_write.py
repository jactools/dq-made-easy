from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.domain.entities import build_rule_record_entity, RuleRecordEntity
from app.domain.entities import rule_policy
from app.infrastructure.orm.models import RuleRow
from app.infrastructure.orm.models import RuleCurrentVersionRow
from app.infrastructure.orm.models import RuleReusableFilterRow
from app.infrastructure.orm.models import RuleVersionRow
from app.infrastructure.orm.session import session_scope


class RulesWriteMixin:

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
