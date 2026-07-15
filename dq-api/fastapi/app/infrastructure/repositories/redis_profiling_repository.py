from __future__ import annotations
import os
from typing import Optional

import json

import redis

from app.domain.entities import SuggestionProfilingRequestEntity
from app.domain.entities import SuggestionProfilingStartEntity
from app.domain.entities.profiling_request import ProfilingRequest
from app.domain.interfaces.profiling_repository import ProfilingRepository


class RedisProfilingRepository(ProfilingRepository):
    """Simple Redis-backed profiling request store using Redis hashes.

    Keys used: `profiling:{profiling_request_id}` -> hash of fields
    """

    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379, redis_db: int = 0, password: str | None = None) -> None:
        self._client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=password,
            decode_responses=True,
            ssl=True,
            ssl_cert_reqs="required",
            ssl_ca_certs=os.getenv("REDIS_CA_BUNDLE")
            or os.getenv("SSL_CERT_FILE")
            or "/etc/openmetadata/certs/internal-ca-bundle.pem",
            ssl_check_hostname=True,
        )

    def _key(self, profiling_request_id: str) -> str:
        return f"profiling:{profiling_request_id}"

    def get_data_source_name(self, data_source_id: str) -> str | None:
        raise NotImplementedError("RedisProfilingRepository does not support public profiling data-source lookups")

    def list_profiling_requests(
        self,
        *,
        user_id: str,
        data_source_id: str | None,
        limit: int,
    ) -> list[SuggestionProfilingRequestEntity]:
        raise NotImplementedError("RedisProfilingRepository does not support public profiling request listing")

    def request_profiling(self, *, user_id: str, data_source_id: str) -> SuggestionProfilingStartEntity:
        raise NotImplementedError("RedisProfilingRepository does not support public profiling enqueue")

    def get_profiling_request_status(self, profiling_request_id: str) -> SuggestionProfilingRequestEntity:
        raise NotImplementedError("RedisProfilingRepository does not support public profiling status reads")

    def find_active_profiling_request(self, data_source_id: str) -> SuggestionProfilingRequestEntity | None:
        for key in self._client.scan_iter(match=self._key("*")):
            payload = self._client.hgetall(key)
            if not payload:
                continue
            if str(payload.get("data_source_id") or "") != str(data_source_id or ""):
                continue
            if str(payload.get("status") or "").strip() not in {"pending", "started"}:
                continue
            return SuggestionProfilingRequestEntity.model_validate(payload)
        return None

    def create_request(self, request: ProfilingRequest) -> ProfilingRequest:
        key = self._key(request.profiling_request_id)
        payload = {
            "profiling_request_id": request.profiling_request_id,
            "data_source_id": request.data_source_id or "",
            "requested_by_user_id": request.requested_by_user_id or "",
            "requested_at": request.requested_at.isoformat(),
            "started_at": "",
            "completed_at": "",
            "status": request.status or "pending",
            "error_message": "",
            "job_id": request.job_id or "",
        }
        self._client.hset(key, mapping=payload)
        return request

    def set_started(self, profiling_request_id: str, job_id: str) -> None:
        key = self._key(profiling_request_id)
        if not self._client.exists(key):
            raise KeyError(f"profiling_request {profiling_request_id} not found")
        self._client.hset(key, mapping={"started_at": __import__("datetime").datetime.utcnow().isoformat(), "job_id": job_id, "status": "started"})

    def set_completed(self, profiling_request_id: str, success: bool, error_message: Optional[str] = None) -> None:
        key = self._key(profiling_request_id)
        if not self._client.exists(key):
            raise KeyError(f"profiling_request {profiling_request_id} not found")
        mapping = {"completed_at": __import__("datetime").datetime.utcnow().isoformat(), "status": "completed" if success else "failed"}
        if error_message:
            mapping["error_message"] = error_message
        self._client.hset(key, mapping=mapping)
