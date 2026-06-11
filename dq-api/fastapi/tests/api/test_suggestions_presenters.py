from __future__ import annotations

from app.api.presenters.suggestions import build_data_source_not_found_payload
from app.api.presenters.suggestions import build_data_sources_payload
from app.api.presenters.suggestions import build_not_authenticated_payload
from app.api.presenters.suggestions import build_profiling_enqueue_failed_payload
from app.api.presenters.suggestions import build_profiling_rate_limit_payload
from app.api.presenters.suggestions import build_profiling_request_not_found_payload
from app.api.presenters.suggestions import build_profiling_request_status_payload
from app.api.presenters.suggestions import build_profiling_requests_payload
from app.api.presenters.suggestions import build_suggestion_not_found_payload
from app.api.presenters.suggestions import build_suggestions_payload
from app.api.presenters.suggestions import can_request_profiling
from app.api.presenters.suggestions import normalize_suggestion_apply_rule_id
from app.api.presenters.suggestions import serialize_suggestion_entities
from app.api.presenters.suggestions import serialize_suggestion_entity
from app.domain.entities import SuggestionActionResultEntity
from app.domain.entities import SuggestionDataSourceEntity
from app.domain.entities import SuggestionProfilingRequestEntity


def test_suggestions_presenters_serialization_and_payloads(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.presenters.suggestions.has_required_scope",
        lambda scopes, required: "dq:profiling:request" in scopes and bool(required),
    )

    source = SuggestionDataSourceEntity(data_source_id="src-1", name="Source")
    request = SuggestionProfilingRequestEntity(id="req-1", status="pending")
    result = SuggestionActionResultEntity(success=True, message="Suggestion applied")

    assert can_request_profiling(["dq:profiling:request"]) is True
    assert serialize_suggestion_entity(result)["message"] == "Suggestion applied"
    assert serialize_suggestion_entities([source])[0]["data_source_id"] == "src-1"
    assert normalize_suggestion_apply_rule_id({"rule_id": "rule-1"}) == "rule-1"
    assert normalize_suggestion_apply_rule_id({"ruleId": "rule-2"}) == "rule-2"
    assert normalize_suggestion_apply_rule_id({}) is None

    assert build_not_authenticated_payload() == {"error": "Not authenticated", "status": 401}
    assert build_data_source_not_found_payload() == {"error": "Data source not found", "status": 404}
    assert build_suggestion_not_found_payload() == {"error": "Suggestion not found", "status": 404}
    assert build_profiling_request_not_found_payload() == {"error": "Profiling request not found", "status": 404}
    assert build_profiling_rate_limit_payload(last_requested_at="2026-03-29T09:00:00+00:00", minutes_remaining=12) == {
        "error": "Profiling was requested recently for this data source",
        "last_requested_at": "2026-03-29T09:00:00+00:00",
        "minutes_remaining": 12,
        "status": 429,
    }
    assert build_profiling_enqueue_failed_payload(profiling_request_id="req-2") == {
        "error": "profiling_enqueue_failed",
        "message": "Failed to enqueue profiling request",
        "profiling_request_id": "req-2",
        "status": 503,
    }
    assert build_data_sources_payload(data_sources=[source], granted_scopes=["dq:profiling:request"]) == {
        "success": True,
        "data_sources": [serialize_suggestion_entity(source)],
        "can_request_profiling": True,
    }
    assert build_suggestions_payload([result]) == {
        "success": True,
        "suggestions": [serialize_suggestion_entity(result)],
        "count": 1,
    }
    assert build_profiling_requests_payload([request]) == {
        "success": True,
        "profiling_requests": [serialize_suggestion_entity(request)],
        "count": 1,
    }
    assert build_profiling_request_status_payload(request) == {
        "success": True,
        "request": serialize_suggestion_entity(request),
    }
