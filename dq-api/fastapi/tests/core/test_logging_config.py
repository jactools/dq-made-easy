import logging
import json
import sys

from app.core import logging_config


def test_normalize_environment_label_maps_known_values() -> None:
    assert logging_config.normalize_environment_label("development") == "dev"
    assert logging_config.normalize_environment_label("local") == "dev"
    assert logging_config.normalize_environment_label("testing") == "test"
    assert logging_config.normalize_environment_label("ci") == "test"
    assert logging_config.normalize_environment_label("production") == "prod"
    assert logging_config.normalize_environment_label("staging") == "staging"


def test_telemetry_context_filter_sets_correlation_trace_and_span_fields(monkeypatch) -> None:
    monkeypatch.setattr(logging_config, "get_correlation_id", lambda: "corr-123")
    monkeypatch.setattr(logging_config, "get_user_id", lambda: None)
    monkeypatch.setattr(logging_config, "_current_trace_id", lambda: "trace-abc")
    monkeypatch.setattr(logging_config, "_current_span_id", lambda: "span-def")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "dq-api-test")
    monkeypatch.setenv("OTEL_SERVICE_VERSION", "1.2.3")

    record = logging.LogRecord(
        name="tests.logging",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    context_filter = logging_config._TelemetryContextFilter()
    assert context_filter.filter(record) is True

    assert record.correlation_id == "corr-123"
    assert record.correlationId == "corr-123"
    assert record.user_id == "anonymous"
    assert record.trace_id == "trace-abc"
    assert record.span_id == "span-def"
    assert record.environment == "prod"
    assert record.service_name == "dq-api-test"
    assert record.service_version == "1.2.3"


def test_telemetry_context_filter_preserves_existing_record_fields(monkeypatch) -> None:
    monkeypatch.setattr(logging_config, "get_correlation_id", lambda: "corr-override")
    monkeypatch.setattr(logging_config, "get_user_id", lambda: "user-from-context")
    monkeypatch.setattr(logging_config, "_current_trace_id", lambda: "trace-new")
    monkeypatch.setattr(logging_config, "_current_span_id", lambda: "span-new")

    record = logging.LogRecord(
        name="tests.logging.existing",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.user_id = "existing-user"
    record.environment = "existing-env"
    record.service_name = "existing-service"
    record.service_version = "existing-version"

    context_filter = logging_config._TelemetryContextFilter()
    assert context_filter.filter(record) is True

    assert record.user_id == "existing-user"
    assert record.environment == "existing-env"
    assert record.service_name == "existing-service"
    assert record.service_version == "existing-version"


def test_json_formatter_excludes_private_and_stdlib_fields_and_serializes_exception() -> None:
    formatter = logging_config._JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="tests.logging.formatter",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="error happened",
            args=(),
            exc_info=sys.exc_info(),
        )
        record.custom_field = "visible"
        record._private_field = "hidden"
        rendered = formatter.format(record)

    payload = json.loads(rendered)
    assert payload["msg"] == "error happened"
    assert payload["custom_field"] == "visible"
    assert "_private_field" not in payload
    assert "exception" in payload
