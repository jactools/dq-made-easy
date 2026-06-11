from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ConfigDict, Field

from app.schemas.pydantic_base import SnakeModel, to_snake_alias

from app.application.services import normalize_join_definition
from app.application.services import validate_filter_expression
from app.api.presenters.reusable_assets import build_reusable_filter_create_payload
from app.api.presenters.reusable_assets import build_reusable_filter_update_payload
from app.api.presenters.reusable_assets import build_reusable_join_create_payload
from app.api.presenters.reusable_assets import build_reusable_join_update_payload
from app.core.dependencies import get_rules_repository
from app.core.request_context import get_user_id
from app.domain.interfaces import RulesRepository

router = APIRouter(tags=["rules"])


def _validate_filter_expression(raw_expression: str) -> str | None:
    return validate_filter_expression(raw_expression)


class ReusableFilterCreateRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    name: str
    expression: str | None = None
    filterExpression: str | None = None
    description: str | None = None
    workspace: str | None = None
    workspaceId: str | None = None
    active: bool = True


class ReusableJoinCreateRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    name: str
    joinDefinition: str | list[dict] | dict | None = None
    description: str | None = None
    workspace: str | None = None
    workspaceId: str | None = None
    active: bool = True


class ReusableFilterUpdateRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    name: str | None = None
    expression: str | None = None
    filterExpression: str | None = None
    description: str | None = None
    active: bool | None = None


class ReusableJoinUpdateRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    name: str | None = None
    joinDefinition: str | list[dict] | dict | None = None
    description: str | None = None
    active: bool | None = None


@router.get("/reusable-filters")
async def list_reusable_filters(
    workspace: str | None = Query(default=None),
    q: str | None = Query(default=None),
    repository: RulesRepository = Depends(get_rules_repository),
) -> list[dict]:
    return await repository.list_reusable_filters(workspace=workspace, query=q)


@router.post("/reusable-filters")
async def create_reusable_filter(
    body: ReusableFilterCreateRequest,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    payload = build_reusable_filter_create_payload(
        body=body,
        actor_id=get_user_id(),
        expression_validator=_validate_filter_expression,
    )
    return await repository.create_reusable_filter(**payload)


@router.delete("/reusable-filters/{filter_id}")
async def delete_reusable_filter(
    filter_id: str,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    try:
        deleted = await repository.delete_reusable_filter(filter_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Not found")

    return {"ok": True}


@router.get("/reusable-filters/{filter_id}")
async def get_reusable_filter(
    filter_id: str,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    reusable_filter = await repository.get_reusable_filter(filter_id)
    if reusable_filter is None:
        raise HTTPException(status_code=404, detail="Not found")
    return reusable_filter


@router.put("/reusable-filters/{filter_id}")
async def update_reusable_filter(
    filter_id: str,
    body: ReusableFilterUpdateRequest,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    existing = await repository.get_reusable_filter(filter_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Not found")

    payload = build_reusable_filter_update_payload(
        body=body,
        existing=existing,
        expression_validator=_validate_filter_expression,
    )

    updated = await repository.update_reusable_filter(filter_id=filter_id, **payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Not found")
    return updated


@router.get("/reusable-joins")
async def list_reusable_joins(
    workspace: str | None = Query(default=None),
    repository: RulesRepository = Depends(get_rules_repository),
) -> list[dict]:
    return await repository.list_reusable_joins(workspace=workspace)


@router.post("/reusable-joins")
async def create_reusable_join(
    body: ReusableJoinCreateRequest,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    payload = build_reusable_join_create_payload(
        body=body,
        actor_id=get_user_id(),
        join_definition_normalizer=normalize_join_definition,
    )
    return await repository.create_reusable_join(**payload)


@router.delete("/reusable-joins/{join_id}")
async def delete_reusable_join(
    join_id: str,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    try:
        deleted = await repository.delete_reusable_join(join_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Not found")

    return {"ok": True}


@router.get("/reusable-joins/{join_id}")
async def get_reusable_join(
    join_id: str,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    reusable_join = await repository.get_reusable_join(join_id)
    if reusable_join is None:
        raise HTTPException(status_code=404, detail="Not found")
    return reusable_join


@router.put("/reusable-joins/{join_id}")
async def update_reusable_join(
    join_id: str,
    body: ReusableJoinUpdateRequest,
    repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    existing = await repository.get_reusable_join(join_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Not found")

    payload = build_reusable_join_update_payload(
        body=body,
        existing=existing,
        join_definition_normalizer=normalize_join_definition,
    )

    updated = await repository.update_reusable_join(join_id=join_id, **payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Not found")
    return updated