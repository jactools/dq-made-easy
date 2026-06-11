from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.domain.entities import SuggestionActionResultEntity
from app.domain.entities import SuggestionDataSourceEntity
from app.domain.entities import NaturalLanguageDraftRequestEntity
from app.domain.entities import NaturalLanguageDraftRequestHistoryEntity
from app.domain.entities import SuggestionEntity
from app.domain.entities import SuggestionMetricsClearResultEntity
from app.domain.interfaces.v1.suggestions_repository import SuggestionNotFoundError
from app.domain.interfaces.v1.suggestions_repository import NaturalLanguageDraftRequestNotFoundError
from app.domain.interfaces.v1.suggestions_repository import SuggestionsRepository


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.isoformat()


class InMemorySuggestionsRepository(SuggestionsRepository):
    def __init__(
        self,
        *,
        data_sources: list[dict] | None = None,
        suggestions: list[dict] | None = None,
        natural_language_requests: list[dict] | None = None,
    ) -> None:
        self.data_sources = list(data_sources or [])
        self.suggestions = list(suggestions or [])
        self.natural_language_requests = list(natural_language_requests or [])
        self.natural_language_request_history: list[dict[str, Any]] = []
        self.interactions: list[dict[str, Any]] = []
        self.preview_interactions: list[dict[str, Any]] = []

    @staticmethod
    def _coerce_data_source(row: SuggestionDataSourceEntity | dict) -> SuggestionDataSourceEntity:
        if isinstance(row, SuggestionDataSourceEntity):
            return row
        return SuggestionDataSourceEntity.model_validate(row)

    @staticmethod
    def _coerce_suggestion(row: SuggestionEntity | dict) -> SuggestionEntity:
        if isinstance(row, SuggestionEntity):
            return row
        return SuggestionEntity.model_validate(row)

    @staticmethod
    def _coerce_natural_language_request(
        row: NaturalLanguageDraftRequestEntity | dict,
    ) -> NaturalLanguageDraftRequestEntity:
        if isinstance(row, NaturalLanguageDraftRequestEntity):
            return row
        return NaturalLanguageDraftRequestEntity.model_validate(row)

    @staticmethod
    def _coerce_natural_language_request_history(
        row: NaturalLanguageDraftRequestHistoryEntity | dict,
    ) -> NaturalLanguageDraftRequestHistoryEntity:
        if isinstance(row, NaturalLanguageDraftRequestHistoryEntity):
            return row
        return NaturalLanguageDraftRequestHistoryEntity.model_validate(row)

    def list_data_sources(self) -> list[SuggestionDataSourceEntity]:
        return [self._coerce_data_source(row) for row in self.data_sources]

    def create_suggestion(
        self,
        *,
        user_id: str,
        data_source_id: str,
        suggested_rule: dict,
        confidence_score: float | None,
        reason: str | None,
        rule_type: str | None,
        created_from_profiling_request_id: str | None = None,
    ) -> SuggestionEntity:
        entity = SuggestionEntity(
            id=str(uuid4()),
            user_id=user_id,
            data_source_id=data_source_id,
            suggested_rule=dict(suggested_rule),
            confidence_score=confidence_score,
            reason=reason,
            rule_type=rule_type,
            created_from_profiling_request_id=created_from_profiling_request_id,
            status="pending",
            created_at=_utc_iso(datetime.now(UTC)),
            expires_at=None,
        )
        self.suggestions.insert(0, entity.model_dump(mode="json"))
        return entity

    def list_suggestions(
        self,
        *,
        user_id: str | None,
        data_source_id: str | None,
        status: str,
    ) -> list[SuggestionEntity]:
        rows = list(self.suggestions)
        if user_id:
            rows = [row for row in rows if row.get("user_id") == user_id]
        if data_source_id:
            rows = [row for row in rows if row.get("data_source_id") == data_source_id]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return [self._coerce_suggestion(row) for row in rows]

    def record_natural_language_request(
        self,
        *,
        request: NaturalLanguageDraftRequestEntity,
    ) -> NaturalLanguageDraftRequestEntity:
        self.natural_language_requests.insert(0, request.model_dump(mode="json"))
        self.record_natural_language_request_history_event(
            request_id=request.request_id,
            action="created",
            to_status=request.status,
            actor_id=request.requested_by_user_id,
            details={
                "job_id": request.job_id,
                "analysis_type": request.analysis_type,
                "analysis_provider": request.analysis_provider,
                "current_workspace_id": request.current_workspace_id,
                "selected_attribute_ids": list(request.selected_attribute_ids),
                "accessible_workspace_ids": list(request.accessible_workspace_ids),
                "correlation_id": request.correlation_id,
            },
        )
        return request

    def update_natural_language_request(
        self,
        *,
        request_id: str,
        status: str,
        job_id: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        error_message: str | None = None,
        suggestion_id: str | None = None,
        result: dict | None = None,
    ) -> NaturalLanguageDraftRequestEntity:
        request = next((row for row in self.natural_language_requests if row.get("request_id") == request_id), None)
        if request is None:
            raise NaturalLanguageDraftRequestNotFoundError("Natural-language request not found")

        previous_status = str(request.get("status") or "pending")
        request["status"] = status
        if job_id is not None:
            request["job_id"] = job_id
        if started_at is not None:
            request["started_at"] = started_at
        if completed_at is not None:
            request["completed_at"] = completed_at
        request["error_message"] = error_message
        request["suggestion_id"] = suggestion_id
        if result is not None:
            request["result"] = dict(result)
        self.record_natural_language_request_history_event(
            request_id=request_id,
            action="status_changed",
            from_status=previous_status,
            to_status=status,
            details={
                "job_id": request.get("job_id"),
                "started_at": request.get("started_at"),
                "completed_at": request.get("completed_at"),
                "error_message": error_message,
                "suggestion_id": suggestion_id,
                "result": dict(result) if result is not None else request.get("result"),
            },
        )
        return self._coerce_natural_language_request(request)

    def record_natural_language_request_history_event(
        self,
        *,
        request_id: str,
        action: str,
        from_status: str | None = None,
        to_status: str | None = None,
        actor_id: str | None = None,
        details: dict | None = None,
    ) -> NaturalLanguageDraftRequestHistoryEntity:
        item = {
            "id": str(uuid4()),
            "request_id": request_id,
            "action": str(action or "unknown").strip().lower() or "unknown",
            "from_status": from_status,
            "to_status": to_status,
            "actor_id": actor_id,
            "changed_at": _utc_iso(datetime.now(UTC)),
            "details": dict(details) if details is not None else {},
        }
        self.natural_language_request_history.insert(0, item)
        return self._coerce_natural_language_request_history(item)

    def list_natural_language_request_history(
        self,
        *,
        request_id: str,
        limit: int,
        offset: int,
    ) -> list[NaturalLanguageDraftRequestHistoryEntity] | None:
        if not any(row.get("request_id") == request_id for row in self.natural_language_requests):
            return None

        rows = [row for row in self.natural_language_request_history if row.get("request_id") == request_id]
        normalized_limit = max(1, min(limit, 100))
        normalized_offset = max(0, offset)
        window = rows[normalized_offset : normalized_offset + normalized_limit]
        return [self._coerce_natural_language_request_history(row) for row in window]

    def list_natural_language_requests(
        self,
        *,
        user_id: str,
        workspace_id: str | None,
        limit: int,
    ) -> list[NaturalLanguageDraftRequestEntity]:
        rows = [row for row in self.natural_language_requests if row.get("requested_by_user_id") == user_id]
        if workspace_id:
            rows = [row for row in rows if row.get("current_workspace_id") == workspace_id]
        return [self._coerce_natural_language_request(row) for row in rows[: max(1, min(limit, 100))]]

    def update_suggestion_status(
        self,
        *,
        user_id: str,
        suggestion_id: str,
        action: str,
        rule_id: str | None = None,
    ) -> SuggestionActionResultEntity:
        status_map = {
            "accept": "accepted",
            "dismiss": "dismissed",
            "apply": "applied",
        }
        suggestion = next((row for row in self.suggestions if row.get("id") == suggestion_id), None)
        if suggestion is None:
            raise SuggestionNotFoundError("Suggestion not found")

        next_status = status_map[action]
        suggestion["status"] = next_status
        self.interactions.append(
            {
                "id": str(uuid4()),
                "suggestion_id": suggestion_id,
                "user_id": user_id,
                "action": next_status,
                "rule_created_from_suggestion_id": rule_id,
                "created_at": _utc_iso(datetime.now(UTC)),
            }
        )
        if str(suggestion.get("data_source_id") or "").startswith("nl-preview:"):
            preview_action = {
                "accepted": "suggestion_accepted",
                "dismissed": "suggestion_rejected",
                "applied": "suggestion_applied",
            }.get(next_status)
            if preview_action:
                self.preview_interactions.append(
                    {
                        "id": str(uuid4()),
                        "user_id": user_id,
                        "workspace_id": str(suggestion.get("data_source_id") or "").removeprefix("nl-preview:"),
                        "action": preview_action,
                        "result": "success",
                        "error_code": None,
                        "details_json": {"suggestion_id": suggestion_id},
                        "created_at": _utc_iso(datetime.now(UTC)),
                    }
                )
        return SuggestionActionResultEntity(message=f"Suggestion {next_status}")

    def record_preview_event(
        self,
        *,
        user_id: str,
        workspace_id: str,
        action: str,
        result: str = "success",
        error_code: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.preview_interactions.append(
            {
                "id": str(uuid4()),
                "user_id": user_id,
                "workspace_id": workspace_id,
                "action": action,
                "result": result,
                "error_code": error_code,
                "details_json": dict(details) if details is not None else None,
                "created_at": _utc_iso(datetime.now(UTC)),
            }
        )

    def clear_metrics(self) -> SuggestionMetricsClearResultEntity:
        deleted_count = len(self.interactions) + len(self.preview_interactions) + len(self.natural_language_request_history)
        self.interactions.clear()
        self.preview_interactions.clear()
        self.natural_language_request_history.clear()
        return SuggestionMetricsClearResultEntity(
            message="Suggestions metrics cleared",
            deleted_count=deleted_count,
        )