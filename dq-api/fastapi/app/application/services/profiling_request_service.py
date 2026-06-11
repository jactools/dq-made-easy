from __future__ import annotations

from app.domain.entities import SuggestionProfilingRequestEntity
from app.domain.entities import SuggestionProfilingStartEntity
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import ProfilingRepository


class ProfilingRequestService:
    def __init__(
        self,
        *,
        profiling_repository: ProfilingRepository,
        approvals_repository: ApprovalsRepository,
    ) -> None:
        self._profiling_repository = profiling_repository
        self._approvals_repository = approvals_repository

    def request_profiling(
        self,
        *,
        user_id: str,
        data_source_id: str,
        workspace_id: str,
    ) -> SuggestionProfilingStartEntity:
        result = self._profiling_repository.request_profiling(user_id=user_id, data_source_id=data_source_id)
        data_source_name = self._profiling_repository.get_data_source_name(data_source_id) or data_source_id

        self._approvals_repository.append_audit_event(
            approval_id=f"profiling-request:{data_source_id}:{result.profiling_request_id}",
            action="profiling.requested",
            actor_id=user_id,
            details={
                "workspace_id": workspace_id,
                "data_source_id": data_source_id,
                "data_source_name": data_source_name,
                "profiling_request_id": result.profiling_request_id,
                "message": f"Profiling requested for {data_source_name}",
            },
        )
        return result

    def list_profiling_requests(
        self,
        *,
        user_id: str,
        data_source_id: str | None,
        limit: int,
    ) -> list[SuggestionProfilingRequestEntity]:
        return self._profiling_repository.list_profiling_requests(
            user_id=user_id,
            data_source_id=data_source_id,
            limit=limit,
        )

    def get_profiling_request_status(self, profiling_request_id: str) -> SuggestionProfilingRequestEntity:
        return self._profiling_repository.get_profiling_request_status(profiling_request_id)