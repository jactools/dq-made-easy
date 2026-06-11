from __future__ import annotations

from datetime import datetime, timezone

from app.domain.entities import SessionEntity
from app.domain.interfaces.v1.session_repository import SessionRepository


class InMemorySessionsRepository(SessionRepository):
    def __init__(self) -> None:
        self._store: dict[str, SessionEntity] = {}

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
        self._store[session_id] = SessionEntity(
            id=session_id,
            user_id=user_id,
            last_activity=datetime.now(timezone.utc).replace(tzinfo=None),
            access_token=access_token,
            id_token=id_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
        )

    def touch_session(self, session_id: str) -> None:
        entry = self._store.get(session_id)
        if entry:
            entry.last_activity = datetime.now(timezone.utc).replace(tzinfo=None)

    def get_session(self, session_id: str) -> SessionEntity | None:
        return self._store.get(session_id)

    def delete_session(self, session_id: str) -> None:
        self._store.pop(session_id, None)
