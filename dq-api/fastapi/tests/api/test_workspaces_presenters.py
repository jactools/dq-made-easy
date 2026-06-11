from __future__ import annotations

from types import SimpleNamespace

from app.api.presenters.workspaces import build_workspaces_page_payload


def test_build_workspaces_page_payload_serializes_and_paginates() -> None:
    rows = [
        SimpleNamespace(id="w1", name="Workspace 1", description="One"),
        {"id": "w2", "name": "Workspace 2", "description": "Two"},
        SimpleNamespace(
            id="w3",
            name="Workspace 3",
            description="Three",
            model_dump=lambda: {"id": "w3", "name": "Workspace 3", "description": "Three"},
        ),
    ]

    payload = build_workspaces_page_payload(rows, page=1, limit=2)

    assert payload["data"] == [
        {"id": "w1", "name": "Workspace 1", "description": "One"},
        {"id": "w2", "name": "Workspace 2", "description": "Two"},
    ]
    assert payload["pagination"] == {
        "total": 3,
        "page": 1,
        "limit": 2,
        "total_pages": 2,
        "has_next": True,
        "has_previous": False,
    }
