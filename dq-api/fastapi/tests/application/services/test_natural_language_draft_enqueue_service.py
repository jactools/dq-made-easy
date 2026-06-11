from __future__ import annotations

import json

from app.application.services.natural_language_draft_enqueue_service import _build_queue_payload
from app.application.services.natural_language_draft_enqueue_service import mark_request_completed
from app.application.services.natural_language_draft_enqueue_service import mark_request_started
from app.api.v1.schemas.natural_language_rule_drafting_view import NaturalLanguageRulePreviewCreateSuggestionRequestView


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.events: list[dict[str, object]] = []

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def xadd(self, key: str, fields: dict[str, str], maxlen: int | None = None, approximate: bool = False) -> str:
        self.events.append({"key": key, "fields": fields, "maxlen": maxlen, "approximate": approximate})
        return f"{len(self.events)}-0"


def test_build_queue_payload_uses_snake_case_contract() -> None:
    request_body = NaturalLanguageRulePreviewCreateSuggestionRequestView(
        prompt="Suggest the most appropriate DQ rule for customer_id 123",
        search_scope="current",
        current_workspace_id="retail-banking",
        analysis_provider="llm",
        selected_attribute_ids=["attr-retail-customer-id"],
    )

    payload = _build_queue_payload(
        request_body,
        correlation_id="corr-1",
        requested_by_user_id="user-1",
        accessible_workspace_ids={"retail-banking"},
        selected_attribute_ids=["attr-retail-customer-id"],
    )

    assert payload["current_workspace_id"] == "retail-banking"
    assert payload["selected_attribute_ids"] == ["attr-retail-customer-id"]
    assert payload["analysis_provider"] == "llm"
    assert payload["requested_by_user_id"] == "user-1"
    assert payload["correlation_id"] == "corr-1"


def test_status_transitions_publish_stream_events() -> None:
    client = _FakeRedis()
    record = {
        "request_id": "request-1",
        "job_id": "job-1",
        "current_workspace_id": "retail-banking",
        "version_id": "version-1",
        "selected_attribute_ids": ["attr-1"],
        "prompt": "Generate data definitions",
        "requested_by_user_id": "user-1",
        "requested_at": "2026-05-26T12:00:00+00:00",
        "status": "pending",
        "analysis_type": "definition_task",
        "analysis_provider": "llm",
        "task_payload": {"version_id": "version-1"},
    }
    client.set("natural-language-draft-request:request-1", json.dumps(record))

    started = mark_request_started(client, request_id="request-1", job_id="job-2")
    completed = mark_request_completed(
        client,
        request_id="request-1",
        success=True,
        result={"registry_contract": {"definitions": []}},
    )

    assert started is not None
    assert started["status"] == "started"
    assert completed is not None
    assert completed["status"] == "completed"
    assert [event["key"] for event in client.events] == [
        "natural-language-draft-request-events:request-1",
        "natural-language-draft-request-events:request-1",
    ]
    started_payload = json.loads(client.events[0]["fields"]["data"])
    completed_payload = json.loads(client.events[1]["fields"]["data"])
    assert started_payload["status"] == "started"
    assert started_payload["request"]["analysis_type"] == "definition_task"
    assert completed_payload["status"] == "completed"
    assert completed_payload["request"]["result"] == {"registry_contract": {"definitions": []}}