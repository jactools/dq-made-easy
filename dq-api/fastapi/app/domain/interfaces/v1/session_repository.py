from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.entities import SessionEntity


class SessionRepository(Protocol):
    def create_session(
        self,
        session_id: str,
        user_id: str,
        *,
        access_token: str | None = None,
        id_token: str | None = None,
        refresh_token: str | None = None,
        token_expires_at: datetime | None = None,
    ) -> None: ...

    def touch_session(self, session_id: str) -> None: ...

    def get_session(self, session_id: str) -> SessionEntity | None: ...

    def delete_session(self, session_id: str) -> None: ...
