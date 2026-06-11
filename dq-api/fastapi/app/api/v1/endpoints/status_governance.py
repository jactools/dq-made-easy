from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ConfigDict, Field

from app.core.request_context import get_scopes
from app.domain.status_governance import build_allowed_transitions_by_status_map
from app.domain.status_governance import canonicalize_status
from app.domain.status_governance import get_status_model_definition
from app.domain.status_governance import is_transition_allowed
from app.domain.status_governance import is_transition_defined
from app.domain.status_governance import normalize_status
from app.schemas.pydantic_base import SnakeModel, to_snake_alias

router = APIRouter(tags=["governance"])


class StatusValueView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    value: str
    label: str
    description: str | None = None
    isInitial: bool = False
    isTerminal: bool = False


class StatusTransitionView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    fromStatus: str
    toStatus: str
    label: str
    requiredAnyScopes: list[str] = Field(default_factory=list)


class StatusModelView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    entity: str
    statuses: list[StatusValueView]
    transitions: list[StatusTransitionView]
    allowedTransitionsByStatus: dict[str, list[str]]


@router.get("/governance/status-models/{entity}", response_model=StatusModelView)
async def get_status_model(entity: str) -> StatusModelView:
    normalized_entity = str(entity or "").strip().lower()
    model_definition = get_status_model_definition(normalized_entity)
    if model_definition is None:
        raise HTTPException(status_code=404, detail=f"Unknown status model entity '{entity}'")
    statuses, transitions = model_definition

    scopes = [str(scope).strip() for scope in get_scopes() if str(scope).strip()]

    return StatusModelView(
        entity=normalized_entity,
        statuses=[StatusValueView.model_validate(status.model_dump()) for status in statuses],
        transitions=[StatusTransitionView.model_validate(transition.model_dump()) for transition in transitions],
        allowedTransitionsByStatus=build_allowed_transitions_by_status_map(
            transitions=transitions,
            granted_scopes=scopes,
        ),
    )
