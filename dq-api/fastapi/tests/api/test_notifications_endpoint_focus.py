from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import notifications as notifications_endpoints


class _ApprovalsRepo:
    def __init__(self, audit_rows: list[dict]):
        self._audit_rows = list(audit_rows)

    def list_approval_audit(self):
        return [SimpleNamespace(**row) for row in list(self._audit_rows)]


@pytest.mark.anyio
async def test_list_notifications_supports_contract_change_notifications():
    repo = _ApprovalsRepo(
        [
            {
                "id": "n3",
                "approvalId": "contract-review:asset-1:asset-1-contract-v1",
                "action": "notification.contract_change",
                "actorId": "user-1",
                "timestamp": "2026-04-08T00:00:00Z",
                "details": {
                    "message": "Contract approved for Data Asset 'asset-1'",
                    "review_status": "approved",
                },
            }
        ]
    )

    request = SimpleNamespace(state=SimpleNamespace(user_id="user-1"))

    rows = await notifications_endpoints.list_notifications(
        request=request,
        limit=50,
        offset=0,
        action=None,
        notification_type="contract_change",
        repository=repo,
    )

    assert len(rows) == 1
    assert rows[0].notificationType == "contract_change"
    assert rows[0].message == "Contract approved for Data Asset 'asset-1'"


@pytest.mark.anyio
async def test_list_notifications_filters_by_actor_and_action():
    repo = _ApprovalsRepo(
        [
            {
                "id": "n1",
                "approvalId": "a1",
                "action": "notification.gx_suite_empty",
                "actorId": "user-1",
                "timestamp": "2026-04-08T00:00:00Z",
                "details": {"message": "m1"},
            },
            {
                "id": "n2",
                "approvalId": "a1",
                "action": "notification.gx_suite_empty",
                "actorId": "user-2",
                "timestamp": "2026-04-08T00:00:01Z",
                "details": {"message": "m2"},
            },
            {
                "id": "x1",
                "approvalId": "a1",
                "action": "gx_suite.empty.registered",
                "actorId": "user-reviewer",
                "timestamp": "2026-04-08T00:00:02Z",
                "details": {},
            },
        ]
    )

    request = SimpleNamespace(state=SimpleNamespace(user_id="user-1"))

    rows = await notifications_endpoints.list_notifications(
        request=request,
        limit=50,
        offset=0,
        repository=repo,
    )

    assert len(rows) == 1
    assert rows[0].recipientId == "user-1"
    assert rows[0].notificationType == "gx_suite_empty"
    assert rows[0].message == "m1"
