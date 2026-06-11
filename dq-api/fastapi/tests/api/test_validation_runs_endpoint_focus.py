from __future__ import annotations

import asyncio

from app.api.v1.endpoints.validation_runs import _paginate_runs
from app.api.v1.endpoints.validation_runs import _serialize_validation_run
from app.api.v1.endpoints.validation_runs import export_validation_run
from app.api.v1.endpoints.validation_runs import get_validation_run
from app.api.v1.endpoints.validation_runs import list_validation_runs
from app.infrastructure.repositories.in_memory_validation_run_repository import InMemoryValidationRunRepository


async def _seed_repository() -> InMemoryValidationRunRepository:
    repository = InMemoryValidationRunRepository()
    await repository.save_run(
        run_id="run-1",
        workspace="ws-1",
        triggered_by="user-1",
        run_at="2026-05-22T10:00:00Z",
        total=1,
        valid_count=1,
        invalid_count=0,
        status="completed",
        items=[
            {
                "id": "item-1",
                "ruleId": "rule-1",
                "ruleName": "Rule 1",
                "ruleVersionNumber": 1,
                "valid": True,
                "errors": 0,
                "warnings": 0,
                "diagnostics": [],
                "conflicts": [],
            }
        ],
    )
    return repository


def test_paginate_runs_helper_serializes_expected_shape() -> None:
    payload = _paginate_runs([{"id": "a"}, {"id": "b"}], page=1, limit=1)

    assert payload["data"] == [{"id": "a"}]
    assert payload["pagination"]["total"] == 2
    assert payload["pagination"]["page"] == 1


def test_serialize_validation_run_returns_model_dump() -> None:
    repository = asyncio.run(_seed_repository())
    run = asyncio.run(repository.get_run("run-1"))

    assert run is not None
    payload = _serialize_validation_run(run)

    assert payload["id"] == "run-1"
    assert payload["validation_items"][0]["rule_id"] == "rule-1"


async def _call_list_validation_runs() -> object:
    repository = await _seed_repository()
    return await list_validation_runs(workspace="ws-1", page=1, limit=20, repository=repository)


async def _call_get_validation_run(run_id: str) -> object:
    repository = await _seed_repository()
    return await get_validation_run(run_id=run_id, repository=repository)


async def _call_export_validation_run(run_id: str, format: str) -> object:
    repository = await _seed_repository()
    return await export_validation_run(run_id=run_id, format=format, repository=repository)


def test_list_validation_runs_returns_paginated_view() -> None:
    result = asyncio.run(_call_list_validation_runs())

    assert result.pagination.total == 1
    assert result.pagination.page == 1
    assert result.data[0].id == "run-1"


def test_get_validation_run_returns_view_and_404() -> None:
    result = asyncio.run(_call_get_validation_run("run-1"))
    assert result.id == "run-1"

    missing_repository = InMemoryValidationRunRepository()
    try:
        asyncio.run(get_validation_run(run_id="missing", repository=missing_repository))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("expected a 404 for missing validation run")


def test_export_validation_run_returns_json_and_csv() -> None:
    json_response = asyncio.run(_call_export_validation_run("run-1", "json"))
    csv_response = asyncio.run(_call_export_validation_run("run-1", "csv"))

    assert json_response.status_code == 200
    assert csv_response.status_code == 200
    assert "application/json" in json_response.media_type
    assert "text/csv" in csv_response.media_type


def test_export_validation_run_returns_404_for_missing_run() -> None:
    repository = InMemoryValidationRunRepository()

    try:
        asyncio.run(export_validation_run(run_id="missing", format="json", repository=repository))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("expected a 404 for missing validation run export")
