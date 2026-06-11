from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fastapi import HTTPException


def build_reusable_filter_create_payload(
    *,
    body: Any,
    actor_id: str | None,
    expression_validator: Callable[[str], str | None],
) -> dict[str, Any]:
    name = str(getattr(body, "name", "") or "").strip()
    expression = str(getattr(body, "expression", None) or getattr(body, "filterExpression", None) or "").strip()
    description = str(getattr(body, "description", "") or "").strip() or None
    workspace = str(getattr(body, "workspace", None) or getattr(body, "workspaceId", None) or "default").strip() or "default"

    if not name:
        raise HTTPException(status_code=400, detail="Filter name is required")

    validation_error = expression_validator(expression)
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)

    return {
        "name": name,
        "expression": expression,
        "description": description,
        "workspace": workspace,
        "created_by": actor_id or "user-admin",
        "active": bool(getattr(body, "active", True)),
    }


def build_reusable_filter_update_payload(
    *,
    body: Any,
    existing: Mapping[str, Any],
    expression_validator: Callable[[str], str | None],
) -> dict[str, Any]:
    name = str(body.name).strip() if getattr(body, "name", None) is not None else str(existing.get("name") or "").strip()
    description = body.description.strip() if getattr(body, "description", None) is not None else existing.get("description")

    if getattr(body, "expression", None) is not None:
        expression = str(body.expression).strip()
    elif getattr(body, "filterExpression", None) is not None:
        expression = str(body.filterExpression).strip()
    else:
        expression = str(existing.get("filter_expression") or existing.get("expression") or "").strip()

    active = body.active if isinstance(getattr(body, "active", None), bool) else bool(existing.get("active"))

    if not name:
        raise HTTPException(status_code=400, detail="Filter name is required")
    if not expression:
        raise HTTPException(status_code=400, detail="Filter expression is required")

    validation_error = expression_validator(expression)
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)

    return {
        "name": name,
        "expression": expression,
        "description": description,
        "active": active,
    }


def build_reusable_join_create_payload(
    *,
    body: Any,
    actor_id: str | None,
    join_definition_normalizer: Callable[[Any], tuple[str | None, str | None]],
) -> dict[str, Any]:
    name = str(getattr(body, "name", "") or "").strip()
    description = str(getattr(body, "description", "") or "").strip() or None
    workspace = str(getattr(body, "workspace", None) or getattr(body, "workspaceId", None) or "default").strip() or "default"
    join_definition = getattr(body, "joinDefinition", None)

    if not name:
        raise HTTPException(status_code=400, detail="Join name is required")
    if join_definition is None:
        raise HTTPException(status_code=400, detail="Join definition is required")

    serialized_join_definition, join_error = join_definition_normalizer(join_definition)
    if join_error:
        raise HTTPException(status_code=400, detail=join_error)
    if not serialized_join_definition:
        raise HTTPException(status_code=400, detail="Join definition is required")

    return {
        "name": name,
        "join_definition": serialized_join_definition,
        "description": description,
        "workspace": workspace,
        "created_by": actor_id or "user-admin",
        "active": bool(getattr(body, "active", True)),
    }


def build_reusable_join_update_payload(
    *,
    body: Any,
    existing: Mapping[str, Any],
    join_definition_normalizer: Callable[[Any], tuple[str | None, str | None]],
) -> dict[str, Any]:
    name = str(body.name).strip() if getattr(body, "name", None) is not None else str(existing.get("name") or "").strip()
    description = body.description.strip() if getattr(body, "description", None) is not None else existing.get("description")

    if getattr(body, "joinDefinition", None) is not None:
        join_definition_input = body.joinDefinition
    else:
        join_definition_input = existing.get("join_definition")

    if join_definition_input is None:
        raise HTTPException(status_code=400, detail="Join definition is required")

    serialized_join_definition, join_error = join_definition_normalizer(join_definition_input)
    if join_error:
        raise HTTPException(status_code=400, detail=join_error)
    if not serialized_join_definition:
        raise HTTPException(status_code=400, detail="Join definition is required")

    active = body.active if isinstance(getattr(body, "active", None), bool) else bool(existing.get("active"))

    if not name:
        raise HTTPException(status_code=400, detail="Join name is required")

    return {
        "name": name,
        "join_definition": serialized_join_definition,
        "description": description,
        "active": active,
    }