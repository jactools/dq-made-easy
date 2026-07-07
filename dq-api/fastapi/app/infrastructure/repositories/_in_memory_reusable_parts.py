from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities import RuleCreatorEntity, RuleTagEntity


class InMemoryReusablePartsMixin:

    async def get_user_by_id(self, user_id: str) -> RuleCreatorEntity | None:
        return self._users.get(user_id)

    async def get_tags_by_ids(self, tag_ids: list[str]) -> list[RuleTagEntity]:
        return [self._tags[tag_id] for tag_id in tag_ids if tag_id in self._tags]

    async def list_reusable_filters(self, workspace: str | None = None, query: str | None = None) -> list[dict]:
        rows = [row.copy() for row in self._reusable_filters.values()]
        if workspace:
            rows = [row for row in rows if str(row.get("workspace") or "") == workspace]
        normalized_query = str(query or "").strip().lower()
        if normalized_query:
            rows = [
                row for row in rows
                if normalized_query in " ".join([
                    str(row.get("name") or ""),
                    str(row.get("description") or ""),
                    str(row.get("filter_expression") or row.get("expression") or ""),
                ]).lower()
            ]
        return sorted(rows, key=lambda row: str(row.get("name") or "").lower())

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
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        filter_id = f"rf_{uuid4().hex[:10]}"
        row = {
            "id": filter_id,
            "name": name,
            "description": description,
            "expression": expression,
            "filter_expression": expression,
            "workspace": workspace,
            "created_by": created_by,
            "active": bool(active),
            "created_at": now,
            "updated_at": now,
        }
        self._reusable_filters[filter_id] = row
        return row.copy()

    async def delete_reusable_filter(self, filter_id: str) -> bool:
        if filter_id not in self._reusable_filters:
            return False

        in_use = any(
            filter_id in (row.get("reusableFilterIds") or [])
            for row in await self._list_rule_payloads(include_deleted=False)
        )
        if in_use:
            raise ValueError("Cannot delete reusable filter that is assigned to one or more rules")

        del self._reusable_filters[filter_id]
        return True

    async def get_reusable_filter(self, filter_id: str) -> dict | None:
        row = self._reusable_filters.get(filter_id)
        if row is None:
            return None
        return row.copy()

    async def update_reusable_filter(
        self,
        *,
        filter_id: str,
        name: str,
        expression: str,
        description: str | None,
        active: bool,
    ) -> dict | None:
        row = self._reusable_filters.get(filter_id)
        if row is None:
            return None

        row["name"] = name
        row["description"] = description
        row["expression"] = expression
        row["filter_expression"] = expression
        row["active"] = bool(active)
        row["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return row.copy()

    async def list_reusable_joins(self, workspace: str | None = None) -> list[dict]:
        rows = [row.copy() for row in self._reusable_joins.values()]
        if workspace:
            rows = [row for row in rows if str(row.get("workspace") or "") == workspace]
        return sorted(rows, key=lambda row: str(row.get("name") or "").lower())

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
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        join_id = f"rj_{uuid4().hex[:10]}"
        row = {
            "id": join_id,
            "name": name,
            "description": description,
            "join_definition": join_definition,
            "workspace": workspace,
            "created_by": created_by,
            "active": bool(active),
            "created_at": now,
            "updated_at": now,
        }
        self._reusable_joins[join_id] = row
        return row.copy()

    async def delete_reusable_join(self, join_id: str) -> bool:
        if join_id not in self._reusable_joins:
            return False

        in_use = any(
            str(row.get("reusable_join_id") or "") == join_id
            for row in await self._list_rule_payloads(include_deleted=False)
        )
        if in_use:
            raise ValueError("Cannot delete reusable join that is assigned to one or more rules")

        del self._reusable_joins[join_id]
        return True

    async def get_reusable_join(self, join_id: str) -> dict | None:
        row = self._reusable_joins.get(join_id)
        if row is None:
            return None
        return row.copy()

    async def update_reusable_join(
        self,
        *,
        join_id: str,
        name: str,
        join_definition: str,
        description: str | None,
        active: bool,
    ) -> dict | None:
        row = self._reusable_joins.get(join_id)
        if row is None:
            return None

        row["name"] = name
        row["description"] = description
        row["join_definition"] = join_definition
        row["active"] = bool(active)
        row["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return row.copy()
