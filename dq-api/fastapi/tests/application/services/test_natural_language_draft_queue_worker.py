from __future__ import annotations

from threading import Event

import pytest

import app.application.services.natural_language_draft_queue_worker as worker_module


class _FakeThread:
    def __init__(self, *, target, name: str, daemon: bool) -> None:
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        self.join_timeout = None

    def start(self) -> None:
        self.started = True

    def join(self, timeout: float | None = None) -> None:
        self.join_timeout = timeout


def test_build_natural_language_draft_queue_worker_initializes_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker_module, "Thread", _FakeThread)

    worker = worker_module.build_natural_language_draft_queue_worker(
        queue_key="dq-natural-language-draft:queue",
        redis_url="redis://redis:6379/0",
        llm_service_url="https://dq-made-easy-llm:8000",
    )

    assert isinstance(worker._thread, _FakeThread)
    assert worker._thread.name == "natural-language-draft-worker"
    assert worker._thread.daemon is True

    worker.start()
    assert worker._thread.started is True

    worker.stop_event = Event()
    worker.stop()
    assert worker._thread.join_timeout == 5