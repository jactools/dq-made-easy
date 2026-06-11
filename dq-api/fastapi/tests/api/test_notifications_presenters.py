from __future__ import annotations

from types import SimpleNamespace

from app.api.presenters.notifications import build_notification_entities


def test_build_notification_entities_filters_and_sorts() -> None:
    notifications = build_notification_entities(
        [
            SimpleNamespace(
                id="n1",
                approvalId="a1",
                action="notification.gx_suite_empty",
                actorId="user-1",
                timestamp="2026-04-08T00:00:00Z",
                details={"message": "older"},
            ),
            {
                "id": "n2",
                "approvalId": "a1",
                "action": "notification.gx_suite_empty",
                "actorId": "user-1",
                "timestamp": "2026-04-08T00:00:01Z",
                "details": {"message": "newer"},
            },
            SimpleNamespace(
                id="x1",
                approvalId="a1",
                action="gx_suite.empty.registered",
                actorId="user-1",
                timestamp="2026-04-08T00:00:02Z",
                details={},
            ),
        ],
        "user-1",
    )

    assert [item.id for item in notifications] == ["n2", "n1"]
    assert notifications[0].message == "newer"
    assert notifications[0].notificationType == "gx_suite_empty"
