from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI

from app.core import telemetry


class _DummySpan:
    def __init__(self, recording: bool = True) -> None:
        self._recording = recording
        self.attributes: dict[str, object] = {}

    def is_recording(self) -> bool:
        return self._recording

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


def test_trace_export_debug_enabled_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_TRACE_EXPORT_DEBUG", "true")
    assert telemetry._trace_export_debug_enabled() is True

    monkeypatch.setenv("OTEL_TRACE_EXPORT_DEBUG", "0")
    assert telemetry._trace_export_debug_enabled() is False


def test_build_trace_exporter_wraps_exporter_when_debug_enabled(monkeypatch) -> None:
    base_exporter = SimpleNamespace(export=lambda spans: spans, shutdown=lambda: None, force_flush=lambda timeout=30000: True)
    monkeypatch.setattr(telemetry, "_otlp_protocol", lambda endpoint=None: "http")
    monkeypatch.setattr(telemetry, "OTLPHttpSpanExporter", lambda endpoint: base_exporter)
    monkeypatch.setenv("OTEL_TRACE_EXPORT_DEBUG", "1")

    exporter = telemetry._build_trace_exporter("http://collector:4318/v1/traces")

    assert isinstance(exporter, telemetry._LoggingSpanExporter)
    assert exporter._exporter is base_exporter


def test_set_span_attributes_handles_scalars_sequences_and_fallback_string() -> None:
    span = _DummySpan(recording=True)

    telemetry.set_span_attributes(
        span,
        string_value="ok",
        number_value=3,
        bool_value=True,
        list_value=["a", "b"],
        tuple_value=(1, 2),
        dict_value={"k": "v"},
        none_value=None,
    )

    assert span.attributes["string_value"] == "ok"
    assert span.attributes["number_value"] == 3
    assert span.attributes["bool_value"] is True
    assert span.attributes["list_value"] == ["a", "b"]
    assert span.attributes["tuple_value"] == [1, 2]
    assert span.attributes["dict_value"] == "{'k': 'v'}"
    assert "none_value" not in span.attributes


def test_set_span_attributes_ignores_non_recording_span() -> None:
    span = _DummySpan(recording=False)

    telemetry.set_span_attributes(span, key="value")

    assert span.attributes == {}


def test_instrument_app_is_idempotent_for_same_app(monkeypatch) -> None:
    app = FastAPI()
    settings = SimpleNamespace(database_url=None)
    instrument_app_mock = Mock()

    monkeypatch.setattr(telemetry, "configure_telemetry", lambda cfg: None)
    monkeypatch.setattr(telemetry.FastAPIInstrumentor, "instrument_app", instrument_app_mock)
    monkeypatch.setattr(telemetry, "_INSTRUMENTED_APPS", set())

    telemetry.instrument_app(app, settings)
    telemetry.instrument_app(app, settings)

    instrument_app_mock.assert_called_once()


def test_shutdown_telemetry_flushes_trace_and_meter(monkeypatch) -> None:
    trace_provider = SimpleNamespace(force_flush=Mock())
    meter_provider = SimpleNamespace(force_flush=Mock())

    monkeypatch.setattr(telemetry, "_TRACE_PROVIDER", trace_provider)
    monkeypatch.setattr(telemetry, "_METER_PROVIDER", meter_provider)

    telemetry.shutdown_telemetry()

    trace_provider.force_flush.assert_called_once()
    meter_provider.force_flush.assert_called_once()