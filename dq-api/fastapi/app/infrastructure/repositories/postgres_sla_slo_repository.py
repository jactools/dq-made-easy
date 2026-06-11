from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.domain.entities.sla_slo import SlaSloDefinitionEntity
from app.domain.entities.sla_slo import build_sla_slo_definition_entity
from app.domain.interfaces.v1.sla_slo_repository import SlaSloRepository
from app.infrastructure.orm.models import SlaSloDefinitionRow
from app.infrastructure.orm.session import session_scope


class PostgresSlaSloRepository(SlaSloRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def list_sla_slo_definitions(
        self,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        scope_kind: str | None = None,
        metric_kind: str | None = None,
    ) -> list[SlaSloDefinitionEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(SlaSloDefinitionRow)
            if workspace_id is not None:
                stmt = stmt.where(SlaSloDefinitionRow.workspace_id == workspace_id)
            if status is not None:
                normalized = str(status).strip().lower()
                stmt = stmt.where(
                    (SlaSloDefinitionRow.lifecycle_status == normalized)
                    | (SlaSloDefinitionRow.approval_status == normalized)
                )
            if scope_kind is not None:
                stmt = stmt.where(SlaSloDefinitionRow.scope_kind == scope_kind)
            if metric_kind is not None:
                stmt = stmt.where(SlaSloDefinitionRow.metric_kind == metric_kind)
            stmt = stmt.order_by(SlaSloDefinitionRow.updated_at.desc().nullslast(), SlaSloDefinitionRow.created_at.desc().nullslast(), SlaSloDefinitionRow.id.desc())
            rows = session.execute(stmt).scalars().all()
        return [definition for definition in (self._row_to_entity(row) for row in rows) if definition is not None]

    async def get_sla_slo_definition(self, definition_id: str) -> SlaSloDefinitionEntity | None:
        with session_scope(self.database_url) as session:
            row = session.get(SlaSloDefinitionRow, definition_id)
        if row is None:
            return None
        return self._row_to_entity(row)

    async def create_sla_slo_definition(self, payload: dict[str, Any], actor_id: str | None = None) -> SlaSloDefinitionEntity:
        definition_id = str(uuid4())
        created_at = datetime.now(UTC)
        row = SlaSloDefinitionRow(
            id=definition_id,
            workspace_id=str(payload.get("workspace_id") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            description=str(payload.get("description") or "").strip() or None,
            scope_kind=str(payload.get("scope_kind") or "").strip(),
            scope_id=str(payload.get("scope_id") or "").strip(),
            metric_kind=str(payload.get("metric_kind") or "").strip(),
            threshold_value=payload.get("threshold_value"),
            threshold_operator=str(payload.get("threshold_operator") or "gte").strip().lower() or "gte",
            lookback_amount=int(payload.get("lookback_amount") or 30),
            lookback_unit=str(payload.get("lookback_unit") or "day").strip().lower() or "day",
            lifecycle_status="draft",
            approval_status="draft",
            requested_by=str(actor_id or payload.get("requested_by") or "").strip() or None,
            requested_at=created_at,
            reviewed_by=None,
            reviewed_at=None,
            itsm_system=None,
            itsm_ticket_id=None,
            itsm_ticket_number=None,
            itsm_ticket_url=None,
            created_at=created_at,
            updated_at=created_at,
        )
        with session_scope(self.database_url) as session:
            session.add(row)
            session.commit()
        return self._row_to_entity(row) or build_sla_slo_definition_entity(row) or SlaSloDefinitionEntity.model_validate(row)

    async def update_sla_slo_definition(
        self,
        definition_id: str,
        payload: dict[str, Any],
        actor_id: str | None = None,
    ) -> SlaSloDefinitionEntity | None:
        with session_scope(self.database_url) as session:
            row = session.get(SlaSloDefinitionRow, definition_id)
            if row is None:
                return None
            for key in ("workspace_id", "name", "description", "scope_kind", "scope_id", "metric_kind", "threshold_value", "threshold_operator", "lookback_amount", "lookback_unit"):
                if key in payload and payload[key] is not None:
                    setattr(row, key, payload[key])
            row.description = str(row.description or "").strip() or None
            row.threshold_operator = str(row.threshold_operator or "gte").strip().lower() or "gte"
            row.lookback_amount = int(row.lookback_amount or 30)
            row.lookback_unit = str(row.lookback_unit or "day").strip().lower() or "day"
            if actor_id:
                row.requested_by = str(actor_id).strip() or row.requested_by
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
        return self._row_to_entity(row)

    async def approve_sla_slo_definition(
        self,
        definition_id: str,
        payload: dict[str, Any],
        actor_id: str | None = None,
    ) -> SlaSloDefinitionEntity | None:
        with session_scope(self.database_url) as session:
            row = session.get(SlaSloDefinitionRow, definition_id)
            if row is None:
                return None
            row.lifecycle_status = str(payload.get("lifecycle_status") or "active").strip().lower() or "active"
            row.approval_status = str(payload.get("approval_status") or "approved").strip().lower() or "approved"
            row.reviewed_by = str(payload.get("reviewed_by") or actor_id or "").strip() or None
            reviewed_at = payload.get("reviewed_at")
            row.reviewed_at = self._parse_datetime(reviewed_at) or datetime.now(UTC)
            row.itsm_system = str(payload.get("itsm_system") or "").strip() or None
            row.itsm_ticket_id = str(payload.get("itsm_ticket_id") or "").strip() or None
            row.itsm_ticket_number = str(payload.get("itsm_ticket_number") or "").strip() or None
            row.itsm_ticket_url = str(payload.get("itsm_ticket_url") or "").strip() or None
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
        return self._row_to_entity(row)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _row_to_entity(row: SlaSloDefinitionRow) -> SlaSloDefinitionEntity | None:
        payload = {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "name": row.name,
            "description": row.description,
            "scope_kind": row.scope_kind,
            "scope_id": row.scope_id,
            "metric_kind": row.metric_kind,
            "threshold_value": row.threshold_value,
            "threshold_operator": row.threshold_operator,
            "lookback_amount": row.lookback_amount,
            "lookback_unit": row.lookback_unit,
            "lifecycle_status": row.lifecycle_status,
            "approval_status": row.approval_status,
            "requested_by": row.requested_by,
            "requested_at": row.requested_at.isoformat() if row.requested_at else None,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "itsm_system": row.itsm_system,
            "itsm_ticket_id": row.itsm_ticket_id,
            "itsm_ticket_number": row.itsm_ticket_number,
            "itsm_ticket_url": row.itsm_ticket_url,
        }
        return build_sla_slo_definition_entity(payload)
