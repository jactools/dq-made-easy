from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.domain.entities.incident import IncidentEntity
from app.domain.entities.incident import IncidentRootCauseSuggestionEntity
from app.domain.interfaces.v1.incident_repository import IncidentRepository
from app.infrastructure.orm.models import IncidentRow
from app.infrastructure.orm.models import IncidentRootCauseSuggestionRow
from app.infrastructure.orm.session import session_scope


def _row_to_entity(row: IncidentRow) -> IncidentEntity:
    return IncidentEntity(
        id=str(row.id or ""),
        incident_kind=str(row.incident_kind or ""),
        status=str(row.status or "open"),
        title=str(row.title or ""),
        description=str(row.description) if row.description else None,
        severity=str(row.severity) if row.severity else None,
        run_id=str(row.run_id) if row.run_id else None,
        run_plan_id=str(row.run_plan_id) if row.run_plan_id else None,
        workspace_id=str(row.workspace_id) if row.workspace_id else None,
        scope_kind=str(row.scope_kind) if row.scope_kind else None,
        scope_id=str(row.scope_id) if row.scope_id else None,
        source_correlation_id=str(row.source_correlation_id) if row.source_correlation_id else None,
        source_parent_correlation_id=str(row.source_parent_correlation_id) if row.source_parent_correlation_id else None,
        source_request_id=str(row.source_request_id) if row.source_request_id else None,
        source_queue_message_id=str(row.source_queue_message_id) if row.source_queue_message_id else None,
        source_trace_id=str(row.source_trace_id) if row.source_trace_id else None,
        source_system=str(row.source_system) if row.source_system else None,
        failure_code=str(row.failure_code) if row.failure_code else None,
        failure_message=str(row.failure_message) if row.failure_message else None,
        violated_rule_ids=list(row.violated_rule_ids) if row.violated_rule_ids is not None else None,
        violation_count=int(row.violation_count) if row.violation_count is not None else None,
        itsm_ticket_id=str(row.itsm_ticket_id) if row.itsm_ticket_id else None,
        itsm_ticket_number=str(row.itsm_ticket_number) if row.itsm_ticket_number else None,
        assigned_to=str(row.assigned_to) if row.assigned_to else None,
        resolved_at=row.resolved_at.isoformat() if row.resolved_at else None,
        comments=list(row.comments) if row.comments is not None else [],
        resolution_history=list(row.resolution_history) if row.resolution_history is not None else [],
        created_by=str(row.created_by) if row.created_by else None,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_by=str(row.updated_by) if row.updated_by else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )

def _root_cause_suggestion_row_to_entity(row: IncidentRootCauseSuggestionRow) -> IncidentRootCauseSuggestionEntity:
    return IncidentRootCauseSuggestionEntity(
        id=str(row.id or ""),
        workspace_id=str(row.workspace_id) if row.workspace_id else None,
        incident_ids=[str(incident_id).strip() for incident_id in list(row.incident_ids or []) if str(incident_id).strip()],
        incident_count=int(row.incident_count or 0),
        suggested_root_cause=dict(row.suggested_root_cause or {}),
        status=str(row.status or "pending"),
        events=list(row.events_json or []) if row.events_json is not None else [],
        created_by=str(row.created_by) if row.created_by else None,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_by=str(row.updated_by) if row.updated_by else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        accepted_at=row.accepted_at.isoformat() if row.accepted_at else None,
        rejected_at=row.rejected_at.isoformat() if row.rejected_at else None,
        assistance_requested_at=row.assistance_requested_at.isoformat() if row.assistance_requested_at else None,
        assistance_request_reference_id=str(row.assistance_request_reference_id) if row.assistance_request_reference_id else None,
        assistance_request_ticket_id=str(row.assistance_request_ticket_id) if row.assistance_request_ticket_id else None,
        assistance_request_ticket_number=str(row.assistance_request_ticket_number) if row.assistance_request_ticket_number else None,
        assistance_request_ticket_url=str(row.assistance_request_ticket_url) if row.assistance_request_ticket_url else None,
        assistance_request_ticket_system=str(row.assistance_request_ticket_system) if row.assistance_request_ticket_system else None,
        assistance_request_delivery_modes=[str(mode).strip() for mode in list(row.assistance_request_delivery_modes or []) if str(mode).strip()],
        assistance_request_payload=dict(row.assistance_request_payload_json or {}) if row.assistance_request_payload_json is not None else None,
    )


class PostgresIncidentRepository(IncidentRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def create_incident(self, entity: IncidentEntity) -> IncidentEntity:
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        incident_id = entity.id or str(uuid4())
        with session_scope(self.database_url) as session:
            row = IncidentRow(
                id=incident_id,
                incident_kind=entity.incident_kind,
                status=entity.status or "open",
                title=entity.title,
                description=entity.description,
                severity=entity.severity,
                run_id=entity.run_id,
                run_plan_id=entity.run_plan_id,
                workspace_id=entity.workspace_id,
                scope_kind=entity.scope_kind,
                scope_id=entity.scope_id,
                source_correlation_id=entity.source_correlation_id,
                source_parent_correlation_id=entity.source_parent_correlation_id,
                source_request_id=entity.source_request_id,
                source_queue_message_id=entity.source_queue_message_id,
                source_trace_id=entity.source_trace_id,
                source_system=entity.source_system,
                failure_code=entity.failure_code,
                failure_message=entity.failure_message,
                violated_rule_ids=entity.violated_rule_ids,
                violation_count=entity.violation_count,
                itsm_ticket_id=entity.itsm_ticket_id,
                itsm_ticket_number=entity.itsm_ticket_number,
                assigned_to=entity.assigned_to,
                resolved_at=None,
                comments=entity.comments,
                resolution_history=entity.resolution_history,
                created_by=entity.created_by,
                created_at=now,
                updated_by=entity.updated_by,
                updated_at=now,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _row_to_entity(row)

    def get_incident(self, incident_id: str) -> IncidentEntity | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(IncidentRow).where(IncidentRow.id == incident_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return _row_to_entity(row)

    def update_incident(self, entity: IncidentEntity) -> IncidentEntity:
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(IncidentRow).where(IncidentRow.id == entity.id)
            ).scalar_one_or_none()
            if row is None:
                raise ValueError(f"Incident {entity.id!r} not found")
            row.status = entity.status
            row.title = entity.title
            row.description = entity.description
            row.severity = entity.severity
            row.assigned_to = entity.assigned_to
            row.itsm_ticket_id = entity.itsm_ticket_id
            row.itsm_ticket_number = entity.itsm_ticket_number
            row.resolved_at = (
                datetime.fromisoformat(entity.resolved_at).replace(tzinfo=None)
                if entity.resolved_at
                else None
            )
            row.comments = entity.comments
            row.resolution_history = entity.resolution_history
            row.updated_by = entity.updated_by
            row.updated_at = now
            session.commit()
            session.refresh(row)
            return _row_to_entity(row)

    def list_incidents(
        self,
        *,
        workspace_id: str | None = None,
        incident_kind: str | None = None,
        status: str | None = None,
        run_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IncidentEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(IncidentRow).order_by(IncidentRow.created_at.desc().nullslast())
            if workspace_id:
                stmt = stmt.where(IncidentRow.workspace_id == workspace_id)
            if incident_kind:
                stmt = stmt.where(IncidentRow.incident_kind == incident_kind)
            if status:
                stmt = stmt.where(IncidentRow.status == status)
            if run_id:
                stmt = stmt.where(IncidentRow.run_id == run_id)
            stmt = stmt.offset(offset).limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [_row_to_entity(row) for row in rows]

    def create_root_cause_suggestion(self, entity: IncidentRootCauseSuggestionEntity) -> IncidentRootCauseSuggestionEntity:
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        suggestion_id = entity.id or str(uuid4())
        with session_scope(self.database_url) as session:
            row = IncidentRootCauseSuggestionRow(
                id=suggestion_id,
                workspace_id=entity.workspace_id,
                incident_ids=list(entity.incident_ids),
                incident_count=entity.incident_count,
                suggested_root_cause=dict(entity.suggested_root_cause),
                status=entity.status or "pending",
                events_json=list(entity.events),
                created_by=entity.created_by,
                created_at=now,
                updated_by=entity.updated_by,
                updated_at=now,
                accepted_at=datetime.fromisoformat(entity.accepted_at).replace(tzinfo=None) if entity.accepted_at else None,
                rejected_at=datetime.fromisoformat(entity.rejected_at).replace(tzinfo=None) if entity.rejected_at else None,
                assistance_requested_at=datetime.fromisoformat(entity.assistance_requested_at).replace(tzinfo=None) if entity.assistance_requested_at else None,
                assistance_request_reference_id=entity.assistance_request_reference_id,
                assistance_request_ticket_id=entity.assistance_request_ticket_id,
                assistance_request_ticket_number=entity.assistance_request_ticket_number,
                assistance_request_ticket_url=entity.assistance_request_ticket_url,
                assistance_request_ticket_system=entity.assistance_request_ticket_system,
                assistance_request_delivery_modes=list(entity.assistance_request_delivery_modes),
                assistance_request_payload_json=dict(entity.assistance_request_payload) if entity.assistance_request_payload is not None else None,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return _root_cause_suggestion_row_to_entity(row)

    def get_root_cause_suggestion(self, suggestion_id: str) -> IncidentRootCauseSuggestionEntity | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(IncidentRootCauseSuggestionRow).where(IncidentRootCauseSuggestionRow.id == suggestion_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return _root_cause_suggestion_row_to_entity(row)

    def update_root_cause_suggestion(self, entity: IncidentRootCauseSuggestionEntity) -> IncidentRootCauseSuggestionEntity:
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(IncidentRootCauseSuggestionRow).where(IncidentRootCauseSuggestionRow.id == entity.id)
            ).scalar_one_or_none()
            if row is None:
                raise ValueError(f"Incident root cause suggestion {entity.id!r} not found")
            row.workspace_id = entity.workspace_id
            row.incident_ids = list(entity.incident_ids)
            row.incident_count = entity.incident_count
            row.suggested_root_cause = dict(entity.suggested_root_cause)
            row.status = entity.status
            row.events_json = list(entity.events)
            row.created_by = entity.created_by
            row.updated_by = entity.updated_by
            row.accepted_at = datetime.fromisoformat(entity.accepted_at).replace(tzinfo=None) if entity.accepted_at else None
            row.rejected_at = datetime.fromisoformat(entity.rejected_at).replace(tzinfo=None) if entity.rejected_at else None
            row.assistance_requested_at = datetime.fromisoformat(entity.assistance_requested_at).replace(tzinfo=None) if entity.assistance_requested_at else None
            row.assistance_request_reference_id = entity.assistance_request_reference_id
            row.assistance_request_ticket_id = entity.assistance_request_ticket_id
            row.assistance_request_ticket_number = entity.assistance_request_ticket_number
            row.assistance_request_ticket_url = entity.assistance_request_ticket_url
            row.assistance_request_ticket_system = entity.assistance_request_ticket_system
            row.assistance_request_delivery_modes = list(entity.assistance_request_delivery_modes)
            row.assistance_request_payload_json = dict(entity.assistance_request_payload) if entity.assistance_request_payload is not None else None
            row.updated_at = now
            session.add(row)
            session.commit()
            session.refresh(row)
            return _root_cause_suggestion_row_to_entity(row)

    def list_root_cause_suggestions(
        self,
        *,
        workspace_id: str | None = None,
        incident_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IncidentRootCauseSuggestionEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(IncidentRootCauseSuggestionRow).order_by(IncidentRootCauseSuggestionRow.created_at.desc().nullslast())
            if workspace_id:
                stmt = stmt.where(IncidentRootCauseSuggestionRow.workspace_id == workspace_id)
            if status:
                stmt = stmt.where(IncidentRootCauseSuggestionRow.status == status)
            rows = session.execute(stmt).scalars().all()

        entities = [_root_cause_suggestion_row_to_entity(row) for row in rows]
        if incident_id:
            entities = [entity for entity in entities if incident_id in entity.incident_ids]
        return entities[offset : offset + limit]
