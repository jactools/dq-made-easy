from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.domain.entities.ontology_graph import OntologyGraphSnapshotEntity
from app.domain.interfaces.v1.ontology_graph_repository import OntologyGraphRepository
from app.infrastructure.orm.models import OntologyGraphSnapshotRow
from app.infrastructure.orm.session import session_scope


def _snapshot_entity_from_row(row: OntologyGraphSnapshotRow) -> OntologyGraphSnapshotEntity:
    return OntologyGraphSnapshotEntity(
        id=str(row.id or ""),
        graph_id=str(row.graph_id or ""),
        graph_name=str(row.graph_name or ""),
        workspace_id=str(row.workspace_id or "").strip() or None,
        data_product_id=str(row.data_product_id or "").strip() or None,
        captured_at=row.captured_at.isoformat(),
        captured_by=str(row.captured_by or "").strip() or None,
        node_count=int(row.node_count or 0),
        edge_count=int(row.edge_count or 0),
        graph_json=dict(row.graph_json or {}),
        source_summary=dict(row.source_summary_json or {}),
    )


class PostgresOntologyGraphRepository(OntologyGraphRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def record_ontology_graph_snapshot(self, snapshot: OntologyGraphSnapshotEntity) -> OntologyGraphSnapshotEntity:
        with session_scope(self.database_url) as session:
            session.add(
                OntologyGraphSnapshotRow(
                    id=snapshot.id,
                    graph_id=snapshot.graph_id,
                    graph_name=snapshot.graph_name,
                    workspace_id=snapshot.workspace_id,
                    data_product_id=snapshot.data_product_id,
                    captured_at=_parse_iso_datetime(snapshot.captured_at),
                    captured_by=snapshot.captured_by,
                    node_count=int(snapshot.node_count or 0),
                    edge_count=int(snapshot.edge_count or 0),
                    graph_json=dict(snapshot.graph_json or {}),
                    source_summary_json=dict(snapshot.source_summary or {}),
                )
            )
            session.commit()
        return snapshot

    async def get_latest_ontology_graph_snapshot(
        self,
        *,
        graph_id: str,
        workspace_id: str | None = None,
        data_product_id: str | None = None,
    ) -> OntologyGraphSnapshotEntity | None:
        with session_scope(self.database_url) as session:
            stmt = select(OntologyGraphSnapshotRow).where(OntologyGraphSnapshotRow.graph_id == graph_id)
            if workspace_id is not None:
                stmt = stmt.where(OntologyGraphSnapshotRow.workspace_id == workspace_id)
            if data_product_id is not None:
                stmt = stmt.where(OntologyGraphSnapshotRow.data_product_id == data_product_id)
            row = session.execute(stmt.order_by(OntologyGraphSnapshotRow.captured_at.desc())).scalars().first()
            if row is None:
                return None
            return _snapshot_entity_from_row(row)

    async def list_ontology_graph_snapshots(
        self,
        *,
        graph_id: str | None = None,
        workspace_id: str | None = None,
        data_product_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[OntologyGraphSnapshotEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(OntologyGraphSnapshotRow)
            if graph_id is not None:
                stmt = stmt.where(OntologyGraphSnapshotRow.graph_id == graph_id)
            if workspace_id is not None:
                stmt = stmt.where(OntologyGraphSnapshotRow.workspace_id == workspace_id)
            if data_product_id is not None:
                stmt = stmt.where(OntologyGraphSnapshotRow.data_product_id == data_product_id)
            rows = session.execute(
                stmt.order_by(OntologyGraphSnapshotRow.captured_at.desc()).limit(limit).offset(offset)
            ).scalars().all()
            return [_snapshot_entity_from_row(row) for row in rows]


def _parse_iso_datetime(value: str | None):
    from datetime import UTC, datetime

    payload = str(value or "").strip()
    if not payload:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(payload.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
