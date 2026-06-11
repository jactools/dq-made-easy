from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from app.core.auth import has_required_scope
from app.domain.entities.base import EntityModel


def can_request_profiling(
    granted_scopes: Sequence[str],
    *,
    scope_checker: Callable[[list[str], list[str]], bool] = has_required_scope,
) -> bool:
    return scope_checker(list(granted_scopes), ["dq:profiling:request", "dq:rules:test"])


def serialize_suggestion_entity(entity: EntityModel) -> dict[str, Any]:
    return entity.model_dump(mode="json")


def serialize_suggestion_entities(entities: Sequence[EntityModel]) -> list[dict[str, Any]]:
    return [serialize_suggestion_entity(entity) for entity in entities]


def normalize_suggestion_apply_rule_id(payload: dict[str, Any] | None) -> str | None:
    normalized_payload = payload or {}
    rule_id = normalized_payload.get("rule_id")
    if rule_id is None:
        rule_id = normalized_payload.get("ruleId")
    return str(rule_id) if rule_id is not None else None


def build_not_authenticated_payload() -> dict[str, Any]:
    return {"error": "Not authenticated", "status": 401}


def build_data_sources_payload(*, data_sources: Sequence[EntityModel], granted_scopes: Sequence[str]) -> dict[str, Any]:
    return {
        "success": True,
        "data_sources": serialize_suggestion_entities(data_sources),
        "can_request_profiling": can_request_profiling(granted_scopes),
    }


def build_suggestions_payload(suggestions: Sequence[EntityModel]) -> dict[str, Any]:
    serialized = serialize_suggestion_entities(suggestions)
    return {
        "success": True,
        "suggestions": serialized,
        "count": len(serialized),
    }


def build_profiling_requests_payload(requests: Sequence[EntityModel]) -> dict[str, Any]:
    serialized = serialize_suggestion_entities(requests)
    return {
        "success": True,
        "profiling_requests": serialized,
        "count": len(serialized),
    }


def build_profiling_rate_limit_payload(*, last_requested_at: str, minutes_remaining: int) -> dict[str, Any]:
    return {
        "error": "Profiling was requested recently for this data source",
        "last_requested_at": last_requested_at,
        "minutes_remaining": minutes_remaining,
        "status": 429,
    }


def build_profiling_enqueue_failed_payload(*, profiling_request_id: str) -> dict[str, Any]:
    return {
        "error": "profiling_enqueue_failed",
        "message": "Failed to enqueue profiling request",
        "profiling_request_id": profiling_request_id,
        "status": 503,
    }


def build_natural_language_draft_queue_failed_payload(*, request_id: str | None = None) -> dict[str, Any]:
    return {
        "error": "natural_language_draft_enqueue_failed",
        "message": "Failed to enqueue natural-language draft request",
        "request_id": request_id,
        "status": 503,
    }


def build_natural_language_draft_request_not_found_payload() -> dict[str, Any]:
    return {"error": "Natural-language draft request not found", "status": 404}


def build_suggestion_not_found_payload() -> dict[str, Any]:
    return {"error": "Suggestion not found", "status": 404}


def build_data_source_not_found_payload() -> dict[str, Any]:
    return {"error": "Data source not found", "status": 404}


def build_profiling_request_not_found_payload() -> dict[str, Any]:
    return {"error": "Profiling request not found", "status": 404}


def build_profiling_request_status_payload(request: EntityModel) -> dict[str, Any]:
    return {
        "success": True,
        "request": serialize_suggestion_entity(request),
    }