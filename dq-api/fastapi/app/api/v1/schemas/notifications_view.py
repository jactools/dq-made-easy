from __future__ import annotations

from typing import Any

from pydantic import ConfigDict

from dq_domain_validation import NotificationType
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class NotificationView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    notificationType: NotificationType
    recipientId: str
    message: str
    createdAt: str
    details: dict[str, Any]
