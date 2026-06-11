from __future__ import annotations

from datetime import datetime

from app.domain.entities.base import EntityModel


class SessionEntity(EntityModel):
    id: str
    user_id: str
    last_activity: datetime
    access_token: str | None = None
    id_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: datetime | None = None
