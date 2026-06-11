from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select

from app.domain.entities import SessionEntity
from app.domain.interfaces.v1.session_repository import SessionRepository
from app.infrastructure.orm.models import AppSessionRow
from app.infrastructure.orm.session import session_scope


class PostgresSessionRepository(SessionRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def create_session(
        self,
        session_id: str,
        user_id: str,
        *,
        access_token: str | None = None,
        id_token: str | None = None,
        refresh_token: str | None = None,
        token_expires_at: datetime | None = None,
    ) -> None:
        with session_scope(self.database_url) as session:
            row = AppSessionRow(
                id=session_id,
                user_id=user_id,
                last_activity=datetime.now(timezone.utc).replace(tzinfo=None),
                access_token=access_token,
                id_token=id_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at,
            )
            session.merge(row)
            session.commit()

    def touch_session(self, session_id: str) -> None:
        with session_scope(self.database_url) as session:
            stmt = select(AppSessionRow).where(AppSessionRow.id == session_id)
            row = session.execute(stmt).scalars().first()
            if row:
                row.last_activity = datetime.now(timezone.utc).replace(tzinfo=None)
                session.commit()

    def get_session(self, session_id: str) -> SessionEntity | None:
        with session_scope(self.database_url) as session:
            stmt = select(AppSessionRow).where(AppSessionRow.id == session_id)
            row = session.execute(stmt).scalars().first()
            if not row:
                return None
            return SessionEntity(
                id=str(row.id),
                user_id=str(row.user_id),
                last_activity=row.last_activity,
                access_token=row.access_token,
                id_token=row.id_token,
                refresh_token=row.refresh_token,
                token_expires_at=row.token_expires_at,
            )

    def delete_session(self, session_id: str) -> None:
        with session_scope(self.database_url) as session:
            stmt = select(AppSessionRow).where(AppSessionRow.id == session_id)
            row = session.execute(stmt).scalars().first()
            if row:
                session.delete(row)
                session.commit()
