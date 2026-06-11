from __future__ import annotations

import pytest

from app.core import otel_metrics


def test_endpoint_group_from_path_supports_api_and_gateway_prefixes() -> None:
    assert otel_metrics._endpoint_group_from_path("/api/rulebuilder/v1/rules/123") == "rules"
    assert otel_metrics._endpoint_group_from_path("/auth/v1/callback") == "auth"
    assert otel_metrics._endpoint_group_from_path("/") == "unknown"


def test_api_version_from_path_supports_api_and_gateway_prefixes() -> None:
    assert otel_metrics._api_version_from_path("/api/rulebuilder/v1/rules/123") == "v1"
    assert otel_metrics._api_version_from_path("/auth/v1/callback") == "v1"
    assert otel_metrics._api_version_from_path("/") == "unknown"


def test_record_request_metric_uses_low_cardinality_attributes(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Counter:
        def add(self, value, attributes):
            captured["count_value"] = value
            captured["count_attrs"] = attributes

    class _Histogram:
        def record(self, value, attributes):
            captured["hist_value"] = value
            captured["hist_attrs"] = attributes

    monkeypatch.setattr(otel_metrics, "_REQUEST_COUNTER", _Counter())
    monkeypatch.setattr(otel_metrics, "_LATENCY_HISTOGRAM", _Histogram())

    otel_metrics.record_request_metric(
        method="post",
        path="/api/rulebuilder/v1/rules/rule-1/activate",
        operation="/rules/{rule_id}/activate",
        status_code=200,
        duration_ms=18.5,
    )

    assert captured["count_value"] == 1
    assert captured["hist_value"] == 18.5
    attrs = captured["count_attrs"]
    assert attrs["endpoint_group"] == "rules"
    assert attrs["api_version"] == "v1"
    assert attrs["status"] == "success"
    assert attrs["method"] == "POST"
    assert attrs["operation"] == "/rules/{rule_id}/activate"
    assert captured["hist_attrs"] == attrs


def test_increment_auth_failure_records_reason(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Counter:
        def add(self, value, attributes):
            captured["count_value"] = value
            captured["count_attrs"] = attributes

    monkeypatch.setattr(otel_metrics, "_AUTH_FAILURE_COUNTER", _Counter())

    otel_metrics.increment_auth_failure(
        method="GET",
        path="/api/admin/v1/me",
        reason="missing_token",
    )

    assert captured["count_value"] == 1
    attrs = captured["count_attrs"]
    assert attrs["endpoint_group"] == "me"
    assert attrs["method"] == "GET"
    assert attrs["reason"] == "missing_token"


def test_record_async_queue_event_normalizes_attributes(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Counter:
        def add(self, value, attributes):
            captured["count_value"] = value
            captured["count_attrs"] = attributes

    monkeypatch.setattr(otel_metrics, "_QUEUE_EVENT_COUNTER", _Counter())

    otel_metrics.record_async_queue_event(
        service="DQ-API",
        queue_type="GX_EXECUTION",
        stage="Queued",
        result="Success",
    )

    assert captured["count_value"] == 1
    assert captured["count_attrs"] == {
        "service": "dq-api",
        "queue_type": "gx_execution",
        "stage": "queued",
        "result": "success",
    }


def test_record_natural_language_draft_request_event_records_generic_queue_event(monkeypatch) -> None:
    captured: dict[str, list[tuple[int, dict[str, str]]]] = {}

    class _Counter:
        def __init__(self, key: str) -> None:
            self.key = key

        def add(self, value, attributes):
            captured.setdefault(self.key, []).append((value, attributes))

    monkeypatch.setattr(otel_metrics, "_NATURAL_LANGUAGE_DRAFT_REQUEST_EVENT_COUNTER", _Counter("draft"))
    monkeypatch.setattr(otel_metrics, "_QUEUE_EVENT_COUNTER", _Counter("queue"))

    otel_metrics.record_natural_language_draft_request_event(
        stage="Completed",
        result="Succeeded",
        analysis_provider="DQ-LLM",
        error_code=None,
    )

    assert captured["draft"] == [
        (
            1,
            {
                "stage": "completed",
                "result": "succeeded",
                "analysis_provider": "dq-llm",
                "error_code": "none",
            },
        )
    ]
    assert captured["queue"] == [
        (
            1,
            {
                "service": "dq-api",
                "queue_type": "natural_language_draft",
                "stage": "completed",
                "result": "succeeded",
            },
        )
    ]


def test_record_gx_operation_metric_uses_low_cardinality_attributes(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Counter:
        def __init__(self, bucket: str) -> None:
            self.bucket = bucket

        def add(self, value, attributes):
            captured.setdefault(self.bucket, []).append((value, attributes))

    class _Histogram:
        def record(self, value, attributes):
            captured.setdefault("hist_calls", []).append((value, attributes))

    monkeypatch.setattr(otel_metrics, "_GX_OPERATION_COUNTER", _Counter("count_calls"))
    monkeypatch.setattr(otel_metrics, "_GX_OPERATION_LATENCY_HISTOGRAM", _Histogram())
    monkeypatch.setattr(otel_metrics, "_EXECUTION_COMPILE_EVENT_COUNTER", _Counter("compile_calls"))
    monkeypatch.setattr(otel_metrics, "_EXECUTION_DISPATCH_EVENT_COUNTER", _Counter("dispatch_calls"))

    otel_metrics.record_gx_operation_metric(
        surface="gx_api",
        operation="start_suite_run",
        result="accepted",
        status_code=202,
        duration_ms=31.25,
        engine_target="pyspark",
        execution_shape="single_object",
    )

    count_value, count_attrs = captured["count_calls"][0]
    hist_value, hist_attrs = captured["hist_calls"][0]
    assert count_value == 1
    assert hist_value == 31.25
    assert count_attrs["surface"] == "gx_api"
    assert count_attrs["operation"] == "start_suite_run"
    assert count_attrs["result"] == "accepted"
    assert count_attrs["status_code"] == 202
    assert count_attrs["engine_target"] == "pyspark"
    assert count_attrs["execution_shape"] == "single_object"
    assert hist_attrs == count_attrs
    assert captured.get("compile_calls", []) == []
    assert captured["dispatch_calls"] == [
        (
            1,
            {
                "executor": "gx",
                "engine_type": "gx",
                "operation": "start_run",
                "result": "accepted",
                "execution_shape": "single_object",
            },
        )
    ]


def test_record_gx_operation_metric_emits_canonical_compile_events(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Counter:
        def __init__(self, bucket: str) -> None:
            self.bucket = bucket

        def add(self, value, attributes):
            captured.setdefault(self.bucket, []).append((value, attributes))

    class _Histogram:
        def record(self, value, attributes):
            captured.setdefault("hist_calls", []).append((value, attributes))

    monkeypatch.setattr(otel_metrics, "_GX_OPERATION_COUNTER", _Counter("count_calls"))
    monkeypatch.setattr(otel_metrics, "_GX_OPERATION_LATENCY_HISTOGRAM", _Histogram())
    monkeypatch.setattr(otel_metrics, "_EXECUTION_COMPILE_EVENT_COUNTER", _Counter("compile_calls"))
    monkeypatch.setattr(otel_metrics, "_EXECUTION_DISPATCH_EVENT_COUNTER", _Counter("dispatch_calls"))

    otel_metrics.record_gx_operation_metric(
        surface="gx_api",
        operation="save_suite",
        result="succeeded",
        status_code=200,
        duration_ms=12.5,
    )

    assert captured["compile_calls"] == [
        (1, {"engine_type": "gx", "operation": "compile_artifact", "result": "succeeded"})
    ]
    assert captured.get("dispatch_calls", []) == []


def test_record_execution_planner_choice_uses_low_cardinality_attributes(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Counter:
        def add(self, value, attributes):
            captured["count_value"] = value
            captured["count_attrs"] = attributes

    monkeypatch.setattr(otel_metrics, "_EXECUTION_PLANNER_CHOICE_COUNTER", _Counter())

    otel_metrics.record_execution_planner_choice(
        planner="grouped_execution",
        choice="incremental_scope",
        execution_path="incremental_grouped_execution",
        batch_count=2,
        suite_count=4,
        engine_target="pyspark",
        execution_shape="grouped_scope",
    )

    assert captured["count_value"] == 1
    assert captured["count_attrs"] == {
        "planner": "grouped_execution",
        "choice": "incremental_scope",
        "execution_path": "incremental_grouped_execution",
        "batch_count": 2,
        "suite_count": 4,
        "engine_target": "pyspark",
        "execution_shape": "grouped_scope",
    }


def test_record_execution_runtime_cost_records_histogram(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Histogram:
        def record(self, value, attributes):
            captured["hist_value"] = value
            captured["hist_attrs"] = attributes

    monkeypatch.setattr(otel_metrics, "_EXECUTION_RUNTIME_COST_HISTOGRAM", _Histogram())

    otel_metrics.record_execution_runtime_cost(
        executor="pyspark_executor",
        execution_path="grouped_execution",
        planner_choice="full_scope",
        runtime_ms=14.75,
        batch_count=1,
        suite_count=3,
        engine_target="pyspark",
        execution_shape="grouped_scope",
    )

    assert captured["hist_value"] == 14.75
    assert captured["hist_attrs"] == {
        "executor": "pyspark_executor",
        "execution_path": "grouped_execution",
        "planner_choice": "full_scope",
        "batch_count": 1,
        "suite_count": 3,
        "engine_target": "pyspark",
        "execution_shape": "grouped_scope",
    }


def test_record_execution_data_scanned_records_row_and_byte_histograms(monkeypatch) -> None:
    captured: dict[str, list[tuple[float, dict[str, object]]]] = {}

    class _Histogram:
        def __init__(self, bucket: str) -> None:
            self.bucket = bucket

        def record(self, value, attributes):
            captured.setdefault(self.bucket, []).append((value, attributes))

    monkeypatch.setattr(otel_metrics, "_EXECUTION_DATA_SCANNED_ROWS_HISTOGRAM", _Histogram("rows"))
    monkeypatch.setattr(otel_metrics, "_EXECUTION_DATA_SCANNED_BYTES_HISTOGRAM", _Histogram("bytes"))

    otel_metrics.record_execution_data_scanned(
        executor="pyspark_executor",
        execution_path="incremental_grouped_execution",
        planner_choice="mixed_scope",
        batch_count=2,
        suite_count=4,
        data_scanned_rows=128,
        data_scanned_bytes=4096,
        engine_target="pyspark",
        execution_shape="grouped_scope",
    )

    assert captured["rows"] == [
        (
            128.0,
            {
                "executor": "pyspark_executor",
                "execution_path": "incremental_grouped_execution",
                "planner_choice": "mixed_scope",
                "batch_count": 2,
                "suite_count": 4,
                "engine_target": "pyspark",
                "execution_shape": "grouped_scope",
            },
        )
    ]
    assert captured["bytes"] == [
        (
            4096.0,
            {
                "executor": "pyspark_executor",
                "execution_path": "incremental_grouped_execution",
                "planner_choice": "mixed_scope",
                "batch_count": 2,
                "suite_count": 4,
                "engine_target": "pyspark",
                "execution_shape": "grouped_scope",
            },
        )
    ]


def test_increment_gx_failure_records_reason(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Counter:
        def __init__(self, bucket: str) -> None:
            self.bucket = bucket

        def add(self, value, attributes):
            captured.setdefault(self.bucket, []).append((value, attributes))

    monkeypatch.setattr(otel_metrics, "_GX_FAILURE_COUNTER", _Counter("legacy_calls"))
    monkeypatch.setattr(otel_metrics, "_EXECUTION_FAILURE_COUNTER", _Counter("canonical_calls"))

    otel_metrics.increment_gx_failure(
        surface="pyspark_executor",
        operation="execute_plan",
        reason="missing_validation_runner",
    )

    assert captured["legacy_calls"] == [
        (
            1,
            {
                "surface": "pyspark_executor",
                "operation": "execute_plan",
                "reason": "missing_validation_runner",
            },
        )
    ]
    attrs = captured["legacy_calls"][0][1]
    assert attrs["surface"] == "pyspark_executor"
    assert attrs["operation"] == "execute_plan"
    assert attrs["reason"] == "missing_validation_runner"
    assert captured["canonical_calls"] == [
        (
            1,
            {
                "executor": "gx",
                "engine_type": "gx",
                "failure_kind": "missing_validation_runner",
            },
        )
    ]


def test_gx_queue_backlog_callback_reports_queue_length(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Client:
        def llen(self, key: str) -> int:
            captured["queue_key"] = key
            return 7

        def close(self) -> None:
            captured["closed"] = True

    class _RedisModule:
        def from_url(self, url: str, decode_responses: bool = True):
            captured["redis_url"] = url
            captured["decode_responses"] = decode_responses
            return _Client()

    monkeypatch.setattr(otel_metrics, "redis_sync", _RedisModule(), raising=True)
    monkeypatch.setattr(otel_metrics, "_resolve_gx_dispatch_redis_url", lambda: "redis://stub", raising=True)
    monkeypatch.setattr(otel_metrics, "_resolve_gx_execution_queue_key", lambda: "dq-gx:execution-dispatch", raising=True)

    observations = list(otel_metrics._gx_queue_backlog_callback(otel_metrics.CallbackOptions()))

    assert captured["redis_url"] == "redis://stub"
    assert captured["decode_responses"] is True
    assert captured["queue_key"] == "dq-gx:execution-dispatch"
    assert captured["closed"] is True
    assert len(observations) == 1
    assert observations[0].value == 7
    assert observations[0].attributes["queue_key"] == "dq-gx:execution-dispatch"


def test_gx_queue_backlog_callback_fails_without_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(otel_metrics, "_resolve_gx_dispatch_redis_url", lambda: None, raising=True)

    with pytest.raises(RuntimeError, match="GX dispatch Redis URL is not configured"):
        list(otel_metrics._gx_queue_backlog_callback(otel_metrics.CallbackOptions()))


def test_resolve_gx_execution_queue_key_requires_explicit_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GX_EXECUTION_QUEUE_KEY", raising=False)
    monkeypatch.delenv("DQ_GX_EXECUTION_QUEUE_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GX execution queue key is not configured"):
        otel_metrics._resolve_gx_execution_queue_key()


def test_resolve_gx_dispatch_redis_url_prefers_explicit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GX_EXECUTION_REDIS_URL", "redis://explicit")
    monkeypatch.setenv("REDIS_URL", "redis://fallback")

    assert otel_metrics._resolve_gx_dispatch_redis_url() == "redis://explicit"


def test_natural_language_draft_redis_url_and_backlog_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Client:
        def llen(self, key: str) -> int:
            captured["queue_key"] = key
            return 3

        def close(self) -> None:
            captured["closed"] = True

    class _RedisModule:
        def from_url(self, url: str, decode_responses: bool = True):
            captured["redis_url"] = url
            captured["decode_responses"] = decode_responses
            return _Client()

    monkeypatch.setenv("NATURAL_LANGUAGE_DRAFT_REDIS_URL", "redis://draft")
    monkeypatch.setattr(otel_metrics, "redis_sync", _RedisModule(), raising=True)
    monkeypatch.setattr(otel_metrics, "_resolve_natural_language_draft_queue_key", lambda: "dq-draft:queue", raising=True)

    assert otel_metrics._resolve_natural_language_draft_redis_url() == "redis://draft"
    observations = list(otel_metrics._natural_language_draft_queue_backlog_callback(otel_metrics.CallbackOptions()))

    assert captured["redis_url"] == "redis://draft"
    assert captured["decode_responses"] is True
    assert captured["queue_key"] == "dq-draft:queue"
    assert captured["closed"] is True
    assert observations[0].value == 3


def test_queue_backlog_callback_emits_configured_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    class _Client:
        def __init__(self, redis_url: str) -> None:
            self.redis_url = redis_url

        def llen(self, key: str) -> int:
            calls.append((self.redis_url, key))
            return {"dq-profiling:local-queue": 2, "dq-natural-language-draft:queue": 4}[key]

        def close(self) -> None:
            calls.append((self.redis_url, "closed"))

    class _RedisModule:
        def from_url(self, url: str, decode_responses: bool = True):
            assert decode_responses is True
            return _Client(url)

    monkeypatch.setattr(otel_metrics, "redis_sync", _RedisModule(), raising=True)
    monkeypatch.setattr(
        otel_metrics,
        "_configured_queue_specs",
        lambda: iter(
            (
                ("profiling", "dq-api", "dq-profiling:local-queue", lambda: "redis://profiling"),
                ("natural_language_draft", "dq-api", "dq-natural-language-draft:queue", lambda: "redis://draft"),
            )
        ),
        raising=True,
    )

    observations = list(otel_metrics._queue_backlog_callback(otel_metrics.CallbackOptions()))

    assert calls == [
        ("redis://profiling", "dq-profiling:local-queue"),
        ("redis://profiling", "closed"),
        ("redis://draft", "dq-natural-language-draft:queue"),
        ("redis://draft", "closed"),
    ]
    assert [(observation.value, observation.attributes) for observation in observations] == [
        (
            2,
            {
                "service": "dq-api",
                "queue_type": "profiling",
                "queue_key": "dq-profiling:local-queue",
            },
        ),
        (
            4,
            {
                "service": "dq-api",
                "queue_type": "natural_language_draft",
                "queue_key": "dq-natural-language-draft:queue",
            },
        ),
    ]


def test_queue_backlog_callback_fails_when_configured_queue_has_no_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(otel_metrics, "redis_sync", object(), raising=True)
    monkeypatch.setattr(
        otel_metrics,
        "_configured_queue_specs",
        lambda: iter((("natural_language_draft", "dq-api", "dq-natural-language-draft:queue", lambda: None),)),
        raising=True,
    )

    with pytest.raises(RuntimeError, match="Redis URL is not configured for queue type natural_language_draft"):
        list(otel_metrics._queue_backlog_callback(otel_metrics.CallbackOptions()))
