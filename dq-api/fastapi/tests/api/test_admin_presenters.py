from __future__ import annotations

from types import SimpleNamespace

from app.api.presenters.admin import build_admin_users_page_payload
from app.api.presenters.admin import derive_admin_rule_status_from_row
from app.api.presenters.admin import filter_admin_users


def test_admin_presenters_filter_paginate_and_derive_status() -> None:
    users = [
        SimpleNamespace(id="2", name="Zoe", email="zoe@example.com", roles=["viewer"], workspaces=["w2"]),
        SimpleNamespace(id="1", name="Alice", email="alice@example.com", roles=["admin"], workspaces=["w1"]),
    ]

    filtered = filter_admin_users(users, q="alice", sort="name", order="asc")
    assert [user.id for user in filtered] == ["1"]

    page = build_admin_users_page_payload(users, page=1, limit=1)
    assert page == {
        "data": [
            {
                "id": "2",
                "name": "Zoe",
                "email": "zoe@example.com",
                "roles": ["viewer"],
                "workspaces": ["w2"],
            }
        ],
        "pagination": {
            "total": 2,
            "page": 1,
            "limit": 1,
            "total_pages": 2,
            "has_next": True,
            "has_previous": False,
        },
    }

    assert derive_admin_rule_status_from_row({"active": True}) == "activated"
    assert derive_admin_rule_status_from_row({"removed": True}) == "removed"
    assert derive_admin_rule_status_from_row({"last_approval_status": "PENDING_APPROVAL"}) == "pending-approval"
