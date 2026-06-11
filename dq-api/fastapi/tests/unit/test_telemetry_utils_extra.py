from __future__ import annotations

import os
from types import SimpleNamespace

from app.core import telemetry


class DummySpanContext:
    def __init__(self, trace_id: int, span_id: int) -> None:
        self.trace_id = trace_id
        self.span_id = span_id


class DummySpan:
    def __init__(self) -> None:
        self._recording = True
        self.attributes: dict[str, object] = {}

    def is_recording(self) -> bool:
        return self._recording

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value

    def get_span_context(self) -> DummySpanContext:
        return DummySpanContext(trace_id=0x1, span_id=0x2)


class DummyExporter:
    def __init__(self) -> None:
        self.exported = []

    def export(self, spans: list[object]) -> telemetry.SpanExportResult:
        self.exported.append(spans)
        return telemetry.SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def test_normalize_environment_label() -> None:
    assert telemetry.normalize_environment_label("development") == "dev"
    assert telemetry.normalize_environment_label("CI") == "test"
    assert telemetry.normalize_environment_label("production") == "prod"
    assert telemetry.normalize_environment_label(None) == "dev"


def test_otlp_target_and_exporter_endpoint() -> None:
    assert telemetry._otlp_grpc_exporter_endpoint("http://localhost:4317")[0] == "localhost:4317"
    assert telemetry._otlp_grpc_exporter_endpoint("https://example.com:4318") == ("example.com:4318", False)
    assert telemetry._otlp_target("example.com:4318") == ("example.com", 4318)
    assert telemetry._otlp_target("no-host") == ("no-host", 4318)

    os.environ.pop("OTEL_EXPORTER_OTLP_PROTOCOL", None)
    assert telemetry._otlp_protocol("localhost:4317") == "grpc"
    assert telemetry._otlp_protocol("http://example.com:1234") == "http"


def test_metric_export_interval_and_sampler_ratio() -> None:
    os.environ["OTEL_METRIC_EXPORT_INTERVAL_MS"] = "not-a-number"
    assert telemetry._metric_export_interval_ms() == 10000

    os.environ["OTEL_TRACES_SAMPLER_ARG"] = "invalid"
    assert telemetry._sampler_ratio() == 0.1

    os.environ["OTEL_TRACES_SAMPLER_ARG"] = "0.9"
    assert telemetry._sampler_ratio() == 0.9


def test_extract_header_and_server_request_hook() -> None:
    scope = {"headers": [(b"x-correlation-id", b"corr-1")]}
    span = DummySpan()
    telemetry._server_request_hook(span, scope)
    assert span.attributes["correlation_id"] == "corr-1"
    assert scope["otel.trace_id"] == "00000000000000000000000000000001"
    assert span.attributes["environment"] == "dev"


def test_logging_span_exporter_export_success() -> None:
    exporter = telemetry._LoggingSpanExporter(DummyExporter(), "http://endpoint")
    fake_span = SimpleNamespace(
        context=SimpleNamespace(trace_id=0x1, span_id=0x2),
        attributes={"correlation_id": "corr", "job_id": "job", "profiling_request_id": "prid"},
    )
    result = exporter.export([fake_span])
    assert result == telemetry.SpanExportResult.SUCCESS
