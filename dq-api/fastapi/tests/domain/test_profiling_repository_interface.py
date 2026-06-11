from datetime import datetime, timezone

import pytest

from app.domain.entities.profiling_request import ProfilingRequest
from app.domain.interfaces.profiling_repository import ProfilingRepository


def _sample_request() -> ProfilingRequest:
    now = datetime.now(timezone.utc)
    return ProfilingRequest(
        id=None,
        profiling_request_id="pr-1",
        data_source_id="source-1",
        requested_by_user_id="user-1",
        requested_at=now,
        started_at=None,
        completed_at=None,
        status="queued",
        error_message=None,
        job_id=None,
    )


def test_profiling_repository_methods_fail_fast_when_not_implemented() -> None:
    request = _sample_request()

    with pytest.raises(NotImplementedError):
        ProfilingRepository.create_request(object(), request)

    with pytest.raises(NotImplementedError):
        ProfilingRepository.set_started(object(), "pr-1", "job-1")

    with pytest.raises(NotImplementedError):
        ProfilingRepository.set_completed(object(), "pr-1", success=False, error_message="boom")