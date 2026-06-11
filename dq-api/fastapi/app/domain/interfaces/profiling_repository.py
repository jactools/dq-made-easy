from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
from app.domain.entities import SuggestionProfilingRequestEntity
from app.domain.entities import SuggestionProfilingStartEntity
from ..entities.profiling_request import ProfilingRequest


class ProfilingRepositoryError(Exception):
    pass


class ProfilingDataSourceNotFoundError(ProfilingRepositoryError):
    pass


class ProfilingRequestNotFoundError(ProfilingRepositoryError):
    pass


class ProfilingRateLimitError(ProfilingRepositoryError):
    def __init__(self, *, last_requested_at: str | None, minutes_remaining: int) -> None:
        super().__init__("Profiling was requested recently for this data source")
        self.last_requested_at = last_requested_at
        self.minutes_remaining = minutes_remaining


class ProfilingEnqueueFailedError(ProfilingRepositoryError):
    def __init__(self, *, profiling_request_id: str) -> None:
        super().__init__("Failed to enqueue profiling request")
        self.profiling_request_id = profiling_request_id


class ProfilingRepository(ABC):
    @abstractmethod
    def get_data_source_name(self, data_source_id: str) -> str | None:
        raise NotImplementedError()

    @abstractmethod
    def list_profiling_requests(
        self,
        *,
        user_id: str,
        data_source_id: str | None,
        limit: int,
    ) -> list[SuggestionProfilingRequestEntity]:
        raise NotImplementedError()

    @abstractmethod
    def request_profiling(self, *, user_id: str, data_source_id: str) -> SuggestionProfilingStartEntity:
        raise NotImplementedError()

    @abstractmethod
    def get_profiling_request_status(self, profiling_request_id: str) -> SuggestionProfilingRequestEntity:
        raise NotImplementedError()

    @abstractmethod
    def find_active_profiling_request(self, data_source_id: str) -> SuggestionProfilingRequestEntity | None:
        raise NotImplementedError()

    @abstractmethod
    def create_request(self, request: ProfilingRequest) -> ProfilingRequest:
        raise NotImplementedError()

    @abstractmethod
    def set_started(self, profiling_request_id: str, job_id: str) -> None:
        raise NotImplementedError()

    @abstractmethod
    def set_completed(self, profiling_request_id: str, success: bool, error_message: Optional[str] = None) -> None:
        raise NotImplementedError()
