from typing import Protocol

from app.domain.entities import SuggestionActionResultEntity
from app.domain.entities import SuggestionDataSourceEntity
from app.domain.entities import NaturalLanguageDraftRequestEntity
from app.domain.entities import NaturalLanguageDraftRequestHistoryEntity
from app.domain.entities import SuggestionEntity
from app.domain.entities import SuggestionMetricsClearResultEntity


class SuggestionsRepositoryError(Exception):
    pass


class SuggestionDataSourceNotFoundError(SuggestionsRepositoryError):
    pass


class SuggestionNotFoundError(SuggestionsRepositoryError):
    pass


class NaturalLanguageDraftRequestNotFoundError(SuggestionsRepositoryError):
    pass


class SuggestionsRepository(Protocol):
    def list_data_sources(self) -> list[SuggestionDataSourceEntity]:
        ...

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
        ...

    def list_suggestions(
        self,
        *,
        user_id: str | None,
        data_source_id: str | None,
        status: str,
    ) -> list[SuggestionEntity]:
        ...

    def record_natural_language_request(
        self,
        *,
        request: NaturalLanguageDraftRequestEntity,
    ) -> NaturalLanguageDraftRequestEntity:
        ...

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
        ...

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
        ...

    def list_natural_language_request_history(
        self,
        *,
        request_id: str,
        limit: int,
        offset: int,
    ) -> list[NaturalLanguageDraftRequestHistoryEntity] | None:
        ...

    def list_natural_language_requests(
        self,
        *,
        user_id: str,
        workspace_id: str | None,
        limit: int,
    ) -> list[NaturalLanguageDraftRequestEntity]:
        ...

    def update_suggestion_status(
        self,
        *,
        user_id: str,
        suggestion_id: str,
        action: str,
        rule_id: str | None = None,
    ) -> SuggestionActionResultEntity:
        ...

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
        ...

    def clear_metrics(self) -> SuggestionMetricsClearResultEntity:
        ...