"""Validation run history endpoints — DQ-1.4."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.presenters.validation_runs import build_validation_run_csv_export
from app.api.presenters.validation_runs import build_validation_run_json_export
from app.api.presenters.validation_runs import build_validation_run_payload
from app.api.presenters.validation_runs import build_validation_runs_page_payload
from app.api.v1.schemas import ValidationRunView, ValidationRunsPageView
from app.core.dependencies import get_validation_run_repository
from app.domain.interfaces import ValidationRunRepository

router = APIRouter(prefix="/rules/validation-runs", tags=["validation-runs"])


def _serialize_validation_run(run) -> dict:
    return build_validation_run_payload(run)


def _paginate_runs(rows: list[dict], page: int, limit: int) -> dict:
    return build_validation_runs_page_payload(rows, page=page, limit=limit)


@router.get("", response_model=ValidationRunsPageView)
async def list_validation_runs(
    workspace: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    repository: ValidationRunRepository = Depends(get_validation_run_repository),
) -> ValidationRunsPageView:
    offset = (page - 1) * limit
    result = await repository.list_runs(workspace=workspace, limit=limit, offset=offset)
    rows = list(result.data)
    total = int(result.total)
    return ValidationRunsPageView.model_validate(
        build_validation_runs_page_payload(
            [_serialize_validation_run(row) for row in rows],
            page=page,
            limit=limit,
            total=total,
        )
    )


@router.get("/{run_id}", response_model=ValidationRunView)
async def get_validation_run(
    run_id: str,
    repository: ValidationRunRepository = Depends(get_validation_run_repository),
) -> ValidationRunView:
    run = await repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Validation run '{run_id}' not found")
    return ValidationRunView.model_validate(_serialize_validation_run(run))


@router.get("/{run_id}/export")
async def export_validation_run(
    run_id: str,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    repository: ValidationRunRepository = Depends(get_validation_run_repository),
) -> Response:
    run = await repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Validation run '{run_id}' not found")
    serialized_run = _serialize_validation_run(run)

    if format == "csv":
        return Response(
            content=build_validation_run_csv_export(run_id=run_id, serialized_run=serialized_run),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=validation-run-{run_id}.csv"},
        )

    # JSON export
    return Response(
        content=build_validation_run_json_export(serialized_run),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=validation-run-{run_id}.json"},
    )
