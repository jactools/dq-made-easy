from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.domain.entities.sla_slo import SlaSloDefinitionEntity
from app.domain.entities.sla_slo import build_sla_slo_definition_entity
from app.domain.interfaces.v1.sla_slo_repository import SlaSloRepository


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class InMemorySlaSloRepository(SlaSloRepository):
    def __init__(self) -> None:
        self._definitions: dict[str, dict[str, Any]] = {}

    async def list_sla_slo_definitions(
        self,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        scope_kind: str | None = None,
        metric_kind: str | None = None,
    ) -> list[SlaSloDefinitionEntity]:
        rows = list(self._definitions.values())
        if workspace_id is not None:
            target = str(workspace_id).strip().lower()
            rows = [row for row in rows if str(row.get("workspace_id") or "").strip().lower() == target]
        if status is not None:
            target = str(status).strip().lower()
            rows = [row for row in rows if str(row.get("lifecycle_status") or "").strip().lower() == target or str(row.get("approval_status") or "").strip().lower() == target]
        if scope_kind is not None:
            target = str(scope_kind).strip().lower()
            rows = [row for row in rows if str(row.get("scope_kind") or "").strip().lower() == target]
        if metric_kind is not None:
            target = str(metric_kind).strip().lower()
            rows = [row for row in rows if str(row.get("metric_kind") or "").strip().lower() == target]
        rows.sort(key=lambda row: (str(row.get("updated_at") or row.get("created_at") or ""), str(row.get("id") or "")), reverse=True)
        return [definition for definition in (build_sla_slo_definition_entity(row) for row in rows) if definition is not None]

    async def get_sla_slo_definition(self, definition_id: str) -> SlaSloDefinitionEntity | None:
        payload = self._definitions.get(str(definition_id))
        if payload is None:
            return None
        return build_sla_slo_definition_entity(payload)

    async def create_sla_slo_definition(self, payload: dict[str, Any], actor_id: str | None = None) -> SlaSloDefinitionEntity:
        definition_id = str(uuid4())
        created_at = _now_iso()
        record = {
            "id": definition_id,
            "workspace_id": str(payload.get("workspace_id") or "").strip(),
            "name": str(payload.get("name") or "").strip(),
            "description": str(payload.get("description") or "").strip() or None,
            "scope_kind": str(payload.get("scope_kind") or "").strip(),
            "scope_id": str(payload.get("scope_id") or "").strip(),
            "metric_kind": str(payload.get("metric_kind") or "").strip(),
            "threshold_value": payload.get("threshold_value"),
            "threshold_operator": str(payload.get("threshold_operator") or "gte").strip().lower() or "gte",
            "lookback_amount": int(payload.get("lookback_amount") or 30),
            "lookback_unit": str(payload.get("lookback_unit") or "day").strip().lower() or "day",
            "lifecycle_status": "draft",
            "approval_status": "draft",
            "requested_by": str(actor_id or payload.get("requested_by") or "").strip() or None,
            "requested_at": created_at,
            "reviewed_by": None,
            "reviewed_at": None,
            "itsm_system": None,
            "itsm_ticket_id": None,
            "itsm_ticket_number": None,
            "itsm_ticket_url": None,
            "created_at": created_at,
            "updated_at": created_at,
        }
        self._definitions[definition_id] = deepcopy(record)
        entity = build_sla_slo_definition_entity(record)
        if entity is None:
            raise ValueError("SLA/SLO definition payload is invalid")
        return entity

    async def update_sla_slo_definition(
        self,
        definition_id: str,
        payload: dict[str, Any],
        actor_id: str | None = None,
    ) -> SlaSloDefinitionEntity | None:
        existing = self._definitions.get(str(definition_id))
        if existing is None:
            return None

        updated = deepcopy(existing)
        for key in ("workspace_id", "name", "description", "scope_kind", "scope_id", "metric_kind", "threshold_value", "threshold_operator", "lookback_amount", "lookback_unit"):
            if key in payload and payload[key] is not None:
                updated[key] = payload[key]
        updated["description"] = str(updated.get("description") or "").strip() or None
        updated["threshold_operator"] = str(updated.get("threshold_operator") or "gte").strip().lower() or "gte"
        updated["lookback_amount"] = int(updated.get("lookback_amount") or 30)
        updated["lookback_unit"] = str(updated.get("lookback_unit") or "day").strip().lower() or "day"
        updated["updated_at"] = _now_iso()
        if actor_id:
            updated["requested_by"] = str(actor_id).strip() or updated.get("requested_by")
        self._definitions[str(definition_id)] = deepcopy(updated)
        return build_sla_slo_definition_entity(updated)

    async def approve_sla_slo_definition(
        self,
        definition_id: str,
        payload: dict[str, Any],
        actor_id: str | None = None,
    ) -> SlaSloDefinitionEntity | None:
        existing = self._definitions.get(str(definition_id))
        if existing is None:
            return None

        updated = deepcopy(existing)
        updated["lifecycle_status"] = str(payload.get("lifecycle_status") or "active").strip().lower() or "active"
        updated["approval_status"] = str(payload.get("approval_status") or "approved").strip().lower() or "approved"
        updated["reviewed_by"] = str(payload.get("reviewed_by") or actor_id or "").strip() or None
        updated["reviewed_at"] = str(payload.get("reviewed_at") or _now_iso()).strip() or _now_iso()
        updated["itsm_system"] = str(payload.get("itsm_system") or "").strip() or None
        updated["itsm_ticket_id"] = str(payload.get("itsm_ticket_id") or "").strip() or None
        updated["itsm_ticket_number"] = str(payload.get("itsm_ticket_number") or "").strip() or None
        updated["itsm_ticket_url"] = str(payload.get("itsm_ticket_url") or "").strip() or None
        updated["updated_at"] = _now_iso()
        self._definitions[str(definition_id)] = deepcopy(updated)
        return build_sla_slo_definition_entity(updated)
