from __future__ import annotations
import os
from datetime import UTC, datetime, timedelta
import json
from typing import Optional
from uuid import uuid4

import redis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.otel_metrics import record_suggestions_redis_failure
from app.core.otel_metrics import record_suggestions_redis_request
from app.domain.entities import SuggestionProfilingRequestEntity
from app.domain.entities import SuggestionProfilingStartEntity
from app.domain.entities.profiling_request import ProfilingRequest
from app.domain.interfaces.profiling_repository import ProfilingDataSourceNotFoundError
from app.domain.interfaces.profiling_repository import ProfilingEnqueueFailedError
from app.domain.interfaces.profiling_repository import ProfilingRateLimitError
from app.domain.interfaces.profiling_repository import ProfilingRepository
from app.domain.interfaces.profiling_repository import ProfilingRequestNotFoundError
from app.domain.user_names import normalize_user_name_parts
from app.infrastructure.orm.session import session_scope
from app.infrastructure.orm.models import DataSourceMetadataRow
from app.infrastructure.orm.models import DataSourceProfilingRequestRow
from app.infrastructure.orm.models import UserRow


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.isoformat()


def _to_profiling_request_entity(row: DataSourceProfilingRequestRow) -> SuggestionProfilingRequestEntity:
    return SuggestionProfilingRequestEntity(
        id=row.id,
        data_source_id=row.data_source_id,
        requested_by_user_id=row.requested_by_user_id,
        requested_at=_to_iso(row.requested_at),
        started_at=_to_iso(row.started_at),
        completed_at=_to_iso(row.completed_at),
        status=row.status,
        error_message=row.error_message,
        result_metadata_id=row.result_metadata_id,
        job_id=row.job_id,
    )


class PostgresProfilingRepository(ProfilingRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def get_data_source_name(self, data_source_id: str) -> str | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(DataSourceMetadataRow).where(DataSourceMetadataRow.data_source_id == data_source_id)
            ).scalar_one_or_none()
        if row is None:
            return None
        return str(row.name or "").strip() or None

    def list_profiling_requests(
        self,
        *,
        user_id: str,
        data_source_id: str | None,
        limit: int,
    ) -> list[SuggestionProfilingRequestEntity]:
        normalized_limit = max(1, min(limit, 100))

        with session_scope(self.database_url) as session:
            requester_ids = self._resolve_requester_ids(session, user_id)
            stmt = select(DataSourceProfilingRequestRow).where(
                DataSourceProfilingRequestRow.requested_by_user_id.in_(sorted(requester_ids))
            )
            if data_source_id:
                stmt = stmt.where(DataSourceProfilingRequestRow.data_source_id == data_source_id)

            rows = session.execute(
                stmt.order_by(DataSourceProfilingRequestRow.requested_at.desc()).limit(normalized_limit)
            ).scalars().all()

        return [_to_profiling_request_entity(row) for row in rows]

    def request_profiling(self, *, user_id: str, data_source_id: str) -> SuggestionProfilingStartEntity:
        request_id = str(uuid4())
        requested_at = datetime.now(UTC)

        with session_scope(self.database_url) as session:
            requester_id = self._resolve_or_create_user_id(session, user_id)
            source = session.execute(
                select(DataSourceMetadataRow).where(DataSourceMetadataRow.data_source_id == data_source_id)
            ).scalar_one_or_none()

            if source is None:
                raise ProfilingDataSourceNotFoundError("Data source not found")

            latest = session.execute(
                select(DataSourceProfilingRequestRow)
                .where(DataSourceProfilingRequestRow.data_source_id == data_source_id)
                .order_by(DataSourceProfilingRequestRow.requested_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            if latest is not None and latest.requested_at is not None:
                now = datetime.now(UTC)
                last = latest.requested_at if latest.requested_at.tzinfo else latest.requested_at.replace(tzinfo=UTC)
                delta = now - last
                min_interval = timedelta(hours=24)
                if delta < min_interval:
                    minutes_remaining = int((min_interval - delta).total_seconds() // 60) + 1
                    raise ProfilingRateLimitError(
                        last_requested_at=_to_iso(latest.requested_at),
                        minutes_remaining=minutes_remaining,
                    )

            session.add(
                DataSourceProfilingRequestRow(
                    id=request_id,
                    data_source_id=data_source_id,
                    requested_by_user_id=requester_id,
                    requested_at=requested_at,
                    status="pending",
                )
            )
            session.commit()

            source_name = source.name
            source_type = source.source_type

        try:
            self._enqueue_profiling_request(
                request_id=request_id,
                data_source_id=data_source_id,
                user_id=user_id,
                data_source_name=source_name,
                source_type=source_type,
            )
        except Exception as exc:
            self._mark_request_enqueue_failed(request_id=request_id, error_message=str(exc))
            raise ProfilingEnqueueFailedError(profiling_request_id=request_id) from exc

        return SuggestionProfilingStartEntity(
            profiling_request_id=request_id,
            message="Data profiling started. This may take a few minutes.",
            status="pending",
        )

    def get_profiling_request_status(self, profiling_request_id: str) -> SuggestionProfilingRequestEntity:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(DataSourceProfilingRequestRow).where(DataSourceProfilingRequestRow.id == profiling_request_id)
            ).scalar_one_or_none()

        if row is None:
            raise ProfilingRequestNotFoundError("Profiling request not found")

        return _to_profiling_request_entity(row)

    def find_active_profiling_request(self, data_source_id: str) -> SuggestionProfilingRequestEntity | None:
        with session_scope(self.database_url) as session:
            row = session.execute(
                select(DataSourceProfilingRequestRow)
                .where(DataSourceProfilingRequestRow.data_source_id == data_source_id)
                .where(DataSourceProfilingRequestRow.status.in_(["pending", "started"]))
                .order_by(DataSourceProfilingRequestRow.requested_at.desc())
                .limit(1)
            ).scalar_one_or_none()

        if row is None:
            return None

        return _to_profiling_request_entity(row)

    def create_request(self, request: ProfilingRequest) -> ProfilingRequest:
        # Use supplied profiling_request_id as the row id (consistent with existing DDL where id is string)
        row_id = request.profiling_request_id or str(uuid4())
        with session_scope(self.database_url) as session:
            row = DataSourceProfilingRequestRow(
                id=row_id,
                data_source_id=request.data_source_id or "",
                requested_by_user_id=request.requested_by_user_id or "",
                requested_at=request.requested_at or datetime.utcnow(),
                status=request.status or "pending",
                error_message=request.error_message,
                job_id=request.job_id,
            )
            session.add(row)
            session.commit()

        return ProfilingRequest(
            id=None,
            profiling_request_id=row_id,
            data_source_id=request.data_source_id,
            requested_by_user_id=request.requested_by_user_id,
            requested_at=request.requested_at,
            started_at=request.started_at,
            completed_at=request.completed_at,
            status=row.status,
            error_message=row.error_message,
            job_id=row.job_id,
        )

    def set_started(self, profiling_request_id: str, job_id: str) -> None:
        with session_scope(self.database_url) as session:
            row = session.get(DataSourceProfilingRequestRow, profiling_request_id)
            if row is None:
                raise KeyError(f"profiling_request {profiling_request_id} not found")
            row.started_at = datetime.utcnow()
            row.job_id = job_id
            row.status = "started"
            session.commit()

    def set_completed(self, profiling_request_id: str, success: bool, error_message: Optional[str] = None) -> None:
        with session_scope(self.database_url) as session:
            row = session.get(DataSourceProfilingRequestRow, profiling_request_id)
            if row is None:
                raise KeyError(f"profiling_request {profiling_request_id} not found")
            row.completed_at = datetime.utcnow()
            row.status = "completed" if success else "failed"
            if error_message:
                row.error_message = error_message
            session.commit()

    def _resolve_or_create_user_id(self, session, user_id: str) -> str:
        requester = session.execute(select(UserRow).where(UserRow.id == user_id)).scalar_one_or_none()
        if requester is None:
            requester = session.execute(select(UserRow).where(UserRow.external_id == user_id)).scalar_one_or_none()
        if requester is None and "@" in user_id:
            requester = session.execute(select(UserRow).where(UserRow.email == user_id)).scalar_one_or_none()
        if requester is not None:
            return requester.id

        first_name, last_name = normalize_user_name_parts("", "", fallback=user_id)
        email = user_id if "@" in user_id else None
        session.add(UserRow(id=user_id, first_name=first_name, last_name=last_name, email=email, external_id=user_id))
        return user_id

    def _resolve_requester_ids(self, session, user_id: str) -> set[str]:
        requester_ids = {user_id}
        requester = session.execute(select(UserRow).where(UserRow.id == user_id)).scalar_one_or_none()
        if requester is None:
            requester = session.execute(select(UserRow).where(UserRow.external_id == user_id)).scalar_one_or_none()
        if requester is None and "@" in user_id:
            requester = session.execute(select(UserRow).where(UserRow.email == user_id)).scalar_one_or_none()
        if requester is not None:
            requester_ids.add(requester.id)
            if requester.external_id:
                requester_ids.add(requester.external_id)
        return requester_ids

    def _enqueue_profiling_request(
        self,
        *,
        request_id: str,
        data_source_id: str,
        user_id: str,
        data_source_name: str,
        source_type: str,
    ) -> None:
        settings = get_settings()
        redis_host = settings.redis_host if hasattr(settings, "redis_host") else "redis"
        redis_port = int(getattr(settings, "redis_port", 6379))
        redis_password = getattr(settings, "redis_password", None)
        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            decode_responses=True,
            ssl=True,
            ssl_cert_reqs="required",
            ssl_ca_certs=os.getenv("REDIS_CA_BUNDLE")
            or os.getenv("SSL_CERT_FILE")
            or "/etc/openmetadata/certs/internal-ca-bundle.pem",
            ssl_check_hostname=True,
        )
        queue_name = "bull:data-profiling:wait"
        job_payload = {
            "profiling_request_id": request_id,
            "data_source_id": data_source_id,
            "user_id": user_id,
            "data_source_name": data_source_name,
            "source_type": source_type,
        }
        try:
            client.rpush(queue_name, json.dumps({"data": job_payload}))
        except Exception as exc:
            record_suggestions_redis_failure(operation_type="rpush", failure_type=exc.__class__.__name__)
            raise

        record_suggestions_redis_request(operation_type="rpush", status="success")

    def _mark_request_enqueue_failed(self, *, request_id: str, error_message: str) -> None:
        with session_scope(self.database_url) as session:
            row = session.get(DataSourceProfilingRequestRow, request_id)
            if row is None:
                return
            row.status = "failed"
            row.error_message = error_message[:1000]
            session.commit()
