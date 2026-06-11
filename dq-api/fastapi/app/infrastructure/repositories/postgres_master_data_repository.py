from __future__ import annotations

from sqlalchemy import select

from app.domain.entities.master_data import MasterRecordEntity
from app.domain.interfaces.v1.master_data_repository import MasterDataRepository
from app.infrastructure.orm.models import MasterRecordRow
from app.infrastructure.orm.session import session_scope


class PostgresMasterDataRepository(MasterDataRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def list_master_records(
        self,
        domain: str | None = None,
        workspace_id: str | None = None,
    ) -> list[MasterRecordEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(MasterRecordRow)
            if domain is not None:
                stmt = stmt.where(MasterRecordRow.domain == domain)
            if workspace_id is not None:
                stmt = stmt.where(MasterRecordRow.workspace_id == workspace_id)
            stmt = stmt.order_by(MasterRecordRow.display_name, MasterRecordRow.id)
            rows = session.execute(stmt).scalars().all()
            return [
                MasterRecordEntity(
                    id=str(row.id or ""),
                    domain=str(row.domain or ""),
                    display_name=str(row.display_name or ""),
                    business_key=str(row.business_key or ""),
                    golden_record_id=str(row.golden_record_id or ""),
                    match_rule=str(row.match_rule or ""),
                    survivorship_rule=str(row.survivorship_rule or ""),
                    resolution_status=str(row.resolution_status or "golden"),
                    source_count=int(row.source_count or 0),
                    source_systems=list(row.source_systems or []),
                    merged_from_ids=list(row.merged_from_ids or []),
                    owner=str(row.owner or ""),
                    workspace_id=str(row.workspace_id or ""),
                    created_at=self._to_text(row.created_at),
                    updated_at=self._to_text(row.updated_at),
                )
                for row in rows
            ]

    @staticmethod
    def _to_text(value) -> str:
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)