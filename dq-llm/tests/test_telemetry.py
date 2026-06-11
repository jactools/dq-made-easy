from contextlib import nullcontext

import pytest

from telemetry import traced_span, current_trace_id


class FakeSpan:
    def __init__(self):
        self.attributes = {}
        self.recorded = True

    def is_recording(self):
        return self.recorded

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def record_exception(self, exc):
        self.exception = exc

    def set_status(self, status):
        self.status = status


class FakeContextManager:
    def __init__(self, span):
        self._span = span

    def __enter__(self):
        return self._span

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeTracer:
    def __init__(self, span):
        self.span = span

    def start_as_current_span(self, name):
        return FakeContextManager(self.span)


def test_traced_span_sets_attributes(monkeypatch):
    span = FakeSpan()
    tracer = FakeTracer(span)

    monkeypatch.setattr("telemetry.trace.get_tracer", lambda name: tracer)

    with traced_span("demo", user_id="42") as active_span:
        assert active_span is span
        assert active_span.attributes["user_id"] == "42"


def test_current_trace_id_returns_none_without_valid_span(monkeypatch):
    class FakeContext:
        def __init__(self):
            self.is_valid = False

    class FakeSpanContext:
        def __init__(self):
            self.get_span_context = lambda: FakeContext()

    monkeypatch.setattr("telemetry.trace.get_current_span", lambda: FakeSpanContext())

    assert current_trace_id() is None
