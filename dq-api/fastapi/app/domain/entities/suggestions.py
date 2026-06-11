from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.entities.base import EntityModel


class SuggestionDataSourceEntity(EntityModel):
    data_source_id: str
    name: str = ""
    source_type: str | None = None
    record_count: int | None = None
    last_profiled_at: str | None = None


class SuggestionEntity(EntityModel):
    id: str
    user_id: str | None = None
    data_source_id: str = ""
    suggested_rule: dict | None = None
    confidence_score: float | None = None
    reason: str | None = None
    rule_type: str | None = None
    created_from_profiling_request_id: str | None = None
    status: str = "pending"
    created_at: str | None = None
    expires_at: str | None = None


class TagSuggestionEntity(EntityModel):
    id: str
    name: str
    usage_count: int = 0
    source_count: int = 0


class SuggestionProfilingRequestEntity(EntityModel):
    id: str
    data_source_id: str = ""
    requested_by_user_id: str | None = None
    requested_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    status: str = "pending"
    error_message: str | None = None
    result_metadata_id: str | None = None
    job_id: str | None = None


class NaturalLanguageDraftRequestEntity(EntityModel):
    request_id: str
    job_id: str
    current_workspace_id: str = ""
    search_scope: str = "current"
    analysis_provider: str = "llm"
    analysis_type: str = "preview"
    prompt: str = ""
    selected_attribute_ids: list[str] = Field(default_factory=list)
    accessible_workspace_ids: list[str] = Field(default_factory=list)
    requested_by_user_id: str | None = None
    requested_by_email: str | None = None
    requested_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    status: str = "pending"
    error_message: str | None = None
    suggestion_id: str | None = None
    result: dict[str, Any] | None = None
    correlation_id: str | None = None


class NaturalLanguageDraftRequestHistoryEntity(EntityModel):
    id: str
    request_id: str
    action: str
    from_status: str | None = None
    to_status: str | None = None
    actor_id: str | None = None
    changed_at: str
    details: dict[str, Any] = Field(default_factory=dict)


class SuggestionProfilingStartEntity(EntityModel):
    success: bool = True
    profiling_request_id: str
    message: str
    status: str = "pending"


class SuggestionActionResultEntity(EntityModel):
    success: bool = True
    message: str


class SuggestionMetricsClearResultEntity(EntityModel):
    success: bool = True
    message: str
    deleted_count: int = 0