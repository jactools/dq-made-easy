import pytest

from app.api.v1.endpoints.validation_runs import _paginate_runs


pytestmark = pytest.mark.usefixtures("monkeypatch")


def test_paginate_runs_clamps_negative_page_and_limit() -> None:
    rows = [{"id": str(i)} for i in range(5)]

    payload = _paginate_runs(rows, page=-3, limit=0)

    assert payload["data"] == [{"id": "0"}]
    assert payload["pagination"] == {
        "total": 5,
        "page": 1,
        "limit": 1,
        "total_pages": 5,
        "has_next": True,
        "has_previous": False,
    }


def test_paginate_runs_caps_limit_and_reports_previous_page() -> None:
    rows = [{"id": str(i)} for i in range(5)]

    payload = _paginate_runs(rows, page=2, limit=999)

    assert payload["data"] == []
    assert payload["pagination"] == {
        "total": 5,
        "page": 2,
        "limit": 100,
        "total_pages": 1,
        "has_next": False,
        "has_previous": True,
    }


def test_paginate_runs_handles_empty_rows() -> None:
    payload = _paginate_runs([], page=3, limit=20)

    assert payload["data"] == []
    assert payload["pagination"] == {
        "total": 0,
        "page": 3,
        "limit": 20,
        "total_pages": 0,
        "has_next": False,
        "has_previous": True,
    }