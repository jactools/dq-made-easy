from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy import select

from app.infrastructure.orm.models import RuleRow
from app.infrastructure.orm.models import RuleReusableFilterRow
from app.infrastructure.orm.models import ReusableFilterRow
from app.infrastructure.orm.models import ReusableJoinRow
from app.infrastructure.orm.session import session_scope


class ReusablePartsMixin:

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
