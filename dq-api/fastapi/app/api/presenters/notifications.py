from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from dq_domain_validation import NotificationType

from app.domain.entities.approvals import build_approval_audit_entity
from app.domain.entities.base import EntityModel


class NotificationEntity(EntityModel):
    id: str
    notificationType: NotificationType
    recipientId: str
    message: str
    createdAt: str
    details: dict[str, Any]


def build_notification_entities(
    audit_rows: Iterable[Any],
    recipient_id: str,
    *,
    action: str = "notification.gx_suite_empty",
    notification_type: NotificationType = "gx_suite_empty",
) -> list[NotificationEntity]:
    normalized_recipient_id = str(recipient_id or "").strip()
    notifications: list[NotificationEntity] = []
    for row in audit_rows:
        audit = build_approval_audit_entity(row)
        if audit.action != action:
            continue
        if str(audit.actorId or "").strip() != normalized_recipient_id:
            continue
        message = str(audit.details.get("message") or "").strip()
        notifications.append(
            NotificationEntity(
                id=audit.id,
                notificationType=notification_type,
                recipientId=normalized_recipient_id,
                message=message,
                createdAt=audit.timestamp,
                details=dict(audit.details),
            )
        )
    return sorted(notifications, key=lambda item: str(item.createdAt or ""), reverse=True)