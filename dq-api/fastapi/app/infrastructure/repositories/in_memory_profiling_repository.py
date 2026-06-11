from __future__ import annotations
from datetime import datetime
from typing import Dict, Optional

from app.domain.entities.profiling_request import ProfilingRequest
from app.domain.interfaces.profiling_repository import ProfilingRepository

from datetime import UTC, timedelta
from uuid import uuid4

from app.domain.entities import SuggestionDataSourceEntity
from app.domain.entities import SuggestionProfilingRequestEntity
from app.domain.entities import SuggestionProfilingStartEntity
from app.domain.interfaces.profiling_repository import ProfilingDataSourceNotFoundError
from app.domain.interfaces.profiling_repository import ProfilingRateLimitError
from app.domain.interfaces.profiling_repository import ProfilingRequestNotFoundError

def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.isoformat()

class InMemoryProfilingRepository(ProfilingRepository):
    def __init__(self, *, data_sources: list[dict] | None = None, profiling_requests: list[dict] | None = None) -> None:
        self._store: Dict[str, dict] = {}
        self._next_id = 1
        self.data_sources = list(data_sources or [])

        for row in profiling_requests or []:
            profiling_request_id = str(row.get("id") or row.get("profiling_request_id") or uuid4())
            self._store[profiling_request_id] = {
                "id": row.get("id") or profiling_request_id,
                "profiling_request_id": profiling_request_id,
                "data_source_id": row.get("data_source_id"),
                "requested_by_user_id": row.get("requested_by_user_id"),
                "requested_at": row.get("requested_at"),
                "started_at": row.get("started_at"),
                "completed_at": row.get("completed_at"),
                "status": row.get("status") or "pending",
                "error_message": row.get("error_message"),
                "job_id": row.get("job_id"),
            }

    def get_data_source_name(self, data_source_id: str) -> str | None:
        source = next((row for row in self.data_sources if row.get("data_source_id") == data_source_id), None)
        if source is None:
            return None
        entity = SuggestionDataSourceEntity.model_validate(source)
        return entity.name

    def list_profiling_requests(
        self,
        *,
        user_id: str,
        data_source_id: str | None,
        limit: int,
    ) -> list[SuggestionProfilingRequestEntity]:
        rows = [row for row in self._store.values() if row.get("requested_by_user_id") == user_id]
        if data_source_id:
            rows = [row for row in rows if row.get("data_source_id") == data_source_id]
        rows = sorted(rows, key=lambda item: item.get("requested_at") or "", reverse=True)
        return [
            SuggestionProfilingRequestEntity.model_validate(row)
            for row in rows[: max(1, min(limit, 100))]
        ]

    def request_profiling(self, *, user_id: str, data_source_id: str) -> SuggestionProfilingStartEntity:
        source = next((row for row in self.data_sources if row.get("data_source_id") == data_source_id), None)
        if source is None:
            raise ProfilingDataSourceNotFoundError("Data source not found")

        latest = next(
            (
                row
                for row in sorted(
                    self._store.values(),
                    key=lambda item: item.get("requested_at") or "",
                    reverse=True,
                )
                if row.get("data_source_id") == data_source_id
            ),
            None,
        )
        if latest and latest.get("requested_at"):
            last_requested_at = datetime.fromisoformat(str(latest["requested_at"]))
            now = datetime.now(UTC)
            delta = now - (last_requested_at if last_requested_at.tzinfo else last_requested_at.replace(tzinfo=UTC))
            min_interval = timedelta(hours=24)
            if delta < min_interval:
                minutes_remaining = int((min_interval - delta).total_seconds() // 60) + 1
                raise ProfilingRateLimitError(
                    last_requested_at=str(latest["requested_at"]),
                    minutes_remaining=minutes_remaining,
                )

        request_id = str(uuid4())
        row = {
            "id": request_id,
            "profiling_request_id": request_id,
            "data_source_id": data_source_id,
            "requested_by_user_id": user_id,
            "requested_at": _utc_iso(datetime.now(UTC)),
            "started_at": None,
            "completed_at": None,
            "status": "pending",
            "error_message": None,
            "result_metadata_id": None,
            "job_id": None,
        }
        self._store[request_id] = row
        return SuggestionProfilingStartEntity(
            profiling_request_id=request_id,
            message="Data profiling started. This may take a few minutes.",
            status="pending",
        )

    def get_profiling_request_status(self, profiling_request_id: str) -> SuggestionProfilingRequestEntity:
        row = self._store.get(profiling_request_id)
        if row is None:
            raise ProfilingRequestNotFoundError("Profiling request not found")
        return SuggestionProfilingRequestEntity.model_validate(row)

    def find_active_profiling_request(self, data_source_id: str) -> SuggestionProfilingRequestEntity | None:
        for row in sorted(self._store.values(), key=lambda item: item.get("requested_at") or "", reverse=True):
            if str(row.get("data_source_id") or "") != str(data_source_id or ""):
                continue
            if str(row.get("status") or "").strip() not in {"pending", "started"}:
                continue
            return SuggestionProfilingRequestEntity.model_validate(row)
        return None

    def create_request(self, request: ProfilingRequest) -> ProfilingRequest:
        profiling_request_id = request.profiling_request_id or f"pr-{int(datetime.utcnow().timestamp()*1000)}"
        now = request.requested_at or datetime.utcnow()
        row = {
            "id": self._next_id,
            "profiling_request_id": profiling_request_id,
            "data_source_id": request.data_source_id,
            "requested_by_user_id": request.requested_by_user_id,
            "requested_at": now,
            "started_at": None,
            "completed_at": None,
            "status": request.status or "pending",
            "error_message": None,
            "result_metadata_id": None,
            "job_id": request.job_id,
        }
        self._store[profiling_request_id] = row
        self._next_id += 1
        return ProfilingRequest(**row)

    def set_started(self, profiling_request_id: str, job_id: str) -> None:
        row = self._store.get(profiling_request_id)
        if row is None:
            raise KeyError(f"profiling_request {profiling_request_id} not found")
        row["started_at"] = datetime.utcnow()
        row["job_id"] = job_id
        row["status"] = "started"

    def set_completed(self, profiling_request_id: str, success: bool, error_message: Optional[str] = None) -> None:
        row = self._store.get(profiling_request_id)
        if row is None:
            raise KeyError(f"profiling_request {profiling_request_id} not found")
        row["completed_at"] = datetime.utcnow()
        row["status"] = "completed" if success else "failed"
        row["error_message"] = error_message
