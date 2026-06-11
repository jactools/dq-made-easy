from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.presenters.profiling_enqueue import build_profiling_enqueue_response_payload
from app.api.presenters.profiling_enqueue import require_profiling_started_job_id
from app.api.presenters.profiling_enqueue import resolve_profiling_completion_success
from app.api.presenters.profiling_enqueue import resolve_profiling_enqueue_correlation_id
from app.api.presenters.profiling_enqueue import resolve_profiling_enqueue_settings


def test_profiling_enqueue_presenters() -> None:
    settings = SimpleNamespace(name="fallback")
    app_settings = SimpleNamespace(name="app")
    assert resolve_profiling_enqueue_settings(app_settings, settings) is app_settings
    assert resolve_profiling_enqueue_settings(None, settings) is settings

    corr, generated = resolve_profiling_enqueue_correlation_id(
        SimpleNamespace(correlation_id="body-corr"),
        None,
        {"X-Correlation-ID": "header-corr"},
    )
    assert corr == "body-corr"
    assert generated is False

    corr2, generated2 = resolve_profiling_enqueue_correlation_id({}, "ctx-corr", {"x-correlation-id": "header-corr"})
    assert corr2 == "ctx-corr"
    assert generated2 is False

    corr3, generated3 = resolve_profiling_enqueue_correlation_id({}, None, {})
    assert corr3
    assert generated3 is True

    assert build_profiling_enqueue_response_payload(SimpleNamespace(enqueued=True, job_id="job-1")) == {
        "enqueued": True,
        "job_id": "job-1",
    }
    assert require_profiling_started_job_id("started", "job-1") == "job-1"
    with pytest.raises(ValueError):
        require_profiling_started_job_id("started", None)
    assert require_profiling_started_job_id("completed", None) is None
    assert resolve_profiling_completion_success("completed") is True
    assert resolve_profiling_completion_success("failed") is False
