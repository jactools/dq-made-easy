from __future__ import annotations

from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy import select

from app.domain.entities import build_rule_record_entity, RuleEntity, RuleRecordEntity
from app.infrastructure.orm.models import RuleRow
from app.infrastructure.orm.session import session_scope


class RulesReadMixin:

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
